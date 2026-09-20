"""SSE 与安全守卫共享化契约测试（Task 1）。

本轮把两类公共设施从 `internal_api.py` 抽成共享模块：

- SSE 响应样板 → `app/utils/sse_response.py` 的 `sse_response()`
- SSRF 判定 / 导出路径守卫 → `app/utils/security_middleware.py` 的两个纯函数

**Part A（绿，Task 1 即通过）**：锁抽取**前**的现有行为。注入点全部选在
「抽取前后都存在」的符号上（`internal_api._get_xxx()` 工厂、`internal_api._EXPORTS_DIR`、
`internal_api._build_multimodal_message`），因此抽取时断言一字不改。

> 后续修订（多模态归位轮）：上句对 `_build_multimodal_message` 的承诺已到期 ——
> 该函数已迁至 `app.utils.multimodal.build_multimodal_message`（旧名从 `internal_api`
> 删除），本文件的引用点随之从 `internal_api._build_multimodal_message` 改为新模块，
> **断言一字未改**。迁移由 `tests/test_multimodal_utils_contract.py::MM-B03` 锁定。

**Part B（红，Task 2 / Task 4 落地后转绿）**：锁新共享模块自身的契约。

之所以先写这个文件：`AI_SERVICE_ARCHITECTURE_GUIDE.md` line 148 明确
「不要在没有契约测试前搬动 SSE、错误响应和安全校验；这些地方最容易出现
『接口没报错但前端坏了』」。

⚠️ 本文件不断言任何端点调用了 `sse_sanitize` —— 本轮它是「仅归位不接线」，
该状态由 Task 5 的 SSE-D17「未接线锁」负责，不在 Part A/B 里重复。
"""

import importlib
import json
import os

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from httpx import ASGITransport, AsyncClient

import internal_api
from app.events.types import content_event, done_event, error_event
from app.utils.multimodal import build_multimodal_message
from app.utils.sse_heartbeat import sse_heartbeat_generator


def _require(module_path: str, attr: str):
    """Task 2 / Task 4 落地前抛出可读的 RED 错误（而不是裸 ImportError）。"""
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise AssertionError(
            f"{module_path} 尚未创建 —— Task 2 / Task 4 未落地（{exc}）"
        ) from exc
    if not hasattr(module, attr):
        raise AssertionError(f"{module_path} 尚无 {attr} —— Task 2 / Task 4 未落地")
    return getattr(module, attr)


def _make_app() -> FastAPI:
    """与 main.py 相同的校验异常语义（400 + snake_case error_code）。"""
    app = FastAPI()

    @app.exception_handler(RequestValidationError)
    async def _handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        msg = errors[0]["msg"] if errors else "请求参数验证失败"
        loc = errors[0].get("loc", [])
        if loc:
            field = str(loc[-1]) if len(loc) > 1 else str(loc[0])
            msg = f"字段 '{field}' {msg}"
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": msg, "error_code": "INVALID_REQUEST"},
        )

    app.include_router(internal_api.router)
    return app


@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(
        transport=ASGITransport(app=_make_app()), base_url="http://test",
    ) as client:
        yield client


# ═══════════════════════════════════════════════════════════════════
# 替身
# ═══════════════════════════════════════════════════════════════════

class CenterStub:
    """任意方法名 → 返回预置事件序列的异步生成器（并记录调用参数）。

    覆盖 `stream_generate` / `stream_chat` / `generate_stream` / `solve_stream`
    四个同名不同类的入口——它们形状一致，无需各写一个替身。
    """

    def __init__(self, events, *, error=None):
        self._events = list(events)
        self._error = error
        self.calls: list[tuple[str, dict]] = []

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        async def _stream(**kwargs):
            self.calls.append((name, kwargs))
            for event in self._events:
                yield event
            if self._error is not None:
                raise self._error

        return _stream


