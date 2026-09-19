"""答疑域收口契约测试（Task 1）。

锁定 `/internal/tutor/chat` 的对外契约，作为 Task 3 API 收窄的兼容基线：

- TU-C01/C02: token 顺序与 4 字分片 + done 顶层 domain（整段 SSE 字节比对）
- TU-C03: response 为空（sanity 判失败）→ 无 token，直接 done，不是 error
- TU-C04: agent 异常 → error + done，无 token
- TU-C05/C06: profile_delta 仅在 changed=True 时出现在 done，且位于 token 之后
- TU-C07: 画像提取异常 → 静默降级，主回答不受影响
- TU-C08: response 为空时不调用 extract_and_merge
- TU-C09: messages 缺失 / 空列表 / 类型错误 → 400
- TU-C10: TutorCenter.stream_chat 事件序列与分片（Task 2 前 RED）
- TU-C11: TutorCenter 结构契约（async generator；不 import fastapi）
- TU-C12: token / error / done 三类帧 to_sse() 字节形状回归样本

Part A（TU-C01..C09）现在就是绿的：锁的是现状 API 行为。
Task 3 收窄后只允许改 patch 目标（`_get_tutor_agent` → `_get_tutor_center`），
断言一律不动 —— 这就是"字节零变化"的证明。
"""

import contextlib
import inspect
import json

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

import internal_api
from app.events.types import (
    StreamEventType,
    error_content_event,
    flat_done_event,
    token_event,
)
from internal_api import router

TUTOR_FAILED_MESSAGE = "答疑失败，请稍后重试"


def _make_app() -> FastAPI:
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

    app.include_router(router)
    return app


@pytest.fixture
def client():
    return TestClient(_make_app())


@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(
        transport=ASGITransport(app=_make_app()), base_url="http://test",
    ) as client:
        yield client


class _StubTutorAgent:
    def __init__(self, state: dict | None = None, *, error: Exception | None = None):
        self._state = state if state is not None else {"response": "", "domain": "ai"}
        self._error = error
        self.calls: list[dict] = []

    async def run(self, state: dict) -> dict:
        self.calls.append(state)
        if self._error is not None:
            raise self._error
        return self._state


class _StubProfileAgent:
    def __init__(
        self,
        *,
        changed: bool = False,
        profile: dict | None = None,
        error: Exception | None = None,
    ):
        self._changed = changed
        self._profile = profile if profile is not None else {}
        self._error = error
        self.calls: list[dict] = []

    async def extract_and_merge(self, profile_dict: dict, messages: list[dict]) -> dict:
        self.calls.append({"profile_dict": profile_dict, "messages": messages})
        if self._error is not None:
            raise self._error
        return {"changed": self._changed, "profile": self._profile}


@contextlib.contextmanager
def _stub_agents(tutor_agent, profile_agent=None):
    """替换 API 层 agent 工厂。

    Task 3 收窄后这里改为 patch `_get_tutor_center`（注入真实 TutorCenter +
    同一组 stub），上层断言不变。
    """
    profile_agent = profile_agent if profile_agent is not None else _StubProfileAgent()
    with contextlib.ExitStack() as stack:
        stack.enter_context(_patch_attr("_get_tutor_agent", lambda: tutor_agent))
        stack.enter_context(_patch_attr("_get_profile_agent", lambda: profile_agent))
        yield tutor_agent, profile_agent


@contextlib.contextmanager
def _patch_attr(name: str, value):
    original = getattr(internal_api, name)
    setattr(internal_api, name, value)
    try:
        yield
    finally:
        setattr(internal_api, name, original)


MESSAGES = [{"role": "user", "content": "1+1 等于几？"}]


def _token_line(chunk: str) -> str:
    return f'data: {{"type": "token", "content": {json.dumps(chunk, ensure_ascii=False)}}}\n\n'


# ═══════════════════════════════════════════════════════════════
# Part A: /internal/tutor/chat 现状字节契约（现在就绿）
# ═══════════════════════════════════════════════════════════════

