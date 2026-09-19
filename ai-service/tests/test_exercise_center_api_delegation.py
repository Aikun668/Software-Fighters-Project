"""练习域收口同进程 ASGI 委派测试（Task 5）。

用 httpx ASGITransport 起同进程 HTTP/SSE，验证收口后的真实链路：

- EX-A01/A02: POST /internal/exercise/generate → _get_exercise_center →
  ExerciseCenter.generate_stream → event.to_sse()，done 顶层 questions
- EX-A03/A04: POST /internal/solve 事件顺序与失败路径
- EX-A05: 6 个 JSON 端点的响应包装与 400 分支不变
- EX-A06: inspect.getsource 结构断言 —— 路由内不构造 Agent、不加载 prompt、
  不直接调 llm、不手写 SSE

不调真实 LLM：注入替身 Agent / 替身 LLM，其余（API 层、Center、序列化、
纯计算 Service）都走真实代码。
"""

import inspect
import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

import internal_api
from app.centers.exercise_center import ExerciseCenter
from internal_api import router


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


def _parse_sse(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


class _StubAgent:
    def __init__(self, state: dict | None = None, *, error: Exception | None = None):
        self._state = state if state is not None else {}
        self._error = error
        self.calls: list[dict] = []

    async def run(self, state: dict) -> dict:
        self.calls.append(state)
        if self._error is not None:
            raise self._error
        return self._state


class _StubLLM:
    def __init__(self, reply: str):
        self._reply = reply
        self.calls: list[dict] = []

    async def chat(self, messages, system_prompt=None, **kwargs) -> str:
        self.calls.append({"messages": messages, "system_prompt": system_prompt})
        return self._reply


def _stub_center(
    *,
    exercise_state: dict | None = None,
    solve_state: dict | None = None,
    exercise_error: Exception | None = None,
    solve_error: Exception | None = None,
    llm=None,
) -> ExerciseCenter:
    center = ExerciseCenter(
        exercise_agent=_StubAgent(exercise_state, error=exercise_error),
        solve_agent=_StubAgent(solve_state, error=solve_error),
        llm_service=llm,
    )
    center.plan_progress_delay = 0.0
    center.generate_progress_delay = 0.0
    center.token_delay = 0.0
    return center


# ═══════════════════════════════════════════════════════════════
# EX-A01 / A02: /exercise/generate
# ═══════════════════════════════════════════════════════════════

class TestGenerateDelegation:
    @pytest.mark.asyncio
    async def test_a01_a02_generate_stream_delegates_with_top_level_questions(self, async_client):
        questions = [{"question": "1+1=?", "type": "choice"}]
        center = _stub_center(exercise_state={"questions": questions})

        with patch("internal_api._get_exercise_center", return_value=center):
            response = await async_client.post(
                "/internal/exercise/generate",
                json={
                    "topic": "TCP", "count": 1, "strategy": "review",
                    "difficulty": "medium", "student_profile": {},
                },
            )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        events = _parse_sse(response.text)
        assert [e["type"] for e in events] == ["progress", "progress", "done"]
        assert events[0] == {
            "type": "progress", "stage": "plan",
            "content": "正在规划「TCP」的练习题...",
        }
        assert events[1] == {
            "type": "progress", "stage": "generate", "content": "已生成 1 道题目",
        }
        assert events[2] == {"type": "done", "questions": questions}
        assert "data" not in events[2]

    @pytest.mark.asyncio
    async def test_a04_generate_failure_keeps_progress_error_done(self, async_client):
        center = _stub_center(exercise_error=RuntimeError("boom"))

        with patch("internal_api._get_exercise_center", return_value=center):
            response = await async_client.post(
                "/internal/exercise/generate",
                json={"topic": "TCP", "count": 1},
            )

        events = _parse_sse(response.text)
        assert [e["type"] for e in events] == ["progress", "error", "done"]
        assert events[1] == {"type": "error", "content": "题目生成失败，请稍后重试"}
        assert events[2] == {"type": "done"}


# ═══════════════════════════════════════════════════════════════
# EX-A03 / A04: /solve
# ═══════════════════════════════════════════════════════════════

class TestSolveDelegation:
    @pytest.mark.asyncio
    async def test_a03_solve_stream_delegates_in_order(self, async_client):
        center = _stub_center(solve_state={
            "steps": [{"order": 1, "description": "移项"}],
            "solution": "答案是 42",
            "confidence_score": 0.9,
        })

        with patch("internal_api._get_exercise_center", return_value=center):
            response = await async_client.post(
                "/internal/solve",
                json={"question": "1+1=?", "context": ""},
            )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        events = _parse_sse(response.text)
        assert [e["type"] for e in events] == [
            "steps", "token", "token", "confidence", "done",
        ]
        assert events[0]["content"] == [{"order": 1, "description": "移项"}]
        assert "".join(e["content"] for e in events if e["type"] == "token") == "答案是 42"
        assert events[3]["score"] == 0.9
        assert events[4] == {"type": "done"}

    @pytest.mark.asyncio
    async def test_a04_solve_failure_yields_error_then_done(self, async_client):
        center = _stub_center(solve_error=RuntimeError("boom"))

        with patch("internal_api._get_exercise_center", return_value=center):
            response = await async_client.post(
                "/internal/solve",
                json={"question": "1+1=?", "context": ""},
            )

        events = _parse_sse(response.text)
        assert [e["type"] for e in events] == ["error", "done"]
        assert events[0] == {"type": "error", "content": "解题功能暂时不可用，请稍后重试"}
        assert events[1] == {"type": "done"}


# ═══════════════════════════════════════════════════════════════
# EX-A05: JSON 端点包装与 400 分支
# ═══════════════════════════════════════════════════════════════

class TestJsonEndpointDelegation:
    @pytest.mark.asyncio
    async def test_a05_error_analysis_returns_envelope(self, async_client):
        llm = _StubLLM(json.dumps(
            {"analysis": [], "overall_suggestion": "多练习"}, ensure_ascii=False,
        ))
        center = _stub_center(llm=llm)

        with patch("internal_api._get_exercise_center", return_value=center):
            response = await async_client.post(
                "/internal/exercise/error-analysis",
                json={"errors": [{"question": "1+1=?", "user_answer": "3"}], "level": 2},
            )

        body = response.json()
        assert response.status_code == 200
        assert body["success"] is True
        assert body["data"] == {"analysis": [], "overall_suggestion": "多练习"}
        assert "1+1=?" in llm.calls[0]["messages"][0]["content"]

    @pytest.mark.asyncio
    async def test_a05_grade_choice_returns_envelope(self, async_client):
        center = _stub_center()

        with patch("internal_api._get_exercise_center", return_value=center):
            response = await async_client.post(
                "/internal/exercise/grade",
                json={
                    "type": "choice", "user_answer": "A", "correct_answer": "A",
                    "choices": ["A", "B"], "points": 2,
                },
            )

        body = response.json()
        assert response.status_code == 200
        assert body["success"] is True
        assert body["data"]["correct"] is True
        assert body["data"]["score"] == 2

    @pytest.mark.asyncio
    async def test_a05_grade_missing_field_keeps_400(self, async_client):
        center = _stub_center()

        with patch("internal_api._get_exercise_center", return_value=center):
            response = await async_client.post(
                "/internal/exercise/grade", json={"type": "choice"},
            )

        body = response.json()
        assert response.status_code == 400
        assert body["success"] is False
        assert body["errorCode"] == "MISSING_REQUIRED_FIELD"

    @pytest.mark.asyncio
    async def test_a05_evaluation_report_returns_envelope(self, async_client):
        center = _stub_center()

        with patch("internal_api._get_exercise_center", return_value=center):
            response = await async_client.post(
                "/internal/evaluation/report",
                json={"evaluation_results": {"results": [{"correct": True}], "overall_score": 80}},
            )

        body = response.json()
        assert response.status_code == 200
        assert body["success"] is True
        assert "accuracy_pct" in body["data"]

    @pytest.mark.asyncio
    async def test_a05_categorize_returns_results_list(self, async_client):
        center = _stub_center()
        matched = [{"question": "q1", "knowledge_node_id": "kn_1"}]

        with patch("internal_api._get_exercise_center", return_value=center), \
                patch("app.centers.exercise_center.categorize_exercises",
                      new=AsyncMock(return_value=matched)) as service:
            response = await async_client.post(
                "/internal/exercise/categorize",
                json={
                    "exercises": [{"question": "q1", "answer": "a1"}],
                    "knowledge_nodes": [{"id": "kn_1", "name": "极限"}],
                    "course_id": "ai_intro",
                },
            )

        body = response.json()
        assert response.status_code == 200
        assert body["data"] == {"results": matched}
        assert service.await_args.args[2] == "ai_intro"

    @pytest.mark.asyncio
    async def test_a05_session_dashboard_profile_enrich_return_envelope(self, async_client):
        center = _stub_center()
        record = {"knowledge_node_id": "kn_1", "is_correct": False}

        with patch("internal_api._get_exercise_center", return_value=center):
            session = await async_client.post(
                "/internal/exercise/session/analyze",
                json={"records": [record], "masteries": {"kn_1": 0.3}, "course_id": "ai_intro"},
            )
            dashboard = await async_client.post(
                "/internal/exercise/dashboard",
                json={"user_id": 7, "masteries": {"kn_1": 0.3},
                      "recent_records": [record], "course_id": "ai_intro"},
            )
            profile = await async_client.post(
                "/internal/exercise/profile/enrich",
                json={"user_id": 7, "student_profile": {"weak_points": []},
                      "recent_records": [record],
                      "session_analysis": {"weak_nodes": [{"knowledge_node_id": "kn_1"}]}},
            )

        for response in (session, dashboard, profile):
            assert response.status_code == 200
            assert response.json()["success"] is True


# ═══════════════════════════════════════════════════════════════
# EX-A06: 路由源码结构断言
# ═══════════════════════════════════════════════════════════════

# complete_plan_step 归属计划域，见 test_plan_endpoints_api_delegation.py
_EXERCISE_ROUTES = [
    "exercise_generate",
    "solve_question",
    "exercise_error_analysis",
    "grade_exercise",
    "get_evaluation_report",
    "categorize_exercises",
    "analyze_session",
    "exercise_dashboard",
    "enrich_profile",
]

_FORBIDDEN_SYMBOLS = [
    "ExerciseAgent(",
    "SolveAgent(",
    "get_llm_service(",
    "load_prompt_file(",
    "json.dumps(",
    "_sse_stream_chunks(",
]


class TestRouteSourceStructure:
    @pytest.mark.parametrize("route_name", _EXERCISE_ROUTES)
    def test_a06_route_has_no_business_symbols(self, route_name):
        source = inspect.getsource(getattr(internal_api, route_name))
        for symbol in _FORBIDDEN_SYMBOLS:
            assert symbol not in source, f"{route_name} 仍含 {symbol}"

    def test_a06_delegates_to_exercise_center_factory(self):
        for route_name in _EXERCISE_ROUTES:
            source = inspect.getsource(getattr(internal_api, route_name))
            assert "_get_exercise_center()" in source, f"{route_name} 未经 Center"

    def test_a06_solve_agent_factory_removed(self):
        """收口后 /solve 不再有独立 agent 工厂；soft-landing 的 _get_exercise_agent 仍在。"""
        assert not hasattr(internal_api, "_get_solve_agent")
        assert hasattr(internal_api, "_get_exercise_agent")
