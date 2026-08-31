const STAGES = ["plan", "image", "regions", "mask", "storyboard", "render"];
const STAGE_LABELS = {
  plan: "内容规划",
  image: "信息图生成",
  regions: "区域检测",
  mask: "遮罩分析",
  storyboard: "动画模板",
  render: "视频渲染",
};
const STATUS_LABELS = {
  pending: "排队中",
  running: "生成中",
  rendering: "渲染视频中",
  awaiting_render: "待生成视频",
  completed: "已完成",
  failed: "失败",
};

let currentTaskId = null;
let eventSource = null;

const $ = (id) => document.getElementById(id);

async function api(path, options) {
  const resp = await fetch(path, options);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `请求失败（${resp.status}）`);
  }
  return resp.json();
}

function init() {
  $("btn-create").addEventListener("click", createTask);
  $("btn-redo-image").addEventListener("click", () => redo("image"));
  $("btn-redo-regions").addEventListener("click", () => redo("regions"));
  $("btn-redo-render").addEventListener("click", () => redo("render"));
  $("btn-render").addEventListener("click", renderVideo);
  $("btn-retry").addEventListener("click", retryFailed);
  $("btn-new").addEventListener("click", resetUi);
  $("btn-new-from-error").addEventListener("click", resetUi);
  loadHistory();
}

async function createTask() {
  const text = $("input-text").value.trim();
  if (!text) {
    alert("请先输入一段文字");
    return;
  }
  $("btn-create").disabled = true;
  try {
    const meta = await api("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        intro_duration: parseFloat($("p-intro").value),
        point_duration: parseFloat($("p-point").value),
        transition_duration: parseFloat($("p-trans").value),
        outro_duration: parseFloat($("p-outro").value),
      }),
    });
    adoptTask(meta.id);
    loadHistory();
  } catch (err) {
    alert(err.message);
  } finally {
    $("btn-create").disabled = false;
  }
}

function adoptTask(taskId) {
  currentTaskId = taskId;
  $("step-input").classList.add("hidden");
  $("step-history").classList.add("hidden");
  $("step-error").classList.add("hidden");
  $("step-preview").classList.add("hidden");
  $("step-video").classList.add("hidden");
  $("step-progress").classList.remove("hidden");
  $("log").innerHTML = "";
  refreshMeta();
  connectSSE(taskId);
}

async function refreshMeta() {
  if (!currentTaskId) return;
  const meta = await api(`/api/tasks/${currentTaskId}`);
  renderMeta(meta);
}

function renderMeta(meta) {
  renderStageChips(meta);
  const busy = ["pending", "running", "rendering"].includes(meta.status);
  if (!busy) closeSSE();

  if (meta.status === "failed") {
    $("step-error").classList.remove("hidden");
    $("error-text").textContent = meta.error || "未知错误";
    $("step-preview").classList.add("hidden");
    $("step-video").classList.add("hidden");
    return;
  }
  $("step-error").classList.add("hidden");

  if ((meta.status === "awaiting_render" || meta.status === "completed") && meta.mask) {
    renderPreview(meta);
    $("step-preview").classList.remove("hidden");
  }
  if (meta.status === "completed" && meta.video) {
    const player = $("video-player");
    const src = `/api/download/${meta.id}`;
    if (player.getAttribute("src") !== src) {
      player.setAttribute("src", src);
      player.load();
    }
    $("btn-download").href = src;
    $("step-video").classList.remove("hidden");
  } else {
    $("step-video").classList.add("hidden");
  }
}

function renderStageChips(meta) {
  const box = $("stage-indicator");
  box.innerHTML = "";
  const activeIdx = meta.stage ? STAGES.indexOf(meta.stage) : -1;
  STAGES.forEach((stage, idx) => {
    const chip = document.createElement("span");
    chip.className = "stage-chip";
    chip.textContent = STAGE_LABELS[stage];
    if (meta.status === "failed" && idx === activeIdx) chip.classList.add("failed");
    else if (idx < activeIdx) chip.classList.add("done");
    else if (idx === activeIdx && ["running", "rendering"].includes(meta.status))
      chip.classList.add("active");
    else if (["completed", "awaiting_render"].includes(meta.status))
      chip.classList.add("done");
    box.appendChild(chip);
  });
}

