"""计划域收口同进程 ASGI 委派测试（Task 8）。

用 httpx ASGITransport 起同进程 HTTP，验证收窄后的真实链路：

- PL-D01..D08: POST /internal/plans/* → _get_plan_center() → PlanCenter.<入口>
  → PlanService 纯算法 → api_success 序列化
- PL-D09: 委派签名 —— API 把 body 字段原样传给 Center
- PL-D10: inspect.getsource 结构断言 —— 路由内不再持有计划域业务符号

不调真实 LLM：_get_plan_center 被替换为真实 PlanCenter 实例（仅注入替身
ExerciseCenter），PlanCenter / PlanService / 序列化 / 错误映射全部走真实代码。
"""

import inspect
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

import internal_api
from app.centers.plan_center import PlanCenter
from internal_api import router

TODAY = date.today()
IDLE_ANCHOR = (datetime.now(timezone.utc) - timedelta(days=5, hours=1)).isoformat()


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


class _StubExerciseCenter:
    """替身练习 Center：记录调用，返回固定题。"""

    def __init__(self, questions=None):
        self.questions = questions if questions is not None else [{"question": "固定题"}]
        self.consolidation_calls: list[dict] = []
        self.warmup_calls: list[dict] = []

    async def generate_consolidation(self, *, topic, knowledge_node_id, is_near_end):
        self.consolidation_calls.append({
            "topic": topic, "knowledge_node_id": knowledge_node_id,
            "is_near_end": is_near_end,
        })
        return {"questions": list(self.questions)}

    async def generate_warmup(self, *, node_names):
        self.warmup_calls.append({"node_names": list(node_names)})
        return {"questions": [{**q, "review_node": node_names[0]} for q in self.questions]}


def _real_center(exercise_center=None) -> PlanCenter:
    return PlanCenter(exercise_center=exercise_center or _StubExerciseCenter())


def _plan(**over) -> dict:
    base = {
        "id": 7,
        "user_id": 1,
        "status": "active",
        "total_steps": 3,
        "completed_steps": 1,
        "start_date": TODAY.isoformat(),
        "milestones": [{"milestone_id": "m1", "after_step": 2, "description": "第一阶段"}],
    }
    base.update(over)
    return base


def _step(order: int, **over) -> dict:
    base = {
        "id": order,
        "step_order": order,
        "topic": "主题",
        "knowledge_node_id": f"n{order}",
        "status": "pending",
        "estimated_days": 1,
        "topic_difficulty": 3,
        "mastery_current": 0.5,
        "review_count": 0,
        "last_review_at": None,
    }
    base.update(over)
    return base


def _steps_three() -> list[dict]:
    return [
        _step(1, topic="变量"),
        _step(2, topic="循环", estimated_days=2),
        _step(3, topic="函数"),
    ]


# ═══════════════════════════════════════════════════════════════
# PL-D01..D05: 读路径 / 写路径经真实 PlanCenter
# ═══════════════════════════════════════════════════════════════

