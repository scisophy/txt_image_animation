import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


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


@dataclass
class Settings:
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    planner_model: str = field(
        default_factory=lambda: os.getenv("PLANNER_MODEL", "gpt-5.6-sol")
    )
    image_model: str = field(
        default_factory=lambda: os.getenv("IMAGE_MODEL", "gpt-image-2")
    )
    image_size: str = field(default_factory=lambda: os.getenv("IMAGE_SIZE", "2048x1152"))
    image_quality: str = field(
        default_factory=lambda: os.getenv("IMAGE_QUALITY", "high")
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