function renderPreview(meta) {
  $("preview-infographic").src = `/api/tasks/${meta.id}/files/infographic.png`;
  const mask = meta.mask;
  const layer = $("preview-mask-layer");
  const sequence = $("mask-sequence");
  layer.innerHTML = "";
  sequence.innerHTML = "";
  $("mask-color-swatch").style.backgroundColor = mask.color;
  $("mask-color-value").textContent = mask.color;

  const masks = [];
  (mask.regions || []).forEach((region) => {
    const bbox = region.bbox;
    const cover = document.createElement("div");
    cover.className = "preview-mask";
    cover.style.left = `${bbox.x1 * 100}%`;
    cover.style.top = `${bbox.y1 * 100}%`;
    cover.style.width = `${(bbox.x2 - bbox.x1) * 100}%`;
    cover.style.height = `${(bbox.y2 - bbox.y1) * 100}%`;
    cover.style.backgroundColor = mask.color;
    layer.appendChild(cover);
    masks.push(cover);

    const step = document.createElement("button");
    step.className = "mask-step";
    const num = document.createElement("span");
    num.className = "num";
    num.textContent = region.id;
    const text = document.createElement("span");
    text.textContent = region.title;
    step.append(num, text);
    step.addEventListener("click", () => setPreviewStep(region.id, masks, sequence));
    sequence.appendChild(step);
  });

  const reset = document.createElement("button");
  reset.className = "mask-step active";
  reset.textContent = "初始状态 · 全部讲解区遮住";
  reset.addEventListener("click", () => setPreviewStep(0, masks, sequence));
  sequence.prepend(reset);
}

function setPreviewStep(step, masks, sequence) {
  masks.forEach((mask, index) => mask.classList.toggle("revealed", index < step));
  Array.from(sequence.children).forEach((button, index) => {
    button.classList.toggle("active", index === step);
  });
}

function connectSSE(taskId) {
  closeSSE();
  $("log").innerHTML = "";
  eventSource = new EventSource(`/api/tasks/${taskId}/events`);
  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    appendLog(data);
    refreshMeta();
  };
  eventSource.onerror = () => {
    // 服务端在终态后主动关闭连接；若任务仍在跑则自动重连由浏览器处理
    refreshMeta();
  };
}

function closeSSE() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
}

function appendLog(evt) {
  const line = document.createElement("div");
  line.textContent = `[${evt.time}] ${evt.message}`;
  if (evt.status === "failed") line.className = "err";
  const log = $("log");
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
}

async function renderVideo() {
  try {
    await api(`/api/tasks/${currentTaskId}/render`, { method: "POST" });
    connectSSE(currentTaskId);
    refreshMeta();
  } catch (err) {
    alert(err.message);
  }
}

async function redo(stage) {
  try {
    await api(`/api/tasks/${currentTaskId}/redo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stage }),
    });
    $("step-preview").classList.add("hidden");
    $("step-video").classList.add("hidden");
    connectSSE(currentTaskId);
    refreshMeta();
  } catch (err) {
    alert(err.message);
  }
}

async function retryFailed() {
  const meta = await api(`/api/tasks/${currentTaskId}`);
  await redo(meta.stage || "plan");
}

async function loadHistory() {
  let tasks = [];
  try {
    tasks = await api("/api/tasks");
  } catch {
    return;
  }
  const list = $("history-list");
  list.innerHTML = "";
  if (!tasks.length) {
    list.innerHTML = '<div class="history-item"><span class="excerpt">暂无任务</span></div>';
    return;
  }
  tasks.forEach((task) => {
    const item = document.createElement("div");
    item.className = "history-item";
    const excerpt = document.createElement("span");
    excerpt.className = "excerpt";
    excerpt.textContent = `${task.created_at} · ${(task.text || "").slice(0, 40)}`;
    const status = document.createElement("span");
    status.className = "status";
    status.dataset.status = task.status;
    status.textContent = STATUS_LABELS[task.status] || task.status;
    item.append(excerpt, status);
    item.addEventListener("click", () => {
      if (["running", "rendering", "pending"].includes(task.status)) {
        adoptTask(task.id);
      } else {
        currentTaskId = task.id;
        $("step-input").classList.add("hidden");
        $("step-progress").classList.remove("hidden");
        $("log").innerHTML = "";
        refreshMeta();
      }
      loadHistory();
    });
    list.appendChild(item);
  });
}

function resetUi() {
  closeSSE();
  currentTaskId = null;
  $("step-input").classList.remove("hidden");
  $("step-history").classList.remove("hidden");
  $("step-progress").classList.add("hidden");
  $("step-preview").classList.add("hidden");
  $("step-video").classList.add("hidden");
  $("step-error").classList.add("hidden");
  loadHistory();
}

init();