class TestPlanRoutesThroughRealCenter:

    @pytest.mark.asyncio
    async def test_d01_today_delegates_and_returns_envelope(self, async_client):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(internal_api, "_get_plan_center", _real_center)
            response = await async_client.post("/internal/plans/7/today", json={
                "plan": _plan(), "steps": _steps_three(), "masteries": {"n2": 0.4},
            })

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["plan_id"] == 7
        assert body["data"]["today"] == TODAY.isoformat()
        assert [s["step_order"] for s in body["data"]["steps_due_today"]] == [1]
        assert body["data"]["resource_suggestions"][0]["gen_prompt"] == (
            "请为「变量」生成学习资源，难度等级 3/5"
        )

    @pytest.mark.asyncio
    async def test_d02_progress_computes_mastery_and_404(self, async_client):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(internal_api, "_get_plan_center", _real_center)
            ok = await async_client.post("/internal/plans/7/progress", json={
                "user_id": 1, "step_id": 0, "step_order": 2, "status": "completed",
                "score": 0.8, "activity_type": "exercise", "duration_minutes": 30,
                "plan": _plan(total_steps=3, completed_steps=0),
                "steps": _steps_three(), "masteries": {"n2": 0.5},
            })
            missing = await async_client.post("/internal/plans/7/progress", json={
                "user_id": 1, "step_id": 99, "step_order": 88, "status": "completed",
                "score": None, "activity_type": "exercise", "duration_minutes": 0,
                "plan": _plan(), "steps": _steps_three(), "masteries": {},
            })

        assert ok.status_code == 200
        assert ok.json()["data"]["updated_step"]["mastery_current"] == 0.62
        assert ok.json()["data"]["progress_pct"] == 33
        assert missing.status_code == 404
        assert missing.json()["error"] == "步骤 step_id=99 step_order=88 不存在"

    @pytest.mark.asyncio
    async def test_d03_node_status_change_actions_and_404(self, async_client):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(internal_api, "_get_plan_center", _real_center)
            ok = await async_client.post(
                "/internal/plans/7/node-status-change", json={
                    "node_id": "n1", "old_status": "pending", "new_status": "mastered",
                    "plan": _plan(total_steps=2, completed_steps=0),
                    "steps": [_step(1, topic="变量"), _step(2, topic="循环")],
                    "masteries": {},
                })
            missing = await async_client.post(
                "/internal/plans/7/node-status-change", json={
                    "node_id": "n1", "old_status": "", "new_status": "mastered",
                    "plan": {}, "steps": [], "masteries": {},
                })

        assert ok.status_code == 200
        assert ok.json()["data"]["plan_actions"][0]["action"] == "mark_completed"
        assert ok.json()["data"]["progress_pct"] == 50
        assert missing.status_code == 404
        assert missing.json()["error"] == "计划或步骤数据缺失"

    @pytest.mark.asyncio
    async def test_d04_status_both_paths_share_soft_landing(self, async_client):
        payload = {
            "plan": _plan(status="paused", total_steps=2, completed_steps=1,
                          last_activity_at=IDLE_ANCHOR),
            "steps": [
                _step(1, topic="变量", status="paused", topic_difficulty=5,
                      mastery_current=1.0),
                _step(2, topic="循环"),
            ],
        }
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(internal_api, "_get_plan_center", _real_center)
            path = await async_client.post("/internal/plans/7/status", json=payload)
            legacy = await async_client.post("/internal/plans/status", json=payload)

        assert path.status_code == legacy.status_code == 200
        assert path.text == legacy.text
        data = path.json()["data"]
        assert data["days_idle"] == 5
        assert data["soft_landing"]["strategy"] == "warmup"
        assert data["soft_landing"]["days_idle"] == 5
        assert data["steps"][0]["decayed_mastery"] == 0.32

    @pytest.mark.asyncio
    async def test_d05_review_schedule_three_urgencies(self, async_client):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(internal_api, "_get_plan_center", _real_center)
            response = await async_client.post(
                "/internal/plans/7/review-schedule", json={
                    "days_ahead": 7,
                    "steps": [
                        _step(1, topic="高紧急", status="completed", mastery_current=0.5),
                        _step(2, topic="跳过", status="pending"),
                        _step(3, topic="中紧急", status="review", topic_difficulty=1,
                              mastery_current=1.0,
                              last_review_at=(TODAY - timedelta(days=20)).isoformat()),
                    ],
                })

        assert response.status_code == 200
        data = response.json()["data"]
        assert (data["total_reviews"], data["high_urgency"], data["medium_urgency"]) == (2, 1, 1)
        assert [s["topic"] for s in data["schedule"]] == ["高紧急", "中紧急"]


# ═══════════════════════════════════════════════════════════════
# PL-D06..D08: 跨域端点经 PlanCenter 调 ExerciseCenter
# ═══════════════════════════════════════════════════════════════

class TestCrossDomainRoutes:

    @pytest.mark.asyncio
    async def test_d06_complete_step_goes_through_exercise_center(self, async_client):
        stub = _StubExerciseCenter(questions=[{"question": "综合题"}])
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(internal_api, "_get_plan_center", lambda: _real_center(stub))
            response = await async_client.post(
                "/internal/plans/7/complete-step", json={
                    "step": {"step_order": 5, "topic": "函数", "knowledge_node_id": "n3"},
                    "plan": {"completed_steps": 4, "total_steps": 5}, "steps": [],
                })

        assert response.status_code == 200
        assert stub.consolidation_calls == [{
            "topic": "函数", "knowledge_node_id": "n3", "is_near_end": True,
        }]
        assert response.json()["data"]["recommended_action"] == "comprehensive_review"
        assert response.json()["data"]["questions"] == [{"question": "综合题"}]

    @pytest.mark.asyncio
    async def test_d07_regression_warmup_goes_through_exercise_center(self, async_client):
        stub = _StubExerciseCenter(questions=[{"question": "热身题"}])
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(internal_api, "_get_plan_center", lambda: _real_center(stub))
            response = await async_client.post(
                "/internal/plans/7/regression-check", json={
                    "user_id": 1, "plan": _plan(),
                    "steps": [_step(1, topic="变量", status="paused", topic_difficulty=5,
                                    mastery_current=1.0)],
                    "days_idle": 5,
                })

        assert response.status_code == 200
        assert stub.warmup_calls == [{"node_names": ["变量"]}]
        data = response.json()["data"]
        assert data["strategy"] == "warmup"
        assert data["questions"] == [{"question": "热身题", "review_node": "变量"}]

    @pytest.mark.asyncio
    async def test_d08_regression_graded_updates_and_reorders(self, async_client):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(internal_api, "_get_plan_center", _real_center)
            response = await async_client.post(
                "/internal/plans/7/regression-check", json={
                    "user_id": 1, "plan": _plan(),
                    "steps": [_step(1, topic="变量", status="paused", mastery_current=0.5,
                                    knowledge_node_id="n1")],
                    "days_idle": 10,
                    "answers": [{"topic": "变量", "question_type": "choice",
                                 "user_answer": "A", "correct_answer": "A"}],
                })

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["strategy"] == "regression_check"
        assert data["mastery_updates"]["变量"]["new_mastery"] == 0.7
        assert data["reordered_steps"][0]["topic"] == "变量"