class WorkflowStub:
    """`ProfileWorkflow` / `LearningPathWorkflow` 的 `run(state)` 替身。"""

    def __init__(self, state):
        self._state = dict(state)
        self.calls: list[dict] = []

    async def run(self, state):
        self.calls.append(state)
        return dict(self._state)


class InquiryStub:
    """`InquiryService.resolve()` 的同步替身。"""

    def __init__(self, resolved):
        self._resolved = dict(resolved)
        self.calls: list[tuple] = []

    def resolve(self, original_message, answers, **kwargs):
        self.calls.append((original_message, list(answers), kwargs))
        return dict(self._resolved)


RESOLVED = {
    "topic": "反向传播",
    "context_note": "用户已确认想深入数学推导",
    "suggested_types": ["document"],
}

OK_EVENTS = [content_event({"response": "这是正文"}), done_event({"summary": "ok"})]


def _install_profile_chat(monkeypatch):
    stub = WorkflowStub({
        "response": "画像正文", "profile_changed": False, "profile_complete": False,
    })
    monkeypatch.setattr(internal_api, "_get_profile_workflow", lambda: stub)
    return stub


def _install_resources_generate(monkeypatch):
    stub = CenterStub(OK_EVENTS)
    monkeypatch.setattr(internal_api, "_get_resource_center", lambda: stub)
    return stub


def _install_tutor_chat(monkeypatch):
    stub = CenterStub(OK_EVENTS)
    monkeypatch.setattr(internal_api, "_get_tutor_center", lambda: stub)
    return stub


def _install_exercise_generate(monkeypatch):
    stub = CenterStub(OK_EVENTS)
    monkeypatch.setattr(internal_api, "_get_exercise_center", lambda: stub)
    return stub


def _install_solve_question(monkeypatch):
    stub = CenterStub(OK_EVENTS)
    monkeypatch.setattr(internal_api, "_get_exercise_center", lambda: stub)
    return stub


def _install_unified_chat(monkeypatch):
    stub = CenterStub(OK_EVENTS)
    monkeypatch.setattr(internal_api, "_get_chat_center", lambda: stub)
    return stub


def _install_inquiry_resolve(monkeypatch):
    monkeypatch.setattr(internal_api, "_get_inquiry_service", lambda: InquiryStub(RESOLVED))
    resource = CenterStub(OK_EVENTS)
    monkeypatch.setattr(internal_api, "_get_resource_center", lambda: resource)
    return resource


def _install_inquiry_resolve_plan(monkeypatch):
    monkeypatch.setattr(internal_api, "_get_inquiry_service", lambda: InquiryStub(RESOLVED))
    stub = WorkflowStub({
        "steps": [{"title": "第一步"}, {"title": "第二步"}],
        "concept_graph": {"nodes": []},
        "response": "路径摘要",
    })
    monkeypatch.setattr(internal_api, "_get_path_workflow", lambda: stub)
    return stub


# 端点名 → (路径, 请求体, 装配函数)。8 个 SSE 端点逐一列出。
SSE_CASES = {
    "profile_chat": (
        "/internal/profile/chat",
        {"messages": [{"role": "user", "content": "我是谁"}], "user_id": 1},
        _install_profile_chat,
    ),
    "resources_generate": (
        "/internal/resources/generate",
        {"topic": "卷积神经网络", "user_id": 1},
        _install_resources_generate,
    ),
    "tutor_chat": (
        "/internal/tutor/chat",
        {"user_id": 1, "messages": [{"role": "user", "content": "什么是进程"}]},
        _install_tutor_chat,
    ),
    "exercise_generate": (
        "/internal/exercise/generate",
        {"topic": "反向传播", "user_id": 1},
        _install_exercise_generate,
    ),
    "solve_question": (
        "/internal/solve",
        {"question": "求导", "user_id": 1},
        _install_solve_question,
    ),
    "unified_chat": (
        "/internal/api/chat",
        {"message": "什么是过拟合", "user_id": 1, "mode": "auto"},
        _install_unified_chat,
    ),
    "inquiry_resolve": (
        "/internal/inquiry/resolve",
        {"original_message": "讲讲反向传播", "answers": ["要数学推导"], "user_id": 1},
        _install_inquiry_resolve,
    ),
    "inquiry_resolve_plan": (
        "/internal/inquiry/resolve/plan",
        {"original_message": "讲讲反向传播", "answers": ["要数学推导"], "user_id": 1},
        _install_inquiry_resolve_plan,
    ),
}

