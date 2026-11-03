"""SSE 终止合同测试（Task 3 · P0）

合同（来自 archive/temp_file/9.5工程改造计划/2026-09-05-conversation-foundation-rescue.md Task 3）：
1. 成功请求：事件至少有一个 content，最后一个事件是 done。
2. Agent 异常：流以 error 或项目既有的明确终止语义结束，不得无限悬挂。
3. 非法请求：返回可识别错误，不进入 Agent 调度。
4. 终止责任唯一：无论内部发出多少 done、推荐抽取是否卡住，流的最后一个
   事件必须是恰好一个 done。
"""

import asyncio
import json
import time

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock

import internal_api
from app.centers.chat_center import ChatCenter
from app.events.types import content_event, done_event, error_event, inquiry_event
from app.utils.sse_heartbeat import sse_heartbeat_generator

pytestmark = pytest.mark.asyncio(loop_scope="function")


def _make_app() -> FastAPI:
    """与 main.py 相同的校验异常语义（400 + INVALID_REQUEST）。"""
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
async def sse_client():
    async with AsyncClient(transport=ASGITransport(app=_make_app()), base_url="http://test") as client:
        yield client


class _StubChatTaskDispatcher:
    """预置事件序列或抛错的 ChatTaskDispatcher 替身。"""

    def __init__(self, events=None, *, error=None):
        self._events = list(events or [])
        self._error = error

    async def execute(self, plan):
        for event in self._events:
            await asyncio.sleep(0)
            yield event
        if self._error is not None:
            await asyncio.sleep(0)
            raise self._error


class FakeChatCenter:
    """可编程的 ChatCenter 替身：预置事件序列或异常。

    Task 3 后 _unified_chat 委派 ChatCenter.stream_chat()；替身把 stream_chat
    委托给真实 ChatCenter（stub ChatTaskDispatcher + stub extract 注入），因此
    多 done 收敛 / 缺 done 兜底 / 错误补发等终态行为由真实实现承担，
    本文件只验证 API 边界（委派 + SSE 序列化 + 心跳包装）公开语义不变。
    """

    def __init__(self, events=None, error=None, route_error=None):
        import types

        self._events = events or []
        self._error = error
        self.route_calls: list[dict] = []

        real = ChatCenter(dispatcher=_StubChatTaskDispatcher(events, error=error))
        real._extract_knowledge_nodes = AsyncMock(return_value={"primary": []})
        real.route_calls = self.route_calls

        async def _fake_route(self, **kwargs):
            self.route_calls.append(kwargs)
            if route_error is not None:
                raise route_error
            from app.centers.schemas import ExecutionPlan

            return ExecutionPlan(tasks=[], is_clear=True, intent_meta={"strategy": "fake"})

        real.route = types.MethodType(_fake_route, real)
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)


def _install(center: FakeChatCenter, monkeypatch) -> None:
    monkeypatch.setattr(internal_api, "_chat_center_singleton", center)


async def _collect_sse(client, payload: dict) -> list[dict]:
    """消费 SSE 流，返回解析后的事件列表（忽略心跳注释行）。"""
    events: list[dict] = []
    async with client.stream("POST", "/internal/api/chat", json=payload) as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if not data_str:
                continue
            try:
                events.append(json.loads(data_str))
            except json.JSONDecodeError:
                continue
    return events


CHAT_OK = {"user_id": 1, "message": "什么是进程？", "mode": "auto"}


# ── 1. 成功合同 ──────────────────────────────────────────────

class TestSuccessContract:
    async def test_content_then_single_done_last(self, sse_client, monkeypatch):
        center = FakeChatCenter(events=[
            content_event({"response": "进程是资源分配的基本单位"}),
            done_event({"summary": "ok"}),
        ])
        _install(center, monkeypatch)

        events = await _collect_sse(sse_client, CHAT_OK)

        types = [e.get("type") for e in events]
        assert "content" in types, f"缺少 content 事件: {types}"
        assert types[-1] == "done", f"最后一个事件必须是 done，实际: {types}"
        assert types.count("done") == 1, f"done 必须恰好一个，实际: {types}"

    async def test_multiple_pipeline_done_collapsed_to_one(self, sse_client, monkeypatch):
        """内部 Agent 各自发 done 时，边界必须收敛为恰好一个 done。"""
        center = FakeChatCenter(events=[
            content_event({"response": "第一段"}),
            done_event({"summary": "任务1"}),
            done_event({"summary": "任务2"}),
        ])
        _install(center, monkeypatch)

        events = await _collect_sse(sse_client, CHAT_OK)

        types = [e.get("type") for e in events]
        assert types.count("done") == 1, f"多个内部 done 必须收敛为 1 个，实际: {types}"
        assert types[-1] == "done"


