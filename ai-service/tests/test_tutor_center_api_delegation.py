"""答疑域收口同进程 ASGI 委派测试（Task 4）。

用 httpx ASGITransport 起同进程 HTTP/SSE，验证收窄后的真实链路：

- TU-A01: POST /internal/tutor/chat → _get_tutor_center →
  TutorCenter.stream_chat → event.to_sse()，恰好一次委派、恰好一个 done
- TU-A02: 普通聊天 token 流逐字节形状 + 顶层 domain
- TU-A03: profile_delta 仅在 changed=True 时出现在 done
- TU-A04: agent 异常 → error + 唯一 done，无 token
- TU-A05: 画像提取异常 → 静默降级，主回答与 done 不受影响
- TU-A06: inspect.getsource 结构断言 —— 路由内不构造 Agent、不做分片、
  不手写 SSE、不直接取 Agent 工厂

不调真实 LLM：注入替身 Agent，其余（API 层、TutorCenter、事件序列化）都走真实代码。
"""

import inspect
import json
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

import internal_api
from app.centers.tutor_center import TutorCenter
from internal_api import router

TUTOR_FAILED_MESSAGE = "答疑失败，请稍后重试"

MESSAGES = [{"role": "user", "content": "1+1 等于几？"}]


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


def _stub_center(
    *,
    tutor_state: dict | None = None,
    tutor_error: Exception | None = None,
    profile_agent=None,
) -> TutorCenter:
    center = TutorCenter(
        tutor_agent=_StubTutorAgent(tutor_state, error=tutor_error),
        profile_agent=profile_agent if profile_agent is not None else _StubProfileAgent(),
    )
    center.token_delay = 0.0
    center.chunk_size = 4
    return center


def _token_line(chunk: str) -> str:
    return f'data: {{"type": "token", "content": {json.dumps(chunk, ensure_ascii=False)}}}\n\n'


async def _post(client, body: dict | None = None):
    return await client.post(
        "/internal/tutor/chat",
        json=body if body is not None else {
            "user_id": 1, "messages": MESSAGES, "student_profile": {},
        },
    )


# ═══════════════════════════════════════════════════════════════
# TU-A01: 委派事实
# ═══════════════════════════════════════════════════════════════

class _SpyCenter:
    """记录 stream_chat 调用参数，再转交真实 Center。"""

    def __init__(self, center: TutorCenter):
        self._center = center
        self.calls: list[dict] = []

    def stream_chat(self, **kwargs):
        self.calls.append(kwargs)
        return self._center.stream_chat(**kwargs)


class TestDelegation:
    @pytest.mark.asyncio
    async def test_a01_request_delegates_once_to_stream_chat(self, async_client):
        center = _stub_center(tutor_state={"response": "答案是 42。", "domain": "ai"})
        spy = _SpyCenter(center)

        with patch("internal_api._get_tutor_center", return_value=spy):
            response = await _post(async_client)

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert spy.calls == [{"messages": MESSAGES, "student_profile": {}}]
        assert center.tutor_agent.calls == [
            {"messages": MESSAGES, "student_profile": {}},
        ]
        assert response.text.count('"type": "done"') == 1


# ═══════════════════════════════════════════════════════════════
# TU-A02 / A03: 成功路径字节形状
# ═══════════════════════════════════════════════════════════════

class TestSuccessPath:
    @pytest.mark.asyncio
    async def test_a02_tokens_then_single_done_with_domain(self, async_client):
        center = _stub_center(tutor_state={"response": "答案是 42。", "domain": "ai"})

        with patch("internal_api._get_tutor_center", return_value=center):
            response = await _post(async_client)

        assert response.text == (
            _token_line("答案是 ")
            + _token_line("42。")
            + 'data: {"type": "done", "domain": "ai"}\n\n'
        )

    @pytest.mark.asyncio
    async def test_a03_profile_delta_lands_in_done(self, async_client):
        profile = _StubProfileAgent(changed=True, profile={"weak_points": ["积分"]})
        center = _stub_center(
            tutor_state={"response": "好。", "domain": "ai"}, profile_agent=profile,
        )

        with patch("internal_api._get_tutor_center", return_value=center):
            response = await _post(async_client, {
                "user_id": 1, "messages": MESSAGES,
                "student_profile": {"knowledge_base": 50},
            })

        assert response.text == (
            _token_line("好。")
            + 'data: {"type": "done", "domain": "ai", "profile_delta": {"weak_points": ["积分"]}}\n\n'
        )
        assert profile.calls[0]["profile_dict"] == {"knowledge_base": 50}


# ═══════════════════════════════════════════════════════════════
# TU-A04 / A05: 失败与降级路径
# ═══════════════════════════════════════════════════════════════

class TestFailureAndDegrade:
    @pytest.mark.asyncio
    async def test_a04_agent_error_yields_error_then_done(self, async_client):
        center = _stub_center(tutor_error=RuntimeError("boom"))

        with patch("internal_api._get_tutor_center", return_value=center):
            response = await _post(async_client)

        assert response.status_code == 200
        assert response.text == (
            f'data: {{"type": "error", "content": "{TUTOR_FAILED_MESSAGE}"}}\n\n'
            + 'data: {"type": "done"}\n\n'
        )
        assert "token" not in response.text

    @pytest.mark.asyncio
    async def test_a05_profile_extract_error_degrades_silently(self, async_client):
        center = _stub_center(
            tutor_state={"response": "答案是 42。", "domain": "ai"},
            profile_agent=_StubProfileAgent(error=RuntimeError("profile boom")),
        )

        with patch("internal_api._get_tutor_center", return_value=center):
            response = await _post(async_client)

        assert response.status_code == 200
        assert response.text == (
            _token_line("答案是 ")
            + _token_line("42。")
            + 'data: {"type": "done", "domain": "ai"}\n\n'
        )
        assert "profile_delta" not in response.text


# ═══════════════════════════════════════════════════════════════
# TU-A06: 路由源码结构断言
# ═══════════════════════════════════════════════════════════════

_FORBIDDEN_SYMBOLS = [
    "TutorAgent(",
    "ProfileAgent(",
    "extract_and_merge",
    "_sse_stream_chunks(",
    "json.dumps(",
    "_get_tutor_agent",
    "_get_profile_agent",
    "asyncio.sleep",
]


class TestRouteSourceStructure:
    def test_a06_route_has_no_business_symbols(self):
        source = inspect.getsource(internal_api.tutor_chat)
        for symbol in _FORBIDDEN_SYMBOLS:
            assert symbol not in source, f"tutor_chat 仍含 {symbol}"

    def test_a06_route_delegates_to_tutor_center_factory(self):
        source = inspect.getsource(internal_api.tutor_chat)
        assert "_get_tutor_center()" in source
        assert "event.to_sse()" in source

    def test_a06_center_factory_injects_agent_singletons(self):
        """唯一装配点：Center 必须注入既有 Agent 单例，不得走 Center 的默认装配。"""
        source = inspect.getsource(internal_api._get_tutor_center)
        assert "_get_tutor_agent()" in source
        assert "_get_profile_agent()" in source
