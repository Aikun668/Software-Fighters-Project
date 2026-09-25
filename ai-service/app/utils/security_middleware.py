"""安全中间件：速率限制 + 安全响应头 + 服务间认证 + 路径/URL 守卫"""

import os
import re
import time
import logging
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# ── SSRF 判定 ────────────────────────────────────────────────

_SSRF_BLOCKED_NETWORKS = re.compile(
    r"://(localhost|127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+|"
    r"0\.0\.0\.0|169\.254\.\d+\.\d+|\[::1\]|\[fe80:)",
    re.IGNORECASE,
)

_SSRF_DECIMAL_IP = re.compile(r"://(\d{8,10})(?:/|$|:)", re.IGNORECASE)
_SSRF_HEX_IP = re.compile(r"://0x[0-9a-f]{6,8}(?:/|$|:)", re.IGNORECASE)
_SSRF_OCTAL_IP = re.compile(r"://0[0-7]{9,11}(?:/|$|:)", re.IGNORECASE)


def is_internal_url(url: str) -> bool:
    """判断 URL 是否指向内网/本机/云元数据地址（SSRF 防护）。"""
    if _SSRF_BLOCKED_NETWORKS.search(url):
        return True
    dec_match = _SSRF_DECIMAL_IP.search(url)
    if dec_match:
        try:
            ip_int = int(dec_match.group(1))
            octets = [(ip_int >> 24) & 0xFF, (ip_int >> 16) & 0xFF, (ip_int >> 8) & 0xFF, ip_int & 0xFF]
            ip_str = ".".join(str(o) for o in octets)
            if _SSRF_BLOCKED_NETWORKS.search(f"://{ip_str}"):
                return True
        except (ValueError, OverflowError):
            pass
    if _SSRF_HEX_IP.search(url) or _SSRF_OCTAL_IP.search(url):
        return True
    return False


# ── 导出文件下载守卫 ─────────────────────────────────────────

def safe_export_path(filename: str, *, allowed_ext: str, exports_dir: str) -> str:
    """校验下载请求并返回可安全读取的绝对路径。

    `basename` 抹平一切目录成分后，再确认 realpath 未逃出导出目录——后者是
    针对符号链接的纵深防御（纯文本穿越已被 basename 挡住）。

    Raises:
        ValueError: 扩展名不符或路径逃出导出目录（调用方映射为 400）
        FileNotFoundError: 文件不存在或已过期（调用方映射为 404）
    """
    safe_name = os.path.basename(filename)
    if os.path.splitext(safe_name)[1].lower() != allowed_ext:
        raise ValueError("不支持的文件类型")
    file_path = os.path.join(exports_dir, safe_name)

    # 包含性判定：`startswith(root)` 会把**同前缀的兄弟目录**（`/x/exports_evil`）误判为内部，
    # 必须按路径段比较（`root + os.sep`）。等值分支覆盖「exports_dir 本身」这一不可能情况，
    # 只为让语义显式。（历轮登记的「导出路径包含性加固」）
    exports_root = os.path.realpath(exports_dir)
    resolved = os.path.realpath(file_path)
    if resolved != exports_root and not resolved.startswith(exports_root + os.sep):
        raise ValueError("非法文件路径")
    if not os.path.exists(file_path):
        raise FileNotFoundError("文件不存在或已过期")
    return file_path


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
