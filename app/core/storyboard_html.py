"""阶段 3a：整图与遮罩规格 → HyperFrames composition HTML。

整个视频始终只展示一张完整信息图。所有讲解区域初始由主背景色遮住，
讲到对应要点时按叙事顺序逐个揭开，已经揭开的区域保持可见。
"""
import html
import json
import logging
import shutil
import urllib.request
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

COMPOSITION_ID = "main"
GSAP_VERSION = "3.14.2"
GSAP_CDN = f"https://cdn.jsdelivr.net/npm/gsap@{GSAP_VERSION}/dist/gsap.min.js"


def ensure_gsap(workspace: Path) -> str:
    """优先使用本地 gsap.min.js，避免渲染时依赖网络；下载失败才回退 CDN。"""
    local = workspace / "gsap.min.js"
    if local.exists() and local.stat().st_size > 0:
        return "gsap.min.js"
    asset = settings.assets_dir / "gsap.min.js"
    if not (asset.exists() and asset.stat().st_size > 0):
        asset.parent.mkdir(parents=True, exist_ok=True)
        try:
            logger.info("下载 GSAP 运行时：%s", GSAP_CDN)
            with urllib.request.urlopen(GSAP_CDN, timeout=30) as resp:
                asset.write_bytes(resp.read())
        except Exception:
            logger.warning("GSAP 下载失败，composition 将引用 CDN", exc_info=True)
            return GSAP_CDN
    shutil.copyfile(asset, local)
    return "gsap.min.js"


def compute_timeline(params: dict, num_points: int) -> dict:
    """计算顺序揭示节点，总时长 = intro + N*point + outro。"""
    intro = float(params.get("intro_duration", settings.intro_duration))
    outro = float(params.get("outro_duration", settings.outro_duration))
    point = float(params.get("point_duration", settings.point_duration))
    trans = float(params.get("transition_duration", settings.transition_duration))

    timeline = {
        "intro": {"start": 0.0, "duration": intro},
        "points": [
            {"id": i + 1, "start": intro + i * point, "duration": point}
            for i in range(num_points)
        ],
        "outro": {"start": intro + num_points * point, "duration": outro},
        "transition": trans,
        "point_duration": point,
        "total": intro + num_points * point + outro,
    }
    return timeline


def _fmt(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".")


def build_storyboard_html(
    workspace: Path,
    headline: str,
    mask_spec: dict,
    params: dict,
) -> Path:
    """生成任务工作区下的 index.html（standalone composition）。"""
    gsap_src = ensure_gsap(workspace)
    regions = sorted(mask_spec.get("regions") or [], key=lambda item: item["id"])
    if not regions:
        raise ValueError("遮罩规格中没有讲解区域")
    timeline = compute_timeline(params, len(regions))

    head = _html_head(headline, gsap_src)
    body_element = _storyboard_section(timeline, regions, mask_spec["color"])
    script = _timeline_script(timeline, regions)

    html_text = (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n'
        f"{head}\n"
        "<body>\n"
        '<div id="root" data-composition-id="main" data-start="0" '
        f'data-width="{settings.video_width}" data-height="{settings.video_height}" '
        f'data-duration="{_fmt(timeline["total"])}">\n'
        + body_element
        + "\n</div>\n"
        f"{script}\n"
        "</body>\n</html>\n"
    )
    out = workspace / "index.html"
    out.write_text(html_text, encoding="utf-8")
    logger.info("composition 已生成：%s（总时长 %.1fs）", out, timeline["total"])
    return out


def _html_head(headline: str, gsap_src: str) -> str:
    title = html.escape(headline or "信息图视频")
    return f"""<head>
<meta charset="UTF-8">
<meta name="viewport" content="width={settings.video_width}, height={settings.video_height}">
<title>{title}</title>
<script src="{gsap_src}"></script>
<style>
@font-face {{
  font-family: "Microsoft YaHei";
  src: local("Microsoft YaHei");
}}
@font-face {{
  font-family: "微软雅黑";
  src: local("微软雅黑");
}}
@font-face {{
  font-family: "PingFang SC";
  src: local("PingFang SC");
}}
body {{
  margin: 0;
  background: #0b0f14;
  font-family: "Microsoft YaHei", "微软雅黑", "PingFang SC", sans-serif;
}}
#root {{
  position: relative;
  width: {settings.video_width}px;
  height: {settings.video_height}px;
  overflow: hidden;
  background: #0b0f14;
}}
.clip {{ position: absolute; inset: 0; }}
.canvas {{ position: absolute; inset: 0; }}
.canvas-img {{ display: block; width: 100%; height: 100%; object-fit: contain; }}
.mask-layer {{ position: absolute; inset: 0; }}
.point-mask {{
  position: absolute;
  transform-origin: right center;
  will-change: transform;
}}
</style>
</head>"""


def _bbox_style(region: dict) -> str:
    bbox = region["bbox"]
    left = float(bbox["x1"]) * 100
    top = float(bbox["y1"]) * 100
    width = (float(bbox["x2"]) - float(bbox["x1"])) * 100
    height = (float(bbox["y2"]) - float(bbox["y1"])) * 100
    return (
        f"left:{_fmt(left)}%;top:{_fmt(top)}%;"
        f"width:{_fmt(width)}%;height:{_fmt(height)}%;"
    )


def _storyboard_section(timeline: dict, regions: list[dict], mask_color: str) -> str:
    masks: list[str] = []
    safe_color = html.escape(mask_color)
    for region in regions:
        pid = int(region["id"])
        style = _bbox_style(region)
        masks.append(
            f'    <div class="point-mask" id="mask-{pid}" '
            f'data-layout-allow-occlusion style="{style}background:{safe_color}"></div>'
        )

    return (
        f'<section id="storyboard" class="clip" data-start="0" '
        f'data-duration="{_fmt(timeline["total"])}" data-track-index="0">\n'
        '  <div class="canvas" id="canvas">\n'
        '    <img class="canvas-img" src="infographic.png" alt="">\n'
        '  </div>\n'
        '  <div class="mask-layer">\n'
        + "\n".join(masks)
        + "\n  </div>\n"
        + "</section>"
    )


def _timeline_script(timeline: dict, regions: list[dict]) -> str:
    """静态 JS + 注入 JSON 规格；所有时长与 data-* 属性同源。"""
    spec = {
        "intro": timeline["intro"],
        "outro": timeline["outro"],
        "transition": timeline["transition"],
        "point_duration": timeline["point_duration"],
        "points": [],
    }
    for region, point_tl in zip(regions, timeline["points"]):
        spec["points"].append(
            {
                "id": region["id"],
                "start": point_tl["start"],
                "duration": point_tl["duration"],
            }
        )
    spec_json = json.dumps(spec, ensure_ascii=False)
    return (
        "<script>\n"
        f"const SPEC = {spec_json};\n"
        + _TIMELINE_JS
        + "\n</script>"
    )


_TIMELINE_JS = """
const tl = gsap.timeline({ paused: true });
const trans = SPEC.transition;

tl.fromTo(
  "#canvas",
  { autoAlpha: 0 },
  { autoAlpha: 1, duration: 0.6, ease: "power2.out" },
  SPEC.intro.start + 0.1
);

for (const p of SPEC.points) {
  tl.fromTo(
    "#mask-" + p.id,
    { scaleX: 1 },
    { scaleX: 0, duration: trans, ease: "power2.inOut" },
    p.start
  );
}

window.__timelines["main"] = tl;
"""