SSE_CASE_NAMES = list(SSE_CASES)

# 8 个端点的路由函数名（用于结构断言 / 防退化锁）
SSE_ROUTE_FUNCTIONS = [
    "profile_chat", "resources_generate", "tutor_chat", "exercise_generate",
    "solve_question", "_unified_chat", "inquiry_resolve", "inquiry_resolve_plan",
]


async def _raw_sse(client, path: str, payload: dict) -> tuple[int, str, str]:
    """打一个 SSE 端点，返回 (status, content_type, 原始响应文本)。"""
    async with client.stream("POST", path, json=payload) as resp:
        chunks = [chunk async for chunk in resp.aiter_text()]
        return resp.status_code, resp.headers.get("content-type", ""), "".join(chunks)


def _parse_events(raw: str) -> list[dict]:
    events = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line.startswith("data:"):
            continue
        body = line[5:].strip()
        if not body:
            continue
        try:
            events.append(json.loads(body))
        except json.JSONDecodeError:
            continue
    return events


# ═══════════════════════════════════════════════════════════════════
# Part A — 锁抽取前的现有行为（Task 1 即绿）
# ═══════════════════════════════════════════════════════════════════

class TestPartAContentType:
    """A01：8 个 SSE 端点的响应头与状态码。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("case_name", SSE_CASE_NAMES)
    async def test_a01_sse_endpoints_return_event_stream(
        self, async_client, monkeypatch, case_name,
    ):
        path, payload, install = SSE_CASES[case_name]
        install(monkeypatch)

        status, content_type, _ = await _raw_sse(async_client, path, payload)

        assert status == 200, case_name
        assert content_type.startswith("text/event-stream"), (case_name, content_type)


class TestPartAEventSequence:
    """A02：8 个端点的事件序列以唯一 done 收尾。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("case_name", SSE_CASE_NAMES)
    async def test_a02_each_endpoint_ends_with_single_done(
        self, async_client, monkeypatch, case_name,
    ):
        path, payload, install = SSE_CASES[case_name]
        install(monkeypatch)

        _, _, raw = await _raw_sse(async_client, path, payload)
        events = _parse_events(raw)
        types = [e.get("type") for e in events]

        assert events, f"{case_name} 未产生任何事件"
        assert types[-1] == "done", f"{case_name} 最后事件必须是 done，实际 {types}"
        assert types.count("done") == 1, f"{case_name} done 必须恰好一个，实际 {types}"


class TestPartAHeartbeat:
    """A03：短流不得被注入心跳注释。"""

    @pytest.mark.asyncio
    async def test_a03_short_stream_has_no_heartbeat(self, async_client, monkeypatch):
        path, payload, install = SSE_CASES["resources_generate"]
        install(monkeypatch)

        _, _, raw = await _raw_sse(async_client, path, payload)

        assert ":heartbeat" not in raw, f"短流不应出现心跳，实际响应体：\n{raw}"


