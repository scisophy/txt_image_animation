"""冒烟验证：合成素材生成 composition 并真实调用 HyperFrames 渲染。"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image

from app.core import storyboard_html, video_exporter

WS = Path(tempfile.mkdtemp(prefix="hf_smoke_"))


def make_assets():
    img = Image.new("RGB", (2048, 1152), (24, 32, 48))
    colors = [(231, 76, 60), (46, 204, 113), (52, 152, 219), (241, 196, 15)]
    boxes = [(100, 100, 1000, 600), (1050, 100, 1950, 600), (100, 650, 1000, 1050), (1050, 650, 1950, 1050)]
    for color, box in zip(colors, boxes):
        overlay = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), color)
        img.paste(overlay, (box[0], box[1]))
    img.save(WS / "infographic.png")

    regions = []
    for i, box in enumerate(boxes, start=1):
        x1, y1, x2, y2 = box
        regions.append(
            {
                "id": i,
                "title": f"合成讲解点 {i}",
                "bbox": {
                    "x1": x1 / 2048,
                    "y1": y1 / 1152,
                    "x2": x2 / 2048,
                    "y2": y2 / 1152,
                },
            }
        )
    return {"color": "#182030", "rgb": [24, 32, 48], "regions": regions}


def main():
    print("workspace:", WS)
    mask = make_assets()
    storyboard_html.build_storyboard_html(
        WS, "冒烟测试信息图", mask,
        {"intro_duration": 2, "outro_duration": 2, "point_duration": 4, "transition_duration": 0.8},
    )
    video_exporter.lint_composition(WS)
    video_exporter.check_composition(WS)
    out = video_exporter.render_video(WS, fps=30)
    print("RENDER_OK:", out)


if __name__ == "__main__":
    main()