class TestTutorChatEndpointContract:
    @pytest.mark.asyncio
    async def test_c01_c02_tokens_then_done_with_domain(self, async_client):
        agent = _StubTutorAgent({"response": "答案是 42。", "domain": "ai"})

        with _stub_agents(agent):
            response = await async_client.post(
                "/internal/tutor/chat",
                json={"user_id": 1, "messages": MESSAGES, "student_profile": {}},
            )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert response.text == (
            _token_line("答案是 ")
            + _token_line("42。")
            + 'data: {"type": "done", "domain": "ai"}\n\n'
        )

    @pytest.mark.asyncio
    async def test_c03_empty_response_yields_done_only(self, async_client):
        agent = _StubTutorAgent({"response": "", "domain": "general"})

        with _stub_agents(agent):
            response = await async_client.post(
                "/internal/tutor/chat",
                json={"user_id": 1, "messages": MESSAGES, "student_profile": {}},
            )

        assert response.text == 'data: {"type": "done", "domain": "general"}\n\n'

    @pytest.mark.asyncio
    async def test_c04_agent_error_yields_error_then_done(self, async_client):
        agent = _StubTutorAgent(error=RuntimeError("boom"))

        with _stub_agents(agent):
            response = await async_client.post(
                "/internal/tutor/chat",
                json={"user_id": 1, "messages": MESSAGES, "student_profile": {}},
            )

        assert response.text == (
            f'data: {{"type": "error", "content": "{TUTOR_FAILED_MESSAGE}"}}\n\n'
            + 'data: {"type": "done"}\n\n'
        )

    @pytest.mark.asyncio
    async def test_c05_profile_changed_adds_delta_after_tokens(self, async_client):
        agent = _StubTutorAgent({"response": "答案是 42。", "domain": "ai"})
        profile = _StubProfileAgent(changed=True, profile={"weak_points": ["积分"]})

        with _stub_agents(agent, profile):
            response = await async_client.post(
                "/internal/tutor/chat",
                json={"user_id": 1, "messages": MESSAGES,
                      "student_profile": {"knowledge_base": 50}},
            )

        assert response.text == (
            _token_line("答案是 ")
            + _token_line("42。")
            + 'data: {"type": "done", "domain": "ai", "profile_delta": {"weak_points": ["积分"]}}\n\n'
        )
        assert profile.calls[0]["profile_dict"] == {"knowledge_base": 50}
        assert profile.calls[0]["messages"] == MESSAGES

    @pytest.mark.asyncio
    async def test_c06_profile_unchanged_omits_delta(self, async_client):
        agent = _StubTutorAgent({"response": "好。", "domain": "ai"})
        profile = _StubProfileAgent(changed=False, profile={"weak_points": []})

        with _stub_agents(agent, profile):
            response = await async_client.post(
                "/internal/tutor/chat",
                json={"user_id": 1, "messages": MESSAGES, "student_profile": {}},
            )

        assert response.text == (
            _token_line("好。") + 'data: {"type": "done", "domain": "ai"}\n\n'
        )

    @pytest.mark.asyncio
    async def test_c07_profile_extract_error_degrades_silently(self, async_client):
        agent = _StubTutorAgent({"response": "答案是 42。", "domain": "ai"})
        profile = _StubProfileAgent(error=RuntimeError("profile boom"))

        with _stub_agents(agent, profile):
            response = await async_client.post(
                "/internal/tutor/chat",
                json={"user_id": 1, "messages": MESSAGES, "student_profile": {}},
            )

        assert response.status_code == 200
        assert response.text == (
            _token_line("答案是 ")
            + _token_line("42。")
            + 'data: {"type": "done", "domain": "ai"}\n\n'
        )

    @pytest.mark.asyncio
    async def test_c08_empty_response_skips_profile_extract(self, async_client):
        agent = _StubTutorAgent({"response": "", "domain": "ai"})
        profile = _StubProfileAgent(changed=True, profile={"weak_points": ["x"]})

        with _stub_agents(agent, profile):
            response = await async_client.post(
                "/internal/tutor/chat",
                json={"user_id": 1, "messages": MESSAGES, "student_profile": {}},
            )

        assert response.text == 'data: {"type": "done", "domain": "ai"}\n\n'
        assert profile.calls == []

    def test_c09_invalid_messages_rejected_with_400(self, client):
        missing = client.post("/internal/tutor/chat", json={"user_id": 1})
        empty = client.post(
            "/internal/tutor/chat", json={"user_id": 1, "messages": []},
        )
        wrong_type = client.post(
            "/internal/tutor/chat", json={"user_id": 1, "messages": "not list"},
        )

        for response in (missing, empty, wrong_type):
            assert response.status_code == 400
            assert response.json()["success"] is False


