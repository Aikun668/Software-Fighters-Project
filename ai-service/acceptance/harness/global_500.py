"""全局 500 信封兜底存证（未跟踪 harness，不进 pytest）。

在**同一个 `main.app`** 上只切换「是否注册全局 Exception handler」这一个变量
（`exception_handlers.pop` + 重建 middleware_stack），其余一律不动，把四类端点
的响应字节并排打出来，证明：

1. 漏网 JSON 端点（无 try）—— before 是 `text/plain: Internal Server Error`，
   after 是标准 JSON 信封。这正是 D6 要补的真空白。
2. 未知路由 404 —— `HTTPException` 语义不得被全局兜底改写。
3. 参数校验 400 —— `RequestValidationError` 专属信封不得被改写。
4. SSE 成功路径 —— 媒体类型与事件序列不得被包成 JSON。

用法：python _accept_global_500.py
"""

import asyncio
import hashlib
import sys

import internal_api
import main
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

sys.stdout.reconfigure(encoding="utf-8")


class _RaisingStatusWorkflow:
    def __init__(self, exc: Exception):
        self._exc = exc

    def check_profile_status(self, student_profile):
        raise self._exc


class _OkWorkflow:
    async def run(self, state):
        return {"response": "画像正文", "profile_changed": False, "profile_complete": False}


class _patch:
    def __init__(self, attr, value):
        self.attr = attr
        self.value = value

    def __enter__(self):
        self.original = getattr(internal_api, self.attr)
        replacement = (lambda: self.value) if callable(self.original) else self.value
        setattr(internal_api, self.attr, replacement)
        return self

    def __exit__(self, *exc):
        setattr(internal_api, self.attr, self.original)
        return False


CASES = [
    ("unhandled_json_endpoint",
     ("POST", "/internal/profile/workflow/status", {"student_profile": {}}),
     [("_get_profile_workflow", _RaisingStatusWorkflow(RuntimeError("配置爆炸")))]),
    ("unknown_route_404",
     ("GET", "/internal/definitely-not-a-route", None), []),
    ("validation_error_400",
     ("POST", "/internal/api/chat", {}), []),
    ("sse_success_profile_chat",
     ("POST", "/internal/profile/chat",
      {"messages": [{"role": "user", "content": "我是谁"}], "user_id": 1}),
     [("_get_profile_workflow", _OkWorkflow())]),
]


def _toggle_global_handler(enabled: bool) -> None:
    """只改「全局 Exception handler 是否在册」这一件事，然后强制重建中间件栈。"""
    app: FastAPI = main.app
    if enabled:
        app.exception_handlers[Exception] = main.unhandled_exception_handler
    else:
        app.exception_handlers.pop(Exception, None)
    app.middleware_stack = None


async def _run(label: str) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=main.app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        for name, (method, path, payload), patches in CASES:
            patchers = [_patch(attr, value) for attr, value in patches]
            for p in patchers:
                p.__enter__()
            try:
                async with client.stream(method, path, json=payload) as resp:
                    chunks = [c async for c in resp.aiter_bytes()]
                    status = resp.status_code
                    ctype = resp.headers.get("content-type", "")
            finally:
                for p in reversed(patchers):
                    p.__exit__()

            body = b"".join(chunks)
            print(f"=== [{label}] case: {name} | {method} {path} ===")
            print(f"status={status}")
            print(f"content-type={ctype}")
            print(f"bytes={len(body)}")
            print(f"sha256={hashlib.sha256(body).hexdigest()}")
            print("--- raw begin ---")
            print(body.decode("utf-8", errors="replace"), end="")
            print("--- raw end ---")
            print()


async def main_() -> None:
    _toggle_global_handler(False)
    await _run("BEFORE")
    _toggle_global_handler(True)
    await _run("AFTER")


asyncio.run(main_())
