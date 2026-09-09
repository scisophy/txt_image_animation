import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# 本项目以根目录 .env 为明确配置来源，避免 Windows 机器级旧变量覆盖当前任务配置。
load_dotenv(PROJECT_ROOT / ".env", override=True)


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    return int(_float(name, float(default)))


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    ark_api_key: str = field(default_factory=lambda: os.getenv("ARK_API_KEY", ""))
    ark_base_url: str = field(
        default_factory=lambda: os.getenv(
            "ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
        )
    )
    text_model: str = field(
        default_factory=lambda: os.getenv(
            "ARK_TEXT_MODEL", "doubao-seed-2-0-lite-260215"
        )
    )
    vision_model: str = field(
        default_factory=lambda: os.getenv(
            "ARK_VISION_MODEL", "doubao-seed-2-0-lite-260215"
        )
    )
    image_model: str = field(
        default_factory=lambda: os.getenv(
            "ARK_IMAGE_MODEL", "doubao-seedream-5-0-260128"
        )
    )
    image_size: str = field(
        default_factory=lambda: os.getenv("ARK_IMAGE_SIZE", "2560x1440")
    )
    image_watermark: bool = field(
        default_factory=lambda: _bool("ARK_IMAGE_WATERMARK", False)
    )

    output_dir: Path = PROJECT_ROOT / "output"
    assets_dir: Path = PROJECT_ROOT / "app" / "assets"

    video_width: int = 1920
    video_height: int = 1080
    video_fps: int = 30

    intro_duration: float = field(default_factory=lambda: _float("INTRO_DURATION", 2.0))
    outro_duration: float = field(default_factory=lambda: _float("OUTRO_DURATION", 2.0))
    point_duration: float = field(default_factory=lambda: _float("POINT_DURATION", 4.0))
    transition_duration: float = field(
        default_factory=lambda: _float("TRANSITION_DURATION", 0.8)
    )

    host: str = field(default_factory=lambda: os.getenv("SERVER_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _int("SERVER_PORT", 8000))


settings = Settings()
