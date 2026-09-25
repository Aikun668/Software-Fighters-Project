"""公共设施抽取原始存证 harness（未跟踪脚本，不进 pytest）。

同进程 ASGI 打**全部 8 个 SSE 端点** + 3 个下载守卫 + SSRF 判定，
把整段响应字节原样打印并附 byte 长度与 sha256，用于抽取前（Task 1）
与抽取后（Task 5）逐字节比对，证明「零行为变化」。

装配点全部选在抽取前后都存在的符号上：
`internal_api._get_xxx()` 工厂 / `internal_api._EXPORTS_DIR`。
多模态探针经 `app.utils.multimodal.build_multimodal_message`（多模态归位轮起的新位置）。

用法：python _accept_sse_all_endpoints.py > _accept_sse_all_before.txt
"""

import asyncio
import hashlib
import os
import sys
import tempfile

import internal_api
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from internal_api import router

from app.utils.multimodal import build_multimodal_message

sys.stdout.reconfigure(encoding="utf-8")


class _StubCenter:
    """任意方法名 → 预置事件序列的异步生成器（覆盖 stream_generate / stream_chat 等）。"""

    def __init__(self, events, error=None):
        self._events = list(events)
        self._error = error

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        async def _stream(**kwargs):
            for event in self._events:
                yield event
            if self._error is not None:
                raise self._error

        return _stream


class _StubWorkflow:
    def __init__(self, state):
        self._state = dict(state)

    async def run(self, state):
        return dict(self._state)


class _RaisingWorkflow:
    """`run()` 直接抛异常 —— 专门打 SSE 端点的 except 兜底路径。"""

    def __init__(self, exc):
        self._exc = exc

    async def run(self, state):
        raise self._exc


class _StubInquiry:
    def __init__(self, resolved):
        self._resolved = dict(resolved)

    def resolve(self, original_message, answers, **kwargs):
        return dict(self._resolved)


class _patch:
    """替换模块级符号；原值是工厂函数（`_get_xxx`）则包一层 lambda，原值是常量则直接赋值。"""

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


def _ok_events():
    from app.events.types import content_event, done_event

    return [content_event({"response": "这是正文"}), done_event({"summary": "ok"})]


RESOLVED = {
    "topic": "反向传播",
    "context_note": "用户已确认想深入数学推导",
    "suggested_types": ["document"],
}

EXPORTS_DIR = os.path.join(tempfile.gettempdir(), "_accept_sse_exports")
os.makedirs(EXPORTS_DIR, exist_ok=True)
for _name in ("export_1.pptx", "export_1.docx", "export_1.pdf"):
    with open(os.path.join(EXPORTS_DIR, _name), "wb") as _f:
        _f.write(b"payload")

