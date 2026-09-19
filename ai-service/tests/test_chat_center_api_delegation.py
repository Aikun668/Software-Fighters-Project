"""ChatCenter API 委派同进程 ASGI 测试（Task 5）。

不调真实 LLM、真实 Center、真实 extract。验证：
- POST /internal/api/chat → _get_chat_center().stream_chat() 委派
- HTTP 200 + text/event-stream + 唯一 done
- token 流顺序保留
- 结构化产物（无 token）成功
- ResultAgent 异常 → error + 唯一 done
- 推荐抽取挂起不阻塞 done
- inspect.getsource(_unified_chat) 结构断言：API 无业务编排
"""

import asyncio
import inspect
import json
import time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import internal_api
from app.centers.chat_center import ChatCenter
from app.events.types import (
    StreamEvent,
    StreamEventType,
    content_event,
    done_event,
)


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════


def _token_event(chunk: str) -> StreamEvent:
    return StreamEvent(type=StreamEventType.TOKEN, data={"content": chunk})


class _StubResultAgent:
    """预置事件序列或抛错的 ResultAgent 替身。"""

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


async def _empty_extract(*args, **kwargs):
    return {"primary": [], "related": [], "broad": [], "all": []}


def _make_chat_center(events, *, error=None, extract=None, timeout=None) -> ChatCenter:
    """真实 ChatCenter + stub ResultAgent + stub extract，走真实 stream_chat。"""
    center = ChatCenter(result_agent=_StubResultAgent(events, error=error))
    center._extract_knowledge_nodes = extract or _empty_extract
    if timeout is not None:
        center._recommendation_timeout_sec = timeout
    return center


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(internal_api.router)
    return app


async def _collect_sse(response) -> list[dict]:
    """从 httpx response 中解析 SSE 文本为事件列表（忽略心跳注释行）。"""
    events: list[dict] = []
    buffer = ""
    async for chunk in response.aiter_text():
        buffer += chunk
        while "\n\n" in buffer:
            block, buffer = buffer.split("\n\n", 1)
            for line in block.split("\n"):
                if line.startswith("data: "):
                    payload = line[len("data: "):]
                    try:
                        events.append(json.loads(payload))
                    except json.JSONDecodeError:
                        pass
                    break
    return events


CHAT_OK = {"user_id": 7, "message": "什么是进程？", "mode": "auto"}


# ═══════════════════════════════════════════════════════════════
# TestChatCenterApiDelegation — /api/chat → stream_chat 委派
# ═══════════════════════════════════════════════════════════════


