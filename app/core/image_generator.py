"""阶段 1b：火山方舟 Seedream 生成整幅信息图并落盘。"""
import base64
import logging
from pathlib import Path

import httpx
from PIL import Image

from app.core.config import settings
from app.core.llm import api_retry, get_client

logger = logging.getLogger(__name__)

TARGET_RATIO = settings.video_width / settings.video_height  # 16:9


def _result_bytes(item) -> bytes:
    """兼容方舟图片接口返回的 base64 或临时 URL。"""
    b64 = getattr(item, "b64_json", None)
    if b64:
        return base64.b64decode(b64)
    url = getattr(item, "url", None)
    if url:
        response = httpx.get(url, timeout=300, follow_redirects=True)
        response.raise_for_status()
        return response.content
    raise RuntimeError("图片生成失败：响应中没有图像数据或下载地址")


@api_retry
def generate_infographic(prompt: str, out_path: Path) -> Path:

    client = get_client()
    logger.info(
        "调用 %s 生成信息图（%s，水印=%s）",
        settings.image_model,
        settings.image_size,
        settings.image_watermark,
    )
    result = client.images.generate(
        model=settings.image_model,
        prompt=prompt,
        size=settings.image_size,
        response_format="b64_json",
        extra_body={
            "watermark": settings.image_watermark,
            "sequential_image_generation": "disabled",
        },
    )
    if not result.data:
        raise RuntimeError("图片生成失败：响应中没有图像结果")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(_result_bytes(result.data[0]))
    crop_to_aspect_ratio(out_path)
    logger.info("信息图已保存：%s", out_path)
    return out_path


def crop_to_aspect_ratio(
    path: Path, ratio: float = TARGET_RATIO, tolerance: float = 0.005
) -> bool:
    """若图片不是目标宽高比（16:9），居中裁剪到该比例；已是则不动。"""
    with Image.open(path) as img:
        img = img.convert("RGB")
        width, height = img.size
        current = width / height
        if abs(current - ratio) <= tolerance:
            return False
        if current > ratio:  # 过宽：裁左右
            new_w = round(height * ratio)
            left = (width - new_w) // 2
            box = (left, 0, left + new_w, height)
        else:  # 过高：裁上下
            new_h = round(width / ratio)
            top = (height - new_h) // 2
            box = (0, top, width, top + new_h)
        img.crop(box).save(path)
        logger.info("素材非 16:9（%dx%d），已居中裁剪：%s", width, height, box)
        return True
