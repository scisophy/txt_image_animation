"""信息图遮罩流水线：状态持久化、事件推送与断点续跑。"""
import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.core import (
    content_planner,
    image_generator,
    mask_builder,
    region_detector,
    storyboard_html,
    video_exporter,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

STAGES = ["plan", "image", "regions", "mask", "storyboard", "render"]
STAGE_LABELS = {
    "plan": "内容规划",
    "image": "信息图生成",
    "regions": "区域检测",
    "mask": "遮罩分析",
    "storyboard": "动画模板",
    "render": "视频渲染",
}

# AI 任务串行执行，避免文本、视觉与生图请求互相挤占方舟限流额度。
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pipeline")


class TaskStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def dir(self, task_id: str) -> Path:
        return self.root / task_id

    def create(self, text: str, params: dict) -> dict:
        task_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        meta = {
            "id": task_id,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "pending",
            "stage": None,
            "error": None,
            "text": text,
            "params": params,
            "plan": None,
            "mask": None,
            "video": None,
        }
        self.dir(task_id).mkdir(parents=True, exist_ok=True)
        self.save(task_id, meta)
        return meta

    def load(self, task_id: str) -> dict | None:
        path = self.dir(task_id) / "meta.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, task_id: str, meta: dict) -> None:
        path = self.dir(task_id) / "meta.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        # Windows 下读端（SSE 轮询）短暂持有 meta.json 句柄时 replace 会 WinError 5
        for _ in range(20):
            try:
                tmp.replace(path)
                return
            except PermissionError:
                time.sleep(0.05)
        tmp.replace(path)

    def list(self) -> list[dict]:
        tasks = []
        for child in self.root.iterdir():
            if child.is_dir():
                meta = self.load(child.name)
                if meta:
                    tasks.append(meta)
        tasks.sort(key=lambda m: m.get("created_at", ""), reverse=True)
        return tasks


class EventBus:
    def __init__(self) -> None:
        self._events: dict[str, list[dict]] = {}
        self._lock = threading.Lock()

    def emit(self, task_id: str, stage: str | None, message: str, status: str) -> None:
        with self._lock:
            events = self._events.setdefault(task_id, [])
            events.append(
                {
                    "seq": len(events),
                    "time": time.strftime("%H:%M:%S"),
                    "stage": stage,
                    "message": message,
                    "status": status,
                }
            )
            logger.info("[%s][%s] %s", task_id, stage, message)

    def snapshot(self, task_id: str) -> list[dict]:
        with self._lock:
            return list(self._events.get(task_id, []))


store = TaskStore(settings.output_dir)
bus = EventBus()


def _emit(task_id: str, meta: dict, message: str, stage: str | None = None) -> None:
    bus.emit(task_id, stage or meta.get("stage"), message, meta["status"])


def run_task(task_id: str, target: str = "storyboard") -> None:
    """在工作线程中执行；target 为 storyboard（停在预览）或 render（出片）。"""
    meta = store.load(task_id)
    if meta is None:
        return
    meta["status"] = "rendering" if target == "render" else "running"
    meta["error"] = None
    store.save(task_id, meta)
    _emit(task_id, meta, "任务开始" + ("（续跑）" if meta.get("stage") else ""))
    try:
        _run_stages(task_id, meta, target)
        meta["status"] = "completed" if target == "render" else "awaiting_render"
        _emit(task_id, meta, "视频渲染完成，可下载播放" if target == "render" else "遮罩分镜就绪，可预览或生成视频")
    except Exception as exc:  # noqa: BLE001 — 单任务失败不能拖垮服务
        logger.exception("任务 %s 失败", task_id)
        meta["status"] = "failed"
        meta["error"] = str(exc)
        _emit(task_id, meta, f"失败：{exc}")
    store.save(task_id, meta)


def _run_stages(task_id: str, meta: dict, target: str) -> None:
    workspace = store.dir(task_id)
    last_stage = target if target in STAGES else "storyboard"
    stages = STAGES[: STAGES.index(last_stage) + 1]

    for stage in stages:
        meta["stage"] = stage
        store.save(task_id, meta)
        _emit(task_id, meta, f"开始：{STAGE_LABELS[stage]}", stage)
        getattr(_stage_impl, stage)(task_id, meta, workspace)
        store.save(task_id, meta)
        _emit(task_id, meta, f"完成：{STAGE_LABELS[stage]}", stage)


class _stage_impl:
    """每个阶段先检查已有产物，实现断点续跑。"""

    @staticmethod
    def plan(task_id: str, meta: dict, workspace: Path) -> None:
        if meta.get("plan"):
            return
        plan = content_planner.plan_content(meta["text"])
        meta["plan"] = content_planner.plan_to_dict(plan)

    @staticmethod
    def image(task_id: str, meta: dict, workspace: Path) -> None:
        out = workspace / "infographic.png"
        if out.exists():
            return
        plan = meta["plan"]
        prompt = content_planner.build_image_prompt(meta["text"], _plan_obj(meta))
        image_generator.generate_infographic(prompt, out)

    @staticmethod
    def regions(task_id: str, meta: dict, workspace: Path) -> None:
        regions_path = workspace / "regions.json"
        if regions_path.exists():
            return
        regions = region_detector.detect_regions(
            workspace / "infographic.png", meta["plan"]["points"]
        )
        regions_path.write_text(
            json.dumps(
                [p.model_dump() for p in regions.points], ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )

    @staticmethod
    def mask(task_id: str, meta: dict, workspace: Path) -> None:
        mask_path = workspace / "mask.json"
        if meta.get("mask") and mask_path.exists():
            return
        regions_path = workspace / "regions.json"
        regions = region_detector.DetectedRegions(
            points=[
                region_detector.DetectedPoint(**p)
                for p in json.loads(regions_path.read_text(encoding="utf-8"))
            ]
        )
        meta["mask"] = mask_builder.build_mask_spec(workspace / "infographic.png", regions)
        mask_path.write_text(
            json.dumps(meta["mask"], ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @staticmethod
    def storyboard(task_id: str, meta: dict, workspace: Path) -> None:
        if (workspace / "index.html").exists():
            return
        storyboard_html.build_storyboard_html(
            workspace,
            meta["plan"].get("headline", ""),
            meta["mask"],
            meta.get("params") or {},
        )

    @staticmethod
    def render(task_id: str, meta: dict, workspace: Path) -> None:
        if (workspace / "final.mp4").exists():
            return
        video_exporter.export_video(workspace, fps=settings.video_fps)
        meta["video"] = "final.mp4"


def _plan_obj(meta: dict):
    from app.core.content_planner import ContentPlan

    return ContentPlan(**meta["plan"])


def start_task(task_id: str, target: str = "storyboard") -> None:
    """提交到串行执行队列（限流友好）。"""
    _executor.submit(run_task, task_id, target)


def redo(task_id: str, from_stage: str) -> str:
    """删除指定阶段及之后的产物并重跑。返回新的目标阶段。"""
    meta = store.load(task_id)
    if meta is None:
        raise KeyError(task_id)
    if meta["status"] in ("running", "rendering"):
        raise RuntimeError("任务正在执行中，请等待完成后再试")
    if from_stage not in STAGES:
        raise ValueError(f"未知阶段：{from_stage}")

    workspace = store.dir(task_id)
    idx = STAGES.index(from_stage)
    artifacts = {
        "plan": lambda: meta.update(plan=None),
        "image": lambda: _remove(workspace / "infographic.png"),
        "regions": lambda: _remove(workspace / "regions.json"),
        "mask": lambda: (
            _remove(workspace / "mask.json"),
            meta.update(mask=None),
        ),
        "storyboard": lambda: _remove(workspace / "index.html"),
        "render": lambda: (
            _remove(workspace / "final.mp4"),
            meta.update(video=None),
        ),
    }
    for stage in STAGES[idx:]:
        artifacts[stage]()
    meta["status"] = "pending"
    meta["error"] = None
    store.save(task_id, meta)

    target = "render" if from_stage == "render" else "storyboard"
    start_task(task_id, target)
    return target


def _remove(path: Path) -> None:
    if path.exists():
        path.unlink()
