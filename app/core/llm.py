"""OpenAI client 封装与限流重试。"""
import logging

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise RuntimeError(
                "缺少 OPENAI_API_KEY：请复制 .env.example 为 .env 并填入 API Key"
            )
        _client = OpenAI(api_key=settings.openai_api_key, timeout=300, max_retries=0)
    return _client


RETRYABLE = (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)

# gpt-image-2 Tier 1 限流 5 张/分钟，指数退避等待额度恢复
api_retry = retry(
    retry=retry_if_exception_type(RETRYABLE),
    wait=wait_exponential(multiplier=4, min=8, max=120),
    stop=stop_after_attempt(6),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
