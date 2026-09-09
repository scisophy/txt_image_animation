"""独立验证火山方舟 API Key；不导入 app 包，也不输出凭据。"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


def main() -> int:
    values = dotenv_values(ENV_PATH)
    api_key = (values.get("ARK_API_KEY") or "").strip()
    base_url = (values.get("ARK_BASE_URL") or DEFAULT_BASE_URL).strip()

    if not api_key:
        print("FAIL: .env 中未配置 ARK_API_KEY")
        return 2

    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        print("FAIL: ARK_BASE_URL 必须是有效的 HTTPS 地址")
        return 2

    ping_url = f"{parsed.scheme}://{parsed.netloc}/ping"
    try:
        response = httpx.get(
            ping_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        print(f"FAIL: 无法连接火山方舟：{type(exc).__name__}")
        return 3

    print(f"HTTP_STATUS={response.status_code}")
    if response.is_success:
        print("ARK_KEY_OK")
        return 0

    error_code = "unknown"
    error_message = "unknown"
    try:
        payload = response.json()
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        error_code = str(error.get("code", error_code))
        error_message = str(error.get("message", error_message))
    except (json.JSONDecodeError, ValueError):
        pass
    print(f"ARK_ERROR_CODE={error_code}")
    print(f"ARK_ERROR_MESSAGE={error_message}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