class TestChatCenterApiDelegation:
    @pytest.mark.asyncio
    async def test_api_chat_delegates_to_stream_chat_with_single_done(self):
        """POST /internal/api/chat → patch _get_chat_center → 委派 stream_chat，1 个 done。"""
        center = _make_chat_center(events=[
            content_event({"response": "进程是资源分配的基本单位"}),
            done_event({"summary": "ok"}),
        ])

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(internal_api, "_get_chat_center", lambda: center)
            async with AsyncClient(
                transport=ASGITransport(app=_make_app()),
                base_url="http://test",
            ) as client:
                response = await client.post("/internal/api/chat", json=CHAT_OK)

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        events = await _collect_sse(response)
        types = [e.get("type") for e in events]
        assert "content" in types
        assert types.count("done") == 1, f"done 必须恰好一个: {types}"
        assert types[-1] == "done"

    @pytest.mark.asyncio
    async def test_normal_chat_token_stream_order_preserved(self):
        """普通聊天 token 流顺序保留，done 唯一且最后。"""
        center = _make_chat_center(events=[
            _token_event("进"),
            _token_event("程"),
            _token_event("是"),
            done_event({"summary": "ok"}),
        ])

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(internal_api, "_get_chat_center", lambda: center)
            async with AsyncClient(
                transport=ASGITransport(app=_make_app()),
                base_url="http://test",
            ) as client:
                response = await client.post("/internal/api/chat", json=CHAT_OK)

        assert response.status_code == 200

        events = await _collect_sse(response)
        token_parts = [e.get("content") for e in events if e.get("type") == "token"]
        assert token_parts == ["进", "程", "是"], f"token 顺序被破坏: {token_parts}"
        types = [e.get("type") for e in events]
        assert types.count("done") == 1
        assert types[-1] == "done"

    @pytest.mark.asyncio
    async def test_structured_result_without_tokens_succeeds(self):
        """结构化产物（计划 steps，无 token）done 携带真实产物，不被误判空正文。"""
        center = _make_chat_center(events=[
            done_event({
                "steps": [{"title": "Python 基础语法"}, {"title": "项目实战"}],
                "total_steps": 2,
            }),
        ])

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(internal_api, "_get_chat_center", lambda: center)
            async with AsyncClient(
                transport=ASGITransport(app=_make_app()),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/internal/api/chat",
                    json={"user_id": 7, "message": "帮我制定 Python 学习计划", "mode": "auto"},
                )

        assert response.status_code == 200

        events = await _collect_sse(response)
        types = [e.get("type") for e in events]
        assert "error" not in types, f"结构化产物被误判空正文失败: {types}"
        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1
        assert done_events[0]["data"]["steps"] == [
            {"title": "Python 基础语法"}, {"title": "项目实战"},
        ]

    @pytest.mark.asyncio
    async def test_result_agent_exception_yields_error_then_single_done(self):
        """ResultAgent 异常 → error（前端可读 content）+ 唯一 done 收尾。"""
        center = _make_chat_center(
            events=[_token_event("前半段")],
            error=RuntimeError("Agent 内部爆炸"),
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(internal_api, "_get_chat_center", lambda: center)
            async with AsyncClient(
                transport=ASGITransport(app=_make_app()),
                base_url="http://test",
            ) as client:
                response = await client.post("/internal/api/chat", json=CHAT_OK)

        assert response.status_code == 200

        events = await _collect_sse(response)
        types = [e.get("type") for e in events]
        assert "error" in types, f"异常必须产生 error 事件: {types}"
        error = next(e for e in events if e.get("type") == "error")
        assert error.get("content"), "error 必须携带前端可读 content"
        assert types.count("done") == 1
        assert types[-1] == "done"

    @pytest.mark.asyncio
    async def test_done_arrives_when_recommendation_extraction_hangs(self):
        """推荐抽取挂起时 done 仍在超时预算内到达（页面不得永远转圈）。"""

        async def _hanging_extract(*args, **kwargs):
            await asyncio.Event().wait()  # 永不完成

        center = _make_chat_center(
            events=[
                content_event({"response": "回答正文"}),
                done_event({"summary": "ok"}),
            ],
            extract=_hanging_extract,
            timeout=0.5,
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(internal_api, "_get_chat_center", lambda: center)
            async with AsyncClient(
                transport=ASGITransport(app=_make_app()),
                base_url="http://test",
            ) as client:
                response = await client.post("/internal/api/chat", json=CHAT_OK)

        start = time.monotonic()
        events = await asyncio.wait_for(_collect_sse(response), timeout=15.0)
        elapsed = time.monotonic() - start

        types = [e.get("type") for e in events]
        assert types[-1] == "done", f"推荐抽取挂起时 done 必须是最后事件: {types}"
        assert elapsed < 10, f"done 被推荐抽取阻塞了 {elapsed:.1f}s"


# ═══════════════════════════════════════════════════════════════
# TestChatApiStructuralAssertions — API 源码结构断言
# ═══════════════════════════════════════════════════════════════


class TestChatApiStructuralAssertions:
    """_unified_chat 只做协议适配：不拥有聊天业务编排和终态拼装。"""

    @staticmethod
    def _route_source() -> str:
        return inspect.getsource(internal_api._unified_chat)

    def test_unified_chat_delegates_to_chat_center_stream_chat(self):
        source = self._route_source()
        assert "_get_chat_center" in source, "_unified_chat 未取 ChatCenter"
        assert "stream_chat" in source, "_unified_chat 未委派 stream_chat"
        assert "to_sse" in source, "_unified_chat 未做 SSE 序列化"
        assert "sse_response(" in source, "_unified_chat 未走共享 SSE 工厂（心跳包装在其中）"

    def test_unified_chat_has_no_business_orchestration(self):
        source = self._route_source()
        for forbidden in (
            "extract_knowledge_nodes",
            "RouterAgent",
            "ResultAgent",
            "RECOMMENDATION_EXTRACTION_TIMEOUT_SEC",
            "_done_payload_has_content",
            "assistant_content",
            "pending_done",
        ):
            assert forbidden not in source, f"_unified_chat 仍包含业务编排符号 {forbidden!r}"
