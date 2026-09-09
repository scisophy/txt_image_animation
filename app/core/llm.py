"""火山方舟 OpenAI 兼容客户端封装与限流重试。"""
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
        if not settings.ark_api_key:
            raise RuntimeError(
                "缺少 ARK_API_KEY：请复制 .env.example 为 .env 并填入火山方舟 API Key"
            )
        _client = OpenAI(
            api_key=settings.ark_api_key,
            base_url=settings.ark_base_url.rstrip("/"),
            timeout=300,
            max_retries=0,
        )
    return _client


RETRYABLE = (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)

# 对火山方舟的限流、连接错误、超时和服务端错误执行指数退避。
api_retry = retry(
    retry=retry_if_exception_type(RETRYABLE),
    wait=wait_exponential(multiplier=4, min=8, max=120),
    stop=stop_after_attempt(6),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