# ═══════════════════════════════════════════════════════════════
# Part B: TutorCenter.stream_chat 契约（Task 2 实现前 RED）
# ═══════════════════════════════════════════════════════════════

async def _collect(agen) -> list:
    return [event async for event in agen]


def _make_center(*, tutor_agent, profile_agent):
    from app.centers.tutor_center import TutorCenter

    center = TutorCenter(tutor_agent=tutor_agent, profile_agent=profile_agent)
    center.token_delay = 0.0
    center.chunk_size = 4
    return center


class TestTutorCenterStreamChat:
    @pytest.mark.asyncio
    async def test_c10_stream_chat_emits_tokens_then_done(self):
        agent = _StubTutorAgent({"response": "答案是 42。", "domain": "ai"})
        center = _make_center(tutor_agent=agent, profile_agent=_StubProfileAgent())

        events = await _collect(
            center.stream_chat(messages=MESSAGES, student_profile={}),
        )

        assert [e.type for e in events] == [
            StreamEventType.TOKEN, StreamEventType.TOKEN, StreamEventType.DONE,
        ]
        assert "".join(e.data["content"] for e in events
                       if e.type is StreamEventType.TOKEN) == "答案是 42。"
        assert events[-1].data == {"domain": "ai"}
        assert agent.calls[0] == {"messages": MESSAGES, "student_profile": {}}

    @pytest.mark.asyncio
    async def test_c10b_stream_chat_error_path(self):
        center = _make_center(
            tutor_agent=_StubTutorAgent(error=RuntimeError("boom")),
            profile_agent=_StubProfileAgent(),
        )

        events = await _collect(
            center.stream_chat(messages=MESSAGES, student_profile={}),
        )

        assert [e.type for e in events] == [StreamEventType.ERROR, StreamEventType.DONE]
        assert events[0].to_sse() == (
            f'data: {{"type": "error", "content": "{TUTOR_FAILED_MESSAGE}"}}\n\n'
        )
        assert events[1].to_sse() == 'data: {"type": "done"}\n\n'

    @pytest.mark.asyncio
    async def test_c10c_stream_chat_profile_delta_and_degrade(self):
        profile = _StubProfileAgent(changed=True, profile={"weak_points": ["积分"]})
        center = _make_center(
            tutor_agent=_StubTutorAgent({"response": "好。", "domain": "ai"}),
            profile_agent=profile,
        )
        events = await _collect(
            center.stream_chat(messages=MESSAGES, student_profile={"knowledge_base": 50}),
        )
        assert events[-1].data == {
            "domain": "ai", "profile_delta": {"weak_points": ["积分"]},
        }
        assert profile.calls[0]["profile_dict"] == {"knowledge_base": 50}

        broken = _make_center(
            tutor_agent=_StubTutorAgent({"response": "好。", "domain": "ai"}),
            profile_agent=_StubProfileAgent(error=RuntimeError("profile boom")),
        )
        events = await _collect(
            broken.stream_chat(messages=MESSAGES, student_profile={}),
        )
        assert events[-1].data == {"domain": "ai"}

    def test_c11_tutor_center_is_async_generator_without_http(self):
        from app.centers import tutor_center as module

        assert inspect.isasyncgenfunction(module.TutorCenter.stream_chat)
        source = inspect.getsource(module)
        assert "fastapi" not in source
        assert "StreamingResponse" not in source


# ═══════════════════════════════════════════════════════════════
# TU-C12: 三类帧 to_sse() 字节形状回归样本
# ═══════════════════════════════════════════════════════════════

class TestTutorEventFramesUnchanged:
    def test_c12_token_error_done_frames(self):
        assert token_event("答案是 ").to_sse() == _token_line("答案是 ")
        assert error_content_event(TUTOR_FAILED_MESSAGE).to_sse() == (
            f'data: {{"type": "error", "content": "{TUTOR_FAILED_MESSAGE}"}}\n\n'
        )
        assert flat_done_event({"domain": "ai"}).to_sse() == (
            'data: {"type": "done", "domain": "ai"}\n\n'
        )
        assert flat_done_event().to_sse() == 'data: {"type": "done"}\n\n'