class TestPartABoundaryTermination:
    """A04：内层生成器抛异常时，边界补发 error + 唯一 done。"""

    @pytest.mark.asyncio
    async def test_a04_inner_exception_yields_error_then_done(
        self, async_client, monkeypatch,
    ):
        stub = CenterStub([content_event({"response": "前半段"})],
                          error=RuntimeError("内部爆炸"))
        monkeypatch.setattr(internal_api, "_get_resource_center", lambda: stub)

        _, _, raw = await _raw_sse(
            async_client, "/internal/resources/generate",
            {"topic": "卷积", "user_id": 1},
        )
        types = [e.get("type") for e in _parse_events(raw)]

        assert "error" in types, f"内层异常必须补发 error，实际 {types}"
        assert types[-1] == "done", f"异常后仍必须以 done 收尾，实际 {types}"
        assert types.count("done") == 1, f"done 必须恰好一个，实际 {types}"


class TestPartADownloadGuards:
    """A05..A08：三个下载端点的路径守卫三档语义。"""

    @pytest.fixture(autouse=True)
    def _tmp_exports(self, tmp_path, monkeypatch):
        """把导出目录指向临时目录：守卫读的是模块级 `_EXPORTS_DIR`，抽取前后同一取值路径。"""
        monkeypatch.setattr(internal_api, "_EXPORTS_DIR", str(tmp_path))
        self.exports_dir = tmp_path
        return tmp_path

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route,ext,media_type", [
        ("/internal/resources/download-pptx", ".pptx",
         "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        ("/internal/resources/download-docx", ".docx",
         "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("/internal/resources/download-pdf", ".pdf", "application/pdf"),
    ])
    async def test_a05_existing_file_served(
        self, async_client, route, ext, media_type,
    ):
        name = f"export_1{ext}"
        (self.exports_dir / name).write_bytes(b"payload")

        resp = await async_client.get(route, params={"filename": name})

        assert resp.status_code == 200, (route, resp.text)
        assert resp.headers["content-type"].startswith(media_type)
        assert resp.content == b"payload"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route", [
        "/internal/resources/download-pptx",
        "/internal/resources/download-docx",
        "/internal/resources/download-pdf",
    ])
    async def test_a06_wrong_extension_maps_to_400(self, async_client, route):
        (self.exports_dir / "export_1.txt").write_bytes(b"x")

        resp = await async_client.get(route, params={"filename": "export_1.txt"})

        assert resp.status_code == 400, (route, resp.text)
        assert resp.json() == {
            "success": False, "errorCode": "INVALID_REQUEST", "error": "不支持的文件类型",
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route,ext", [
        ("/internal/resources/download-pptx", ".pptx"),
        ("/internal/resources/download-docx", ".docx"),
        ("/internal/resources/download-pdf", ".pdf"),
    ])
    async def test_a07_path_traversal_never_escapes_exports(self, async_client, route, ext):
        """穿越路径被 `basename` 抹平后落回 exports 内部，永远读不到外部文件。

        注意顺序：扩展名校验在路径校验之前，所以无扩展名的穿越串先撞上 400「不支持的文件类型」；
        带合法扩展名的穿越串则被抹平成 exports 内部的一个不存在的文件名，落 404。
        """
        no_ext = await async_client.get(
            route, params={"filename": "../../../etc/passwd"},
        )
        assert no_ext.status_code == 400, (route, no_ext.text)
        assert no_ext.json() == {
            "success": False, "errorCode": "INVALID_REQUEST", "error": "不支持的文件类型",
        }

        with_ext = await async_client.get(
            route, params={"filename": f"../../../../etc/shadow{ext}"},
        )
        assert with_ext.status_code == 404, (route, with_ext.text)
        assert with_ext.json() == {
            "success": False, "errorCode": "NOT_FOUND", "error": "文件不存在或已过期",
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route,ext", [
        ("/internal/resources/download-pptx", ".pptx"),
        ("/internal/resources/download-docx", ".docx"),
        ("/internal/resources/download-pdf", ".pdf"),
    ])
    async def test_a08_missing_file_maps_to_404(self, async_client, route, ext):
        resp = await async_client.get(route, params={"filename": f"ghost{ext}"})

        assert resp.status_code == 404, (route, resp.text)
        assert resp.json() == {
            "success": False, "errorCode": "NOT_FOUND", "error": "文件不存在或已过期",
        }

    @pytest.mark.asyncio
    async def test_a09_three_downloads_share_one_envelope(self, async_client):
        """同一个非法输入在三个端点上必须给出**完全相同**的错误信封。"""
        bodies = []
        for route in ("/internal/resources/download-pptx",
                      "/internal/resources/download-docx",
                      "/internal/resources/download-pdf"):
            resp = await async_client.get(
                route, params={"filename": "../../../etc/passwd"},
            )
            bodies.append((resp.status_code, resp.text))

        assert len(set(bodies)) == 1, f"三个端点响应不一致：{bodies}"


