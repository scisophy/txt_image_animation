"""阶段 2b：统计信息图主背景色并生成顺序揭示遮罩规格。"""
from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

from PIL import Image

from app.core.region_detector import DetectedRegions

logger = logging.getLogger(__name__)


def dominant_background_color(
    image_path: Path,
    *,
    max_sample_size: int = 512,
    bucket_size: int = 16,
) -> tuple[int, int, int]:
    """返回图片中像素数量最多的颜色簇的平均 RGB。

    生成图常带有轻微渐变和压缩噪声，直接统计精确 RGB 会把同一背景拆散。
    因此先按每通道 ``bucket_size`` 聚类，再对最大颜色簇取原始像素均值。
    """
    if bucket_size <= 0 or bucket_size > 256:
        raise ValueError("bucket_size 必须在 1 到 256 之间")

    with Image.open(image_path) as source:
        image = source.convert("RGB")
        image.thumbnail((max_sample_size, max_sample_size), Image.Resampling.LANCZOS)
        pixels = list(image.get_flattened_data())

    if not pixels:
        raise RuntimeError("无法统计背景色：图片没有像素")

    def bucket(pixel: tuple[int, int, int]) -> tuple[int, int, int]:
        return tuple(channel // bucket_size for channel in pixel)

    dominant_bucket, _ = Counter(bucket(pixel) for pixel in pixels).most_common(1)[0]
    members = [pixel for pixel in pixels if bucket(pixel) == dominant_bucket]
    rgb = tuple(round(sum(pixel[i] for pixel in members) / len(members)) for i in range(3))
    logger.info("信息图主背景色：rgb%s（样本 %d 像素）", rgb, len(members))
    return rgb


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{channel:02x}" for channel in rgb)


def build_mask_spec(
    infographic_path: Path,
    regions: DetectedRegions,
) -> dict:
    """生成前端预览与 HyperFrames 共用的遮罩规格。"""
    rgb = dominant_background_color(infographic_path)
    points = [point.model_dump() for point in sorted(regions.points, key=lambda p: p.id)]
    return {
        "color": rgb_to_hex(rgb),
        "rgb": list(rgb),
        "regions": points,
    }