# ═══════════════════════════════════════════════════════════════
# PL-D09: 委派签名
# ═══════════════════════════════════════════════════════════════

class _SpyCenter:
    """记录被调用的 Center 入口与关键字实参。"""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def _record(self, name: str, kwargs: dict) -> dict:
        self.calls.append((name, kwargs))
        return {"spy": name}

    async def today_tasks(self, **kwargs):
        return self._record("today_tasks", kwargs)

    async def update_progress(self, **kwargs):
        return self._record("update_progress", kwargs)

    async def node_status_change(self, **kwargs):
        return self._record("node_status_change", kwargs)

    async def plan_status(self, **kwargs):
        return self._record("plan_status", kwargs)

    async def review_schedule(self, **kwargs):
        return self._record("review_schedule", kwargs)

    async def complete_step(self, **kwargs):
        return self._record("complete_step", kwargs)

    async def regression_check(self, **kwargs):
        return self._record("regression_check", kwargs)


class TestDelegationSignature:

    @pytest.mark.asyncio
    async def test_d09_api_passes_body_fields_to_center(self, async_client):
        spy = _SpyCenter()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(internal_api, "_get_plan_center", lambda: spy)

            today = await async_client.post("/internal/plans/7/today", json={
                "plan": _plan(), "steps": _steps_three(), "masteries": {"n2": 0.4},
            })
            progress = await async_client.post("/internal/plans/7/progress", json={
                "user_id": 1, "step_id": 12, "step_order": 0, "status": "completed",
                "score": 0.9, "activity_type": "quiz", "duration_minutes": 15,
                "plan": _plan(), "steps": [], "masteries": {"n1": 0.2},
            })
            review = await async_client.post("/internal/plans/7/review-schedule", json={
                "days_ahead": 3, "steps": [],
            })

        assert [c[0] for c in spy.calls] == [
            "today_tasks", "update_progress", "review_schedule",
        ]
        assert [r.status_code for r in (today, progress, review)] == [200, 200, 200]

        _, today_kwargs = spy.calls[0]
        assert today_kwargs["plan_id"] == 7
        assert today_kwargs["start_date"] is None
        assert today_kwargs["masteries"] == {"n2": 0.4}
        assert today_kwargs["plan"]["id"] == 7

        _, progress_kwargs = spy.calls[1]
        assert progress_kwargs["step_id"] == 12
        assert progress_kwargs["status"] == "completed"
        assert progress_kwargs["score"] == 0.9
        assert progress_kwargs["activity_type"] == "quiz"
        assert progress_kwargs["duration_minutes"] == 15
        assert progress_kwargs["masteries"] == {"n1": 0.2}

        _, review_kwargs = spy.calls[2]
        assert review_kwargs == {"plan_id": 7, "steps": [], "days_ahead": 3}


# ═══════════════════════════════════════════════════════════════
# PL-D10: 路由源码结构断言
# ═══════════════════════════════════════════════════════════════

_PLAN_ROUTES = [
    "get_today_tasks",
    "update_plan_progress",
    "on_node_status_change",
    "get_plan_status",
    "get_plan_status_legacy",
    "get_review_schedule",
    "complete_plan_step",
    "regression_check",
]

_FORBIDDEN_SYMBOLS = [
    "PlanService.",
    "get_plan_service(",
    "_get_exercise_center(",
    "_get_exercise_agent(",
    "ExerciseAgent(",
    "ExerciseCenter(",
    "evaluation_service",
    "estimate_decay(",
    "update_mastery(",
    "soft_landing(",
    "select_today_steps(",
    "compute_next_milestone(",
    "_compute_next_milestone",
    "_get_plan_status_core",
    "StepProxy",
]


class TestRouteSourceStructure:

    @pytest.mark.parametrize("route_name", _PLAN_ROUTES)
    def test_d10_route_delegates_to_plan_center(self, route_name):
        source = inspect.getsource(getattr(internal_api, route_name))
        assert "_get_plan_center()" in source, f"{route_name} 未经 PlanCenter"

    @pytest.mark.parametrize("route_name", _PLAN_ROUTES)
    def test_d10_route_has_no_business_symbols(self, route_name):
        source = inspect.getsource(getattr(internal_api, route_name))
        for symbol in _FORBIDDEN_SYMBOLS:
            assert symbol not in source, f"{route_name} 仍含 {symbol}"

    def test_d10_module_helpers_removed(self):
        assert not hasattr(internal_api, "_compute_next_milestone")
        assert not hasattr(internal_api, "_get_plan_status_core")
        assert not hasattr(internal_api, "RETURN_MESSAGES")
