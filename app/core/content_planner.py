"""阶段 1a：GPT-5.6 Sol 完成内容理解、讲解点提炼与图片内容方案。"""
import json
import logging

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.llm import api_retry, get_client

logger = logging.getLogger(__name__)


class Point(BaseModel):
    id: int = Field(description="讲解点序号，从 1 开始连续递增")
    title: str = Field(description="讲解点标题，简短有力")
    bullets: list[str] = Field(description="该讲解点的正文要点，2-4 条")


class ContentPlan(BaseModel):
    headline: str = Field(description="整张信息图的主标题")
    points: list[Point] = Field(description="3-6 个讲解点，按叙事顺序排列")


PLAN_INSTRUCTIONS = """\
你是一名信息图内容策划。根据用户提供的原文，规划一张 16:9 横版信息图的内容方案：
1. 理解原文主旨，确定叙事重点；
2. 提炼 3-6 个讲解点，按逻辑顺序排列；
3. 为每个讲解点编写简短标题与 2-4 条正文要点；
4. 编写一个统摄全局的主标题。
标题与要点必须使用原文语言，忠实于原文，不得虚构事实。
"""


@api_retry
def plan_content(user_text: str) -> ContentPlan:
    client = get_client()
    response = client.responses.parse(
        model=settings.planner_model,
        reasoning={"effort": "medium"},
        instructions=PLAN_INSTRUCTIONS,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"请为以下内容规划信息图方案：\n\n{user_text}",
                    }
                ],
            }
        ],
        text_format=ContentPlan,
    )
    plan = response.output_parsed
    if plan is None or not plan.points:
        raise RuntimeError("内容规划失败：模型未返回有效讲解点")
    ids = [p.id for p in plan.points]
    if ids != list(range(1, len(plan.points) + 1)):
        for i, p in enumerate(plan.points, start=1):
            p.id = i
    return plan


def build_image_prompt(user_text: str, plan: ContentPlan) -> str:
    """图片 prompt 只包含用户内容、讲解点与整体目标，由图片模型自由设计。"""
    points_desc = "\n".join(
        f"- {p.title}：{'；'.join(p.bullets)}" for p in plan.points
    )
    return (
        f"请生成一张完整的 16:9 横版信息图。\n"
        f"主标题：{plan.headline}\n"
        f"讲解点：\n{points_desc}\n\n"
        f"原始内容：\n{user_text}"
    )


def plan_to_dict(plan: ContentPlan) -> dict:
    return json.loads(plan.model_dump_json())
