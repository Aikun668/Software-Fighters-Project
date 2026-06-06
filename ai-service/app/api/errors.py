"""结构化错误响应系统

借鉴 OpenMAIC lib/server/api-response.ts — 12 种 ApiErrorCode 枚举 + 统一响应格式。
"""

from enum import Enum
from typing import Any

from fastapi.responses import JSONResponse


class ErrorCode(str, Enum):
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    INVALID_REQUEST = "INVALID_REQUEST"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    GENERATION_FAILED = "GENERATION_FAILED"
    PERSIST_FAILED = "PERSIST_FAILED"
    PARSE_FAILED = "PARSE_FAILED"
    CONTENT_UNSAFE = "CONTENT_UNSAFE"
    AGENT_TIMEOUT = "AGENT_TIMEOUT"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_ERROR_STATUS_MAP: dict[ErrorCode, int] = {
    ErrorCode.MISSING_REQUIRED_FIELD: 400,
    ErrorCode.INVALID_REQUEST: 400,
    ErrorCode.CONTENT_UNSAFE: 400,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.PARSE_FAILED: 422,
    ErrorCode.UPSTREAM_ERROR: 502,
    ErrorCode.AGENT_TIMEOUT: 504,
    ErrorCode.GENERATION_FAILED: 500,
    ErrorCode.PERSIST_FAILED: 500,
    ErrorCode.INTERNAL_ERROR: 500,
}


def api_error(
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
    status_code: int | None = None,
) -> JSONResponse:
    if status_code is None:
        status_code = _ERROR_STATUS_MAP.get(code, 500)
    body: dict[str, Any] = {
        "success": False,
        "errorCode": code.value,
        "error": message,
    }
    if details:
        body["details"] = details
    return JSONResponse(body, status_code=status_code)


def api_success(
    data: Any = None,
    status_code: int = 200,
) -> JSONResponse:
    body: dict[str, Any] = {"success": True}
    if data is not None:
        body["data"] = data
    return JSONResponse(body, status_code=status_code)