# ── 2. 异常终止合同 ──────────────────────────────────────────

class TestExceptionContract:
    async def test_error_event_exposes_frontend_readable_content(self, sse_client, monkeypatch):
        center = FakeChatCenter(events=[
            error_event("auto", "回答生成失败，请稍后再试"),
            done_event({"summary": "failed"}),
        ])
        _install(center, monkeypatch)

        events = await _collect_sse(sse_client, CHAT_OK)

        error = next(event for event in events if event.get("type") == "error")
        assert error["content"] == "回答生成失败，请稍后再试"

    async def test_empty_success_done_is_converted_to_error_before_done(self, sse_client, monkeypatch):
        center = FakeChatCenter(events=[done_event({"summary": "only metadata"})])
        _install(center, monkeypatch)

        events = await _collect_sse(sse_client, CHAT_OK)

        assert [event["type"] for event in events] == ["error", "done"]
        assert events[0]["content"] == "模型未返回有效内容，请重试"

    async def test_pipeline_exception_yields_error_then_done(self, sse_client, monkeypatch):
        center = FakeChatCenter(
            events=[content_event({"response": "前半段"})],
            error=RuntimeError("Agent 内部爆炸"),
        )
        _install(center, monkeypatch)

        events = await _collect_sse(sse_client, CHAT_OK)

        types = [e.get("type") for e in events]
        assert "error" in types, f"异常必须产生 error 事件: {types}"
        assert types[-1] == "done", f"异常后仍必须以 done 收尾: {types}"

    async def test_route_exception_returns_identifiable_error(self, monkeypatch):
        """route 阶段异常：HTTP 层可识别错误，不悬挂。"""
        from fastapi.testclient import TestClient

        center = FakeChatCenter(route_error=RuntimeError("路由爆炸"))
        monkeypatch.setattr(internal_api, "_chat_center_singleton", center)
        client = TestClient(_make_app(), raise_server_exceptions=False)

        resp = client.post("/internal/api/chat", json=CHAT_OK)
        assert resp.status_code >= 400, "route 异常必须返回错误状态码"


# ── 2b. 合法空正文模式不误报（终态合同边界） ────────────────

class TestLegitimateNoTextContentContract:
    async def test_inquiry_done_is_not_a_failure(self, sse_client, monkeypatch):
        """追问模式正文就是问题本身，done 载荷 is_clear=False 不得转 error。"""
        center = FakeChatCenter(events=[
            inquiry_event("你想了解什么？"),
            done_event({"type": "inquiry", "question": "你想了解什么？", "is_clear": False}),
        ])
        _install(center, monkeypatch)

        events = await _collect_sse(sse_client, CHAT_OK)

        types = [e.get("type") for e in events]
        assert "error" not in types, f"追问是合法产出，不得误报 error: {types}"
        assert types.count("done") == 1 and types[-1] == "done"

    async def test_resource_done_without_stream_text_is_success(self, sse_client, monkeypatch):
        """资源/习题模式正文随 done 载荷下发，无 token 流不算空正文失败。"""
        center = FakeChatCenter(events=[
            done_event({"content_blocks": [{"type": "course_doc", "heading": "卷积"}]}),
        ])
        _install(center, monkeypatch)

        events = await _collect_sse(sse_client, CHAT_OK)

        types = [e.get("type") for e in events]
        assert "error" not in types, f"资源模式无流式正文是正常的: {types}"
        assert types.count("done") == 1 and types[-1] == "done"

    async def test_done_with_error_field_surfaces_error_content(self, sse_client, monkeypatch):
        """done 载荷携带 error 时，必须先转成前端可读的 error 事件再收尾。"""
        center = FakeChatCenter(events=[done_event({"error": "资源生成失败，请稍后重试"})])
        _install(center, monkeypatch)

        events = await _collect_sse(sse_client, CHAT_OK)

        types = [e.get("type") for e in events]
        error = next(e for e in events if e.get("type") == "error")
        assert error["content"] == "资源生成失败，请稍后重试"
        assert types.count("done") == 1 and types[-1] == "done"

    async def test_missing_done_synthesized_exactly_once(self, sse_client, monkeypatch):
        """管线正常结束但没发 done 时，边界补发恰好一个 done。"""
        center = FakeChatCenter(events=[content_event({"response": "只有正文"})])
        _install(center, monkeypatch)

        events = await _collect_sse(sse_client, CHAT_OK)

        types = [e.get("type") for e in events]
        assert types.count("done") == 1, f"缺失 done 必须恰好补一个: {types}"
        assert types[-1] == "done"

    async def test_pipeline_error_event_without_done_converges(self, sse_client, monkeypatch):
        """管线发过 error 但未发 done：不得重复补 error，且必须以唯一 done 收尾。"""
        center = FakeChatCenter(events=[error_event("auto", "答疑失败")])
        _install(center, monkeypatch)

        events = await _collect_sse(sse_client, CHAT_OK)

        types = [e.get("type") for e in events]
        assert types.count("error") == 1, f"管线已发 error，不得重复: {types}"
        assert types.count("done") == 1 and types[-1] == "done"


