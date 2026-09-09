"""阶段 2a：豆包视觉模型使用结构化输出返回归一化 bbox。"""
import base64
import json
import logging
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.llm import api_retry, get_client

logger = logging.getLogger(__name__)

Coord = Annotated[float, Field(ge=0.0, le=1.0)]


class BBox(BaseModel):
    x1: Coord
    y1: Coord
    x2: Coord
    y2: Coord


class DetectedPoint(BaseModel):
    id: int
    title: str
    bbox: BBox


class DetectedRegions(BaseModel):
    points: list[DetectedPoint]


class RegionValidationError(RuntimeError):
    pass


def detect_regions(infographic_path: Path, plan_points: list[dict]) -> DetectedRegions:
    """在自由布局信息图中定位每个讲解点的完整视觉区域。"""
    image_b64 = base64.b64encode(infographic_path.read_bytes()).decode("ascii")
    points_json = json.dumps(
        [{"id": p["id"], "title": p["title"]} for p in plan_points],
        ensure_ascii=False,
    )
    regions = _detect(image_b64, points_json)
    expected_ids = [p["id"] for p in plan_points]
    _validate(regions, expected_ids)
    return regions


@api_retry
def _detect(image_b64: str, points_json: str) -> DetectedRegions:
    client = get_client()
    response = client.responses.parse(
        model=settings.vision_model,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "根据给定讲解点，在这张自由布局信息图中定位每个讲解点的完整视觉区域。"
                            "每个 id 必须且只能返回一次；bbox 使用 0 到 1 的归一化坐标，"
                            "原点在左上角，并尽量包含该讲解点的标题、正文、图标和背景容器。\n"
                            f"讲解点：{points_json}"
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{image_b64}",
                    },
                ],
            }
        ],
        text_format=DetectedRegions,
    )
    regions = response.output_parsed
    if regions is None or not regions.points:
        raise RegionValidationError("区域检测失败：模型未返回任何区域")
    return regions


def _validate(regions: DetectedRegions, expected_ids: list[int]) -> None:
    got_ids = sorted(p.id for p in regions.points)
    if got_ids != sorted(expected_ids):
        raise RegionValidationError(
            f"区域检测结果与讲解点不对应：期望 {sorted(expected_ids)}，实际 {got_ids}"
        )
    if len(set(p.id for p in regions.points)) != len(regions.points):
        raise RegionValidationError("区域检测结果存在重复 id")
    for p in regions.points:
        b = p.bbox
        if b.x1 >= b.x2 or b.y1 >= b.y2:
            raise RegionValidationError(
                f"讲解点 {p.id} 的 bbox 坐标非法：({b.x1}, {b.y1}, {b.x2}, {b.y2})"
            )