class TestPartASsrfGuard:
    """A10..A11：SSRF 判定行为（经 `build_multimodal_message` 锁定）。

    本类构造时该函数还在 `internal_api._build_multimodal_message`；后一轮的
    「多模态归位」把它搬到了 `app.utils.multimodal`，注入点随迁，**断言一字未改**。
    """

    SAMPLE = b"ZmFrZQ=="

    def _images_of(self, images):
        message = build_multimodal_message("描述", images)
        parts = message["content"]
        if isinstance(parts, str):
            return []
        return [
            p["image_url"]["url"]
            for p in parts
            if isinstance(p, dict) and p.get("type") == "image_url"
        ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("blocked", [
        "http://localhost/a.png",
        "http://127.0.0.1/a.png",
        "http://10.0.0.5/a.png",
        "http://192.168.1.1/a.png",
        "http://169.254.169.254/latest/meta-data",
        "http://2130706433/a.png",
        "http://0x7f000001/a.png",
        "http://017700000001/a.png",
    ])
    async def test_a10_internal_urls_are_dropped(self, blocked):
        assert self._images_of([blocked]) == [], blocked

    @pytest.mark.asyncio
    @pytest.mark.parametrize("allowed", [
        "https://example.com/a.png",
        "http://8.8.8.8/a.png",
        "data:image/png;base64,AAAA",
    ])
    async def test_a11_public_urls_and_data_uri_survive(self, allowed):
        assert self._images_of([allowed]) != [], allowed


class TestPartASanitizeLock:
    """A12..A13：消毒调用防退化锁（本轮不改调用方式，但要防止被删）。"""

    EXPECTED_SANITIZED_ROUTES = [
        "profile_chat", "resources_generate", "tutor_chat", "exercise_generate",
        "solve_question", "_unified_chat", "inquiry_resolve", "inquiry_resolve_plan",
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route_name", EXPECTED_SANITIZED_ROUTES)
    async def test_a12_route_still_calls_sanitize_model(self, route_name):
        import inspect

        source = inspect.getsource(getattr(internal_api, route_name))
        assert "sanitize_model(" in source, f"{route_name} 丢失了 sanitize_model 调用"

    @pytest.mark.asyncio
    async def test_a13_sanitize_model_import_path_unchanged(self):
        from app.utils.prompt_guard import sanitize_model

        assert callable(sanitize_model)
        assert internal_api.sanitize_model is sanitize_model


# ═══════════════════════════════════════════════════════════════════
# Part B — 新共享模块契约（Task 2 / Task 4 转绿）
# ═══════════════════════════════════════════════════════════════════

class TestPartBSseResponseFactory:

    @pytest.mark.asyncio
    async def test_b01_factory_importable_and_accepts_generator(self):
        sse_response = _require("app.utils.sse_response", "sse_response")

        async def stream():
            yield "data: {}\n\n"

        assert isinstance(sse_response(stream()), StreamingResponse)

    @pytest.mark.asyncio
    async def test_b02_factory_uses_event_stream_media_type(self):
        sse_response = _require("app.utils.sse_response", "sse_response")

        async def stream():
            yield "data: {}\n\n"

        assert sse_response(stream()).media_type == "text/event-stream"

    @pytest.mark.asyncio
    async def test_b03_factory_output_equals_manual_wrapping(self):
        """工厂输出与手工 `StreamingResponse(sse_heartbeat_generator(x))` 逐字相同。"""
        sse_response = _require("app.utils.sse_response", "sse_response")

        def _make():
            async def stream():
                yield content_event({"response": "正文"}).to_sse()
                yield done_event({"summary": "ok"}).to_sse()

            return stream()

        via_factory = [chunk async for chunk in sse_response(_make()).body_iterator]
        manual = [
            chunk async for chunk in StreamingResponse(
                sse_heartbeat_generator(_make()), media_type="text/event-stream",
            ).body_iterator
        ]

        assert via_factory == manual


class TestPartBSseSanitize:
    """B07：`sse_sanitize` 搬迁后行为逐字不变（本轮**不接线**）。"""

    SAMPLES = [
        ("正常文本", "正常文本"),
        ("第一段\n\n第二段", "第一段  第二段"),
        ("第一行\ndata: 伪造帧", "第一行 data: 伪造帧"),
        ("含回车\r文本", "含回车文本"),
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("raw,expected", SAMPLES)
    async def test_b07_sanitize_behaviour_unchanged(self, raw, expected):
        sse_sanitize = _require("app.utils.sse_response", "sse_sanitize")

        assert sse_sanitize(raw) == expected


class TestPartBSecurityHelpers:

    @pytest.mark.asyncio
    async def test_b04_is_internal_url_importable(self):
        is_internal_url = _require("app.utils.security_middleware", "is_internal_url")

        assert is_internal_url("http://127.0.0.1/a.png") is True
        assert is_internal_url("http://2130706433/a.png") is True
        assert is_internal_url("https://example.com/a.png") is False

    @pytest.mark.asyncio
    async def test_b05_safe_export_path_extension_and_missing_is(self, tmp_path):
        safe_export_path = _require("app.utils.security_middleware", "safe_export_path")
        exports = str(tmp_path)

        with pytest.raises(ValueError, match="不支持的文件类型"):
            safe_export_path("a.txt", allowed_ext=".pptx", exports_dir=exports)
        with pytest.raises(FileNotFoundError, match="文件不存在或已过期"):
            safe_export_path("ghost.pptx", allowed_ext=".pptx", exports_dir=exports)

    @pytest.mark.asyncio
    async def test_b05b_safe_export_path_rejects_symlink_escape(self, tmp_path):
        """「非法文件路径」是纵深防御分支，只有符号链接逃逸能触发。

        `basename` 已经挡住了纯文本穿越（见 A07），所以这条分支在正常路径下不可达；
        搬迁时如果写丢了它，只有本用例会红。
        """
        safe_export_path = _require("app.utils.security_middleware", "safe_export_path")
        exports = tmp_path / "exports"
        exports.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.pptx").write_bytes(b"secret")

        link = exports / "leak.pptx"
        try:
            os.symlink(outside / "secret.pptx", link)
        except (OSError, NotImplementedError):
            pytest.skip("当前平台不允许创建符号链接，无法触发该分支")

        with pytest.raises(ValueError, match="非法文件路径"):
            safe_export_path("leak.pptx", allowed_ext=".pptx", exports_dir=str(exports))

    @pytest.mark.asyncio
    async def test_b06_safe_export_path_returns_resolved_path(self, tmp_path):
        safe_export_path = _require("app.utils.security_middleware", "safe_export_path")
        target = tmp_path / "export_9.docx"
        target.write_bytes(b"doc")

        resolved = safe_export_path(
            "export_9.docx", allowed_ext=".docx", exports_dir=str(tmp_path),
        )

        assert os.path.basename(resolved) == "export_9.docx"
        assert os.path.realpath(resolved) == os.path.realpath(str(target))
        assert os.path.realpath(resolved).startswith(os.path.realpath(str(tmp_path)))