# ── 3. 非法请求合同 ──────────────────────────────────────────

class TestInvalidRequestContract:
    async def test_missing_message_rejected_without_agent_dispatch(self, sse_client, monkeypatch):
        center = FakeChatCenter(events=[done_event()])
        _install(center, monkeypatch)

        resp = await sse_client.post("/internal/api/chat", json={"user_id": 1})

        assert resp.status_code == 400
        body = resp.json()
        assert body.get("error_code") == "INVALID_REQUEST"
        assert center.route_calls == [], "校验拒绝时不得进入 Agent 调度"

    async def test_empty_message_rejected(self, sse_client, monkeypatch):
        center = FakeChatCenter(events=[done_event()])
        _install(center, monkeypatch)

        resp = await sse_client.post("/internal/api/chat", json={"user_id": 1, "message": ""})

        assert resp.status_code == 400
        assert center.route_calls == []


# ── 4. 终止不被推荐抽取阻塞 ──────────────────────────────────

class TestTerminationNotBlocked:
    async def test_done_arrives_even_when_recommendation_extraction_hangs(
        self, sse_client, monkeypatch
    ):
        """推荐抽取卡死时，done 仍必须在超时预算内到达（页面不得永远转圈）。"""
        center = FakeChatCenter(events=[
            # 用 content 键：确保 assistant_content 累加命中、推荐抽取分支被执行
            content_event({"content": "回答正文"}),
            done_event({"summary": "ok"}),
        ])
        monkeypatch.setattr(internal_api, "_chat_center_singleton", center)

        async def _hanging_extraction(*args, **kwargs):
            await asyncio.Event().wait()  # 永不完成

        # Task 3 后抽取与超时预算都在 ChatCenter 内部
        center._real._extract_knowledge_nodes = _hanging_extraction
        center._real._recommendation_timeout_sec = 0.5

        start = time.monotonic()
        events = await asyncio.wait_for(
            _collect_sse(sse_client, CHAT_OK), timeout=15.0
        )
        elapsed = time.monotonic() - start

        types = [e.get("type") for e in events]
        assert types[-1] == "done", f"推荐抽取卡住时 done 仍必须是最后一个事件: {types}"
        assert elapsed < 10, f"done 被推荐抽取阻塞了 {elapsed:.1f}s"


# ── 5. 心跳包装器：边界终止责任 ─────────────────────────────

class TestHeartbeatBoundaryContract:
    async def _drain(self, inner):
        out = []
        async for item in sse_heartbeat_generator(inner, interval_sec=0.05):
            out.append(item)
        return out

    @staticmethod
    def _types(items: list[str]) -> list[str]:
        types = []
        for item in items:
            for line in item.split("\n"):
                if line.startswith("data:"):
                    try:
                        types.append(json.loads(line[5:].strip()).get("type"))
                    except json.JSONDecodeError:
                        pass
        return types

    async def test_inner_exception_still_ends_with_error_and_done(self):
        """内部生成器抛异常时，包装器必须补发 error + done，不得静默断流。"""
        async def inner():
            yield content_event({"response": "有内容"}).to_sse()
            raise RuntimeError("未捕获的内部异常")

        items = await asyncio.wait_for(self._drain(inner()), timeout=10.0)

        types = self._types(items)
        assert "error" in types, f"内部异常后必须补发 error 事件: {types}"
        assert types[-1] == "done", f"内部异常后必须以 done 收尾: {types}"

    async def test_inner_without_done_gets_synthetic_done(self):
        """内部生成器正常结束但没发 done 时，包装器补发唯一 done。"""
        async def inner():
            yield content_event({"response": "只有内容"}).to_sse()

        items = await asyncio.wait_for(self._drain(inner()), timeout=10.0)

        types = self._types(items)
        assert types.count("done") == 1, f"必须补发恰好一个 done: {types}"
        assert types[-1] == "done"

    async def test_inner_with_done_not_duplicated(self):
        """内部已发 done 时，包装器不得追加第二个 done。"""
        async def inner():
            yield content_event({"response": "内容"}).to_sse()
            yield done_event().to_sse()

        items = await asyncio.wait_for(self._drain(inner()), timeout=10.0)

        types = self._types(items)
        assert types.count("done") == 1
