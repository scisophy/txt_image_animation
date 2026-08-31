"""API 请求/响应模型。"""
from typing import Literal

from pydantic import BaseModel, Field


class CreateTaskRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000, description="用于生成信息图的原文")
    intro_duration: float = Field(default=2.0, ge=0.5, le=10)
    outro_duration: float = Field(default=2.0, ge=0.5, le=10)
    point_duration: float = Field(default=4.0, ge=2, le=15)
    transition_duration: float = Field(default=0.8, ge=0.2, le=3)


class RedoRequest(BaseModel):
    stage: Literal["plan", "image", "regions", "mask", "storyboard", "render"]
