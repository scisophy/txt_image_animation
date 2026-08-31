import json
import subprocess
from pathlib import Path

import pytest

from app.core import (
    content_planner,
    mask_builder,
    region_detector,
    storyboard_html,
    video_exporter,
)


def test_plan_content_parses_and_renumbers(monkeypatch):
    class FakeResponses:
        def parse(self, **kwargs):
            class R:
                output_parsed = content_planner.ContentPlan(
                    headline="主标题",
                    points=[
                        content_planner.Point(id=7, title="A", bullets=["a1"]),
                        content_planner.Point(id=9, title="B", bullets=["b1", "b2"]),
                    ],
                )
            return R()

    class FakeClient:
        responses = FakeResponses()

    monkeypatch.setattr(content_planner, "get_client", lambda: FakeClient())
    plan = content_planner.plan_content("测试文本")
    assert [p.id for p in plan.points] == [1, 2]
    assert plan.headline == "主标题"


def test_build_image_prompt_contains_points():
    plan = content_planner.ContentPlan(
        headline="主标题",
        points=[content_planner.Point(id=1, title="要点一", bullets=["内容"])],
    )
    prompt = content_planner.build_image_prompt("原文", plan)
    assert "16:9" in prompt
    assert "要点一" in prompt
    assert "原文" in prompt


def test_region_validation_detects_mismatch():
    regions = region_detector.DetectedRegions(
        points=[
            region_detector.DetectedPoint(
                id=1, title="A", bbox=region_detector.BBox(x1=0.1, y1=0.1, x2=0.4, y2=0.4)
            )
        ]
    )
    region_detector._validate(regions, [1])
    with pytest.raises(region_detector.RegionValidationError):
        region_detector._validate(regions, [1, 2])
    with pytest.raises(region_detector.RegionValidationError):
        bad = region_detector.DetectedRegions(
            points=[
                region_detector.DetectedPoint(
                    id=1,
                    title="A",
                    bbox=region_detector.BBox(x1=0.4, y1=0.1, x2=0.1, y2=0.4),
                )
            ]
        )
        region_detector._validate(bad, [1])


def test_compute_timeline_total():
    params = {
        "intro_duration": 2,
        "outro_duration": 2,
        "point_duration": 4,
        "transition_duration": 0.8,
    }
    tl = storyboard_html.compute_timeline(params, 3)
    assert tl["total"] == pytest.approx(2 + 3 * 4 + 2)
    assert tl["points"][0]["start"] == pytest.approx(2)
    assert tl["points"][1]["start"] == pytest.approx(6)
    assert tl["points"][0]["duration"] == pytest.approx(4)
    assert tl["outro"]["start"] == pytest.approx(14)


def test_storyboard_html_contract(tmp_path):
    mask = {
        "color": "#f4f5f6",
        "rgb": [244, 245, 246],
        "regions": [
            {
                "id": 1,
                "title": "要点<一>",
                "bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.4, "y2": 0.6},
            },
            {
                "id": 2,
                "title": "要点二",
                "bbox": {"x1": 0.5, "y1": 0.2, "x2": 0.8, "y2": 0.6},
            },
        ],
    }
    out = storyboard_html.build_storyboard_html(
        tmp_path, "测试标题", mask, {"point_duration": 4, "transition_duration": 0.8}
    )
    text = out.read_text(encoding="utf-8")
    assert 'data-composition-id="main"' in text
    assert 'data-width="1920"' in text
    assert 'data-height="1080"' in text
    assert 'data-duration="12' in text  # 2 + 2*4 + 2
    assert 'window.__timelines["main"]' in text
    assert "gsap.timeline({ paused: true })" in text
    assert text.count('class="clip"') == 1  # 全片始终使用同一张完整信息图
    assert "title-bar" not in text  # 底部讲解标题条已移除
    assert "focus-frame" not in text  # 讲解区域蓝色边框已移除
    assert 'src="infographic.png"' in text
    assert 'id="mask-1"' in text
    assert "background:#f4f5f6" in text
    assert "{ scaleX: 1 }" in text
    assert "{ scaleX: 0, duration: trans" in text
    assert 'src: local("Microsoft YaHei")' in text  # 中文字体满足 lint


def test_dominant_background_color_uses_largest_color_cluster(tmp_path):
    from PIL import Image

    path = tmp_path / "background.png"
    image = Image.new("RGB", (100, 100), (246, 247, 248))
    for x in range(20):
        for y in range(100):
            image.putpixel((x, y), (20, 80, 180))
    image.save(path)

    rgb = mask_builder.dominant_background_color(path)
    assert all(abs(actual - expected) <= 2 for actual, expected in zip(rgb, (246, 247, 248)))
    assert mask_builder.rgb_to_hex(rgb).startswith("#")


def test_video_exporter_uses_local_pinned_cli(monkeypatch, tmp_path):
    cli = tmp_path / "hyperframes.mjs"
    cli.write_text("// test", encoding="utf-8")
    monkeypatch.setattr(video_exporter, "HYPERFRAMES_CLI", cli)
    monkeypatch.setattr(video_exporter, "_node", lambda: "node-test")

    assert video_exporter._command(["check"]) == ["node-test", str(cli), "check"]


def test_video_exporter_windows_flags_do_not_detach(monkeypatch):
    monkeypatch.setattr(video_exporter.os, "name", "nt")

    flags = video_exporter._creation_flags()

    assert flags & subprocess.CREATE_NO_WINDOW
    assert not flags & subprocess.DETACHED_PROCESS


def test_video_exporter_non_windows_has_no_creation_flags(monkeypatch):
    monkeypatch.setattr(video_exporter.os, "name", "posix")
    assert video_exporter._creation_flags() == 0
