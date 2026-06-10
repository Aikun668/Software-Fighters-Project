"""安全中间件：速率限制 + 安全响应头 + 服务间认证"""

import os
import time
import logging
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# ── 速率限制 ─────────────────────────────────────────────────

_RATE_LIMIT_WINDOW = 60       # 窗口秒数
_RATE_LIMIT_MAX = 120         # 每窗口最大请求数
_rate_buckets: dict[str, list[float]] = defaultdict(list)


def _clean_bucket(key: str, window: float) -> None:
    now = time.time()
    _rate_buckets[key] = [t for t in _rate_buckets[key] if now - t < window]


def _check_rate_limit(key: str) -> bool:
    now = time.time()
    _clean_bucket(key, _RATE_LIMIT_WINDOW)
    if len(_rate_buckets[key]) >= _RATE_LIMIT_MAX:
        return False
    _rate_buckets[key].append(now)
    return True


# ── 服务间认证 ───────────────────────────────────────────────

_SHARED_SECRET = os.getenv("AI_SERVICE_SHARED_SECRET", "")


def _verify_service_auth(request: Request) -> bool:
    if not _SHARED_SECRET:
        return True  # 未配置时不强制
    auth_header = request.headers.get("Authorization", "")
    expected = f"Bearer {_SHARED_SECRET}"
    return auth_header == expected


# ── 安全头 ───────────────────────────────────────────────────

_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "0",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cache-Control": "no-store, max-age=0",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class SecurityMiddleware(BaseHTTPMiddleware):
    """速率限制 + 服务间认证 + 安全响应头"""

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"

        # 服务间认证：仅 /internal/* 端点需要
        if request.url.path.startswith("/internal"):
            if not _verify_service_auth(request):
                return JSONResponse(
                    status_code=401,
                    content={"success": False, "errorCode": "UNAUTHORIZED", "error": "服务间认证失败"},
                )

        # 速率限制
        if not _check_rate_limit(client_ip):
            return JSONResponse(
                status_code=429,
                content={"success": False, "errorCode": "RATE_LIMITED", "error": "请求过于频繁，请稍后重试"},
            )

        response: Response = await call_next(request)

        # 添加安全响应头
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)

        return response