# (case 名, (method, path, json 请求体或 None, query 参数或 None), [(attr, value), ...])
SSE_CASES = [
    ("profile_chat", ("POST", "/internal/profile/chat",
                      {"messages": [{"role": "user", "content": "我是谁"}], "user_id": 1}, None),
     [("_get_profile_workflow", _StubWorkflow({
         "response": "画像正文", "profile_changed": False, "profile_complete": False,
     }))]),
    ("resources_generate", ("POST", "/internal/resources/generate",
                            {"topic": "卷积神经网络", "user_id": 1}, None),
     [("_get_resource_center", _StubCenter(_ok_events()))]),
    ("tutor_chat", ("POST", "/internal/tutor/chat",
                    {"user_id": 1, "messages": [{"role": "user", "content": "什么是进程"}]}, None),
     [("_get_tutor_center", _StubCenter(_ok_events()))]),
    ("exercise_generate", ("POST", "/internal/exercise/generate",
                           {"topic": "反向传播", "user_id": 1}, None),
     [("_get_exercise_center", _StubCenter(_ok_events()))]),
    ("solve_question", ("POST", "/internal/solve",
                        {"question": "求导", "user_id": 1}, None),
     [("_get_exercise_center", _StubCenter(_ok_events()))]),
    ("unified_chat", ("POST", "/internal/api/chat",
                      {"message": "什么是过拟合", "user_id": 1, "mode": "auto"}, None),
     [("_get_chat_center", _StubCenter(_ok_events()))]),
    ("inquiry_resolve", ("POST", "/internal/inquiry/resolve",
                         {"original_message": "讲讲反向传播", "answers": ["要数学推导"],
                          "user_id": 1}, None),
     [("_get_inquiry_service", _StubInquiry(RESOLVED)),
      ("_get_resource_center", _StubCenter(_ok_events()))]),
    ("inquiry_resolve_plan", ("POST", "/internal/inquiry/resolve/plan",
                              {"original_message": "讲讲反向传播",
                               "answers": ["要数学推导"], "user_id": 1}, None),
     [("_get_inquiry_service", _StubInquiry(RESOLVED)),
      ("_get_path_workflow", _StubWorkflow({
          "steps": [{"title": "第一步"}, {"title": "第二步"}],
          "concept_graph": {"nodes": []},
          "response": "路径摘要",
      }))]),
    ("resources_generate_inner_error",
     ("POST", "/internal/resources/generate", {"topic": "卷积", "user_id": 1}, None),
     [("_get_resource_center",
       _StubCenter(_ok_events()[:1], error=RuntimeError("内部爆炸")))]),
    # 本端点自带的 except 兜底路径（错误帧 + done 帧），多模态归位轮的
    # 「SSE 错误帧改走事件工厂」用它做字节前后比对。
    ("profile_chat_inner_error",
     ("POST", "/internal/profile/chat",
      {"messages": [{"role": "user", "content": "我是谁"}], "user_id": 1}, None),
     [("_get_profile_workflow", _RaisingWorkflow(RuntimeError("画像爆炸")))]),
    ("inquiry_resolve_plan_inner_error",
     ("POST", "/internal/inquiry/resolve/plan",
      {"original_message": "讲讲反向传播", "answers": ["要数学推导"], "user_id": 1}, None),
     [("_get_inquiry_service", _StubInquiry(RESOLVED)),
      ("_get_path_workflow", _RaisingWorkflow(RuntimeError("路径爆炸")))]),
    ("download_pptx_ok", ("GET", "/internal/resources/download-pptx", None,
                          {"filename": "export_1.pptx"}),
     [("_EXPORTS_DIR", EXPORTS_DIR)]),
    ("download_docx_ok", ("GET", "/internal/resources/download-docx", None,
                          {"filename": "export_1.docx"}),
     [("_EXPORTS_DIR", EXPORTS_DIR)]),
    ("download_pdf_ok", ("GET", "/internal/resources/download-pdf", None,
                         {"filename": "export_1.pdf"}),
     [("_EXPORTS_DIR", EXPORTS_DIR)]),
    ("download_traversal_no_ext",
     ("GET", "/internal/resources/download-pptx", None, {"filename": "../../../etc/passwd"}),
     [("_EXPORTS_DIR", EXPORTS_DIR)]),
    ("download_traversal_with_ext",
     ("GET", "/internal/resources/download-pptx", None, {"filename": "../../../../etc/shadow.pptx"}),
     [("_EXPORTS_DIR", EXPORTS_DIR)]),
    ("download_wrong_ext",
     ("GET", "/internal/resources/download-pdf", None, {"filename": "export_1.pptx"}),
     [("_EXPORTS_DIR", EXPORTS_DIR)]),
    ("download_missing",
     ("GET", "/internal/resources/download-docx", None, {"filename": "ghost.docx"}),
     [("_EXPORTS_DIR", EXPORTS_DIR)]),
]


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _build_multimodal_probe() -> str:
    """SSRF 与 MIME 判定的字节化探针（经 `build_multimodal_message` 的公开产物）。"""
    lines = []
    probes = [
        "http://localhost/a.png",
        "http://127.0.0.1/a.png",
        "http://10.0.0.5/a.png",
        "http://169.254.169.254/latest/meta-data",
        "http://2130706433/a.png",
        "http://0x7f000001/a.png",
        "http://017700000001/a.png",
        "https://example.com/a.png",
        "data:image/png;base64,AAAA",
        "data:image/svg+xml;base64,AAAA",
        "rawbase64payload",
    ]
    for probe in probes:
        message = build_multimodal_message("描述", [probe])
        content = message["content"]
        if isinstance(content, str):
            kept = []
        else:
            kept = [p["image_url"]["url"] for p in content
                    if isinstance(p, dict) and p.get("type") == "image_url"]
        lines.append(f"  {probe!r} -> kept={kept}")
    return "\n".join(lines)


async def main() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_make_app()), base_url="http://test",
    ) as client:
        for name, request, patches in SSE_CASES:
            method, path, payload, params = request
            patchers = [_patch(attr, value) for attr, value in patches]
            for p in patchers:
                p.__enter__()
            try:
                async with client.stream(
                    method, path, json=payload, params=params,
                ) as resp:
                    chunks = [chunk async for chunk in resp.aiter_bytes()]
                    status = resp.status_code
                    content_type = resp.headers.get("content-type", "")
            finally:
                for p in reversed(patchers):
                    p.__exit__()

            body = b"".join(chunks)
            print(f"=== case: {name} | {method} {path} ===")
            print(f"status={status}")
            print(f"content-type={content_type}")
            print(f"bytes={len(body)}")
            print(f"sha256={hashlib.sha256(body).hexdigest()}")
            print("--- raw begin ---")
            print(body.decode("utf-8", errors="replace"), end="")
            print("--- raw end ---")
            print()

        print("=== case: ssrf_and_mime_probe ===")
        probe_text = _build_multimodal_probe()
        probe_bytes = probe_text.encode("utf-8")
        print(f"bytes={len(probe_bytes)}")
        print(f"sha256={hashlib.sha256(probe_bytes).hexdigest()}")
        print("--- raw begin ---")
        print(probe_text)
        print("--- raw end ---")
        print()


asyncio.run(main())
