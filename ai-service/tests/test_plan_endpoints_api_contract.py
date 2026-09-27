"""计划域剩余端点收口契约测试（Task 1）。

锁定 `internal_api.py` 里 8 个计划端点的对外契约，作为后续 API 收窄的兼容基线：

- Part A（PL-A01..PL-A30）：锁收口**前**的 HTTP 字节行为，收窄后必须保持全绿。
  注入点全部选在「收窄前后都存在」的符号上（`PlanService` 静态方法、
  `ExerciseCenter` / `ExerciseAgent` 类方法、`evaluation_service` 模块函数、
  `internal_api.api_success`），因此收窄时**断言一字不改**。
- Part B（PL-B01..PL-B16）：锁新增 `PlanService` 纯算法与 `PlanCenter` 业务入口，
  Task 2/3/4 落地前为 **RED**。

预期 RED 形态（Part B）：
    AttributeError: module 'app.centers.plan_center' has no attribute 'PlanNotFoundError'
（模块已存在，因此不是 ModuleNotFoundError）

时间不变量：所有用例都用「相对今天」的输入（`start_date = 今天`、`last_activity_at = 今天-5天`），
期望值由测试自己用同一个 `date.today()` 推导，避免依赖真实时钟。
"""

import contextlib
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import internal_api
from app.centers.exercise_center import ExerciseCenter
from app.agents.exercise_agent import ExerciseAgent
from app.services.plan_constants import RETURN_MESSAGES
from app.services.plan_service import PlanService
from internal_api import router

TODAY = date.today()


# ═══════════════════════════════════════════════════════════════════
# 基础设施
# ═══════════════════════════════════════════════════════════════════

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


@contextlib.contextmanager
def _patch_attr(name: str, value):
    original = getattr(internal_api, name)
    setattr(internal_api, name, value)
    try:
        yield
    finally:
        setattr(internal_api, name, original)


@contextlib.contextmanager
def _patch_method(cls, name: str, value):
    """替换类/模块属性并在退出时还原。

    必须从 `vars()` 取原始对象：对 `@staticmethod` 用 `getattr` 拿到的是裸函数，
    还原后静态方法会退化成实例方法（会把第一个实参当 self 吞掉）。
    """
    original = vars(cls)[name] if name in vars(cls) else getattr(cls, name)
    setattr(cls, name, value)
    try:
        yield
    finally:
        setattr(cls, name, original)


@contextlib.contextmanager
def _boom_success():
    """让路由体内的 `api_success(...)` 抛错，用于锁 500 分支。

    这是唯一一个在收窄前后都稳定存在的注入点：路由永远在同一个 try 里调用
    `api_success`，因此 500 文案可以逐字锁定。
    """
    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    with _patch_attr("api_success", _raise):
        yield


def _plan(**over) -> dict:
    base = {
        "id": 7,
        "user_id": 1,
        "status": "active",
        "total_steps": 3,
        "completed_steps": 1,
    }
    base.update(over)
    return base


def _step(order, *, topic="主题", node_id=None, est=1, status="pending",
          difficulty=3, **over) -> dict:
    base = {
        "id": order,
        "step_order": order,
        "topic": topic,
        "knowledge_node_id": node_id if node_id is not None else f"n{order}",
        "status": status,
        "estimated_days": est,
        "topic_difficulty": difficulty,
        "suggested_resource_types": ["document", "exercise"],
        "mastery_current": 0.5,
        "review_count": 0,
        "last_review_at": None,
    }
    base.update(over)
    return base


def _steps_three() -> list[dict]:
    return [
        _step(1, topic="变量", est=1),
        _step(2, topic="循环", est=2),
        _step(3, topic="函数", est=1),
    ]


# ═══════════════════════════════════════════════════════════════════
# Part A — today（PL-A01..A05 + 404/500）
# ═══════════════════════════════════════════════════════════════════

class TestTodayTasksContract:

    def test_a01_first_day_bucket_and_full_payload(self, client):
        """PL-A01: start_date=今天 → day_index=0，命中第一个 step，逐键锁 payload。"""
        plan = _plan(
            start_date=TODAY.isoformat(),
            milestones=[{"milestone_id": "m1", "after_step": 2, "description": "第一阶段"}],
        )
        r = client.post("/internal/plans/7/today", json={
            "plan": plan, "steps": _steps_three(), "masteries": {"n2": 0.4},
        })
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert list(body["data"].keys()) == [
            "plan_id", "today", "day_index", "total_days_elapsed",
            "steps_due_today", "resource_suggestions", "next_milestone", "summary",
        ]
        assert body["data"] == {
            "plan_id": 7,
            "today": TODAY.isoformat(),
            "day_index": 0,
            "total_days_elapsed": 1,
            "steps_due_today": [{
                "step_order": 1,
                "topic": "变量",
                "knowledge_node_id": "n1",
                "status": "pending",
                "estimated_days": 1,
                "topic_difficulty": 3,
                "suggested_resource_types": ["document", "exercise"],
                "day_progress": 1,
                "day_total": 1,
                "current_mastery": None,
            }],
            "resource_suggestions": [{
                "step_order": 1,
                "topic": "变量",
                "knowledge_node_id": "n1",
                "resource_types": ["document", "exercise"],
                "gen_prompt": "请为「变量」生成学习资源，难度等级 3/5",
            }],
            "next_milestone": {
                "milestone_id": "m1",
                "description": "第一阶段",
                "after_step": 2,
                "steps_remaining": 1,
            },
            "summary": "今日有 1 个学习步骤",
        }

    def test_a02_mid_bucket_day_progress_and_mastery(self, client):
        """PL-A02: 2 天前开始 → day_index=2，命中 est=2 的第二个 step。"""
        plan = _plan(start_date=(TODAY - timedelta(days=2)).isoformat())
        r = client.post("/internal/plans/7/today", json={
            "plan": plan, "steps": _steps_three(), "masteries": {"n2": 0.4},
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["day_index"] == 2
        assert data["total_days_elapsed"] == 3
        assert data["steps_due_today"] == [{
            "step_order": 2,
            "topic": "循环",
            "knowledge_node_id": "n2",
            "status": "pending",
            "estimated_days": 2,
            "topic_difficulty": 3,
            "suggested_resource_types": ["document", "exercise"],
            "day_progress": 2,
            "day_total": 2,
            "current_mastery": 0.4,
        }]

    def test_a03_fallback_branch_with_note(self, client):
        """PL-A03: day_index 超出全部区间且未完成 → 取首个非 completed 步骤 + note。"""
        plan = _plan(start_date=(TODAY - timedelta(days=9)).isoformat())
        steps = _steps_three()
        steps[0]["status"] = "completed"
        r = client.post("/internal/plans/7/today", json={
            "plan": plan, "steps": steps, "masteries": {"n2": 0.4},
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["day_index"] == 9
        assert data["steps_due_today"] == [{
            "step_order": 2,
            "topic": "循环",
            "knowledge_node_id": "n2",
            "status": "pending",
            "estimated_days": 2,
            "topic_difficulty": 3,
            "suggested_resource_types": ["document", "exercise"],
            "day_progress": 1,
            "day_total": 1,
            "current_mastery": 0.4,
            "note": "计划进度落后，显示下一个待完成步骤",
        }]

    def test_a04_invalid_start_date_falls_back_to_today(self, client):
        """PL-A04: 非法 start_date 字符串 → 回退 date.today()。"""
        r = client.post("/internal/plans/7/today", json={
            "plan": _plan(), "steps": _steps_three(), "start_date": "not-a-date",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["day_index"] == 0
        assert data["total_days_elapsed"] == 1
        assert [s["step_order"] for s in data["steps_due_today"]] == [1]

    def test_a05_future_start_date_clamps_day_index_to_zero(self, client):
        """PL-A05: start_date 在未来 → day_index 夹到 0（不是负数）。"""
        r = client.post("/internal/plans/7/today", json={
            "plan": _plan(),
            "steps": _steps_three(),
            "start_date": (TODAY + timedelta(days=3)).isoformat(),
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["day_index"] == 0
        assert data["total_days_elapsed"] == 1
        assert [s["step_order"] for s in data["steps_due_today"]] == [1]

    def test_a06_empty_when_all_done(self, client):
        """PL-A06: 全部完成且超出区间 → 空 + 无兜底 + summary 文案。"""
        plan = _plan(start_date=(TODAY - timedelta(days=9)).isoformat(),
                     completed_steps=3, total_steps=3)
        steps = [_step(i, est=1, status="completed") for i in (1, 2, 3)]
        r = client.post("/internal/plans/7/today", json={"plan": plan, "steps": steps})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["steps_due_today"] == []
        assert data["resource_suggestions"] == []
        assert data["summary"] == "今日无待完成步骤，继续保持！"

    def test_a07_milestone_string_list_yields_none(self, client):
        """PL-A07: milestones 首项是字符串 → next_milestone=None。"""
        plan = _plan(start_date=TODAY.isoformat(), milestones=["里程碑一"])
        r = client.post("/internal/plans/7/today", json={
            "plan": plan, "steps": _steps_three(),
        })
        assert r.status_code == 200
        assert r.json()["data"]["next_milestone"] is None

    def test_a08_plan_missing_returns_404(self, client):
        """PL-A08: plan 为空 dict → 404「计划不存在」。"""
        r = client.post("/internal/plans/7/today", json={"plan": {}, "steps": []})
        assert r.status_code == 404
        assert r.json() == {
            "success": False, "errorCode": "NOT_FOUND", "error": "计划不存在",
        }

    def test_a09_unexpected_error_returns_500(self, client):
        """PL-A09: 路由体内异常 → 500「获取今日任务失败」。"""
        with _boom_success():
            r = client.post("/internal/plans/7/today", json={
                "plan": _plan(start_date=TODAY.isoformat()), "steps": _steps_three(),
            })
        assert r.status_code == 500
        assert r.json() == {
            "success": False, "errorCode": "INTERNAL_ERROR", "error": "获取今日任务失败",
        }


# ═══════════════════════════════════════════════════════════════════
# Part A — progress（PL-A10..A15）
# ═══════════════════════════════════════════════════════════════════

class TestProgressContract:

    def _body(self, **over) -> dict:
        body = {
            "user_id": 1,
            "step_id": 0,
            "step_order": 2,
            "status": "completed",
            "score": 0.8,
            "activity_type": "exercise",
            "duration_minutes": 30,
            "plan": _plan(total_steps=3, completed_steps=0, milestones=[
                {"milestone_id": "m1", "after_step": 2, "description": "第一阶段"},
            ]),
            "steps": _steps_three(),
            "masteries": {"n2": 0.5},
        }
        body.update(over)
        return body

    def test_a10_locate_by_step_order_and_full_payload(self, client):
        """PL-A10: step_id=0 → 按 step_order 定位；掌握度 0.5→0.62（exercise_done, score 0.8）。"""
        r = client.post("/internal/plans/7/progress", json=self._body())
        assert r.status_code == 200
        data = r.json()["data"]
        assert list(data.keys()) == [
            "plan_id", "updated_step", "mastery_updates", "completed_steps",
            "total_steps", "progress_pct", "next_milestone", "updated_steps",
        ]
        assert data["plan_id"] == 7
        assert data["updated_step"] == {
            "step_order": 2,
            "topic": "循环",
            "knowledge_node_id": "n2",
            "status": "completed",
            "score": 0.8,
            "activity_type": "exercise",
            "duration_minutes": 30,
        }
        assert data["mastery_updates"] == {
            "n2": {
                "old_mastery": 0.5,
                "new_mastery": 0.62,
                "delta": 0.12,
                "event_type": "exercise_done",
            },
        }
        assert data["completed_steps"] == 1
        assert data["total_steps"] == 3
        assert data["progress_pct"] == 33
        assert data["next_milestone"] == {
            "milestone_id": "m1", "description": "第一阶段",
            "after_step": 2, "steps_remaining": 1,
        }

    def test_a11_locate_by_step_id_takes_priority(self, client):
        """PL-A11: step_id=1 命中第一个 step（step_id 优先于 step_order）。"""
        r = client.post("/internal/plans/7/progress", json=self._body(
            step_id=1, step_order=3, score=None, activity_type="study",
            masteries={"n1": 0.5},
        ))
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["updated_step"]["step_order"] == 1
        assert data["updated_step"]["knowledge_node_id"] == "n1"
        assert data["mastery_updates"]["n1"]["new_mastery"] == 0.6
        assert data["mastery_updates"]["n1"]["event_type"] == "resource_viewed"
        assert data["mastery_updates"]["n1"]["old_mastery"] == 0.5

    def test_a12_updated_steps_are_shallow_copied(self, client):
        """PL-A12: 原 steps 不被就地修改；其余步骤原样返回。"""
        steps = _steps_three()
        r = client.post("/internal/plans/7/progress", json=self._body(steps=steps))
        assert r.status_code == 200
        data = r.json()["data"]
        assert [s["step_order"] for s in data["updated_steps"]] == [1, 2, 3]
        assert data["updated_steps"][0] == steps[0]
        assert data["updated_steps"][2] == steps[2]
        assert data["updated_steps"][1]["status"] == "completed"
        assert steps[1]["status"] == "pending", "原请求体被就地修改"

    def test_a13_quiz_activity_maps_to_exercise_done(self, client):
        """PL-A13: activity_type=quiz → exercise_done。"""
        r = client.post("/internal/plans/7/progress", json=self._body(
            step_id=2, step_order=0, activity_type="quiz", score=1.0,
        ))
        assert r.status_code == 200
        assert r.json()["data"]["mastery_updates"]["n2"]["event_type"] == "exercise_done"
        assert r.json()["data"]["mastery_updates"]["n2"]["new_mastery"] == 0.7

    def test_a14_step_not_found_returns_404_with_exact_message(self, client):
        """PL-A14: step_id/step_order 都未命中 → 404 + 参数原文案。"""
        r = client.post("/internal/plans/7/progress", json=self._body(
            step_id=99, step_order=88,
        ))
        assert r.status_code == 404
        assert r.json() == {
            "success": False, "errorCode": "NOT_FOUND",
            "error": "步骤 step_id=99 step_order=88 不存在",
        }

    def test_a15_plan_missing_returns_404(self, client):
        """PL-A15: plan 为空 → 404「计划不存在」（先于步骤定位）。"""
        r = client.post("/internal/plans/7/progress", json=self._body(plan={}))
        assert r.status_code == 404
        assert r.json()["error"] == "计划不存在"

    def test_a16_unexpected_error_returns_500(self, client):
        """PL-A16: 路由体内异常 → 500「更新进度失败」。"""
        with _boom_success():
            r = client.post("/internal/plans/7/progress", json=self._body())
        assert r.status_code == 500
        assert r.json() == {
            "success": False, "errorCode": "INTERNAL_ERROR", "error": "更新进度失败",
        }

    def test_a17_mastery_service_failure_returns_500(self, client):
        """PL-A17: PlanService.update_mastery 抛错（收窄前后同一注入点）→ 500。"""
        def _raise(*args, **kwargs):
            raise RuntimeError("service down")

        with _patch_method(PlanService, "update_mastery", staticmethod(_raise)):
            r = client.post("/internal/plans/7/progress", json=self._body())
        assert r.status_code == 500
        assert r.json()["error"] == "更新进度失败"


# ═══════════════════════════════════════════════════════════════════
# Part A — node-status-change（PL-A18..A24）
# ═══════════════════════════════════════════════════════════════════

class TestNodeStatusChangeContract:

    def _body(self, **over) -> dict:
        body = {
            "node_id": "n1",
            "old_status": "pending",
            "new_status": "mastered",
            "plan": _plan(total_steps=2, completed_steps=0),
            "steps": [_step(1, topic="变量"), _step(2, topic="循环")],
            "masteries": {},
        }
        body.update(over)
        return body

    def test_a18_mastered_marks_step_completed(self, client):
        """PL-A18: mastered → mark_completed + 步骤置 completed。"""
        r = client.post("/internal/plans/7/node-status-change", json=self._body(
            masteries={"n1": 0.5},
        ))
        assert r.status_code == 200
        data = r.json()["data"]
        assert list(data.keys()) == [
            "plan_id", "node_id", "new_status", "affected_steps_count", "plan_actions",
            "updated_steps", "plan_status", "completed_steps", "total_steps",
            "progress_pct", "next_milestone", "summary",
        ]
        assert data["affected_steps_count"] == 1
        assert data["plan_actions"] == [{
            "step_order": 1,
            "topic": "变量",
            "action": "mark_completed",
            "old_status": "pending",
            "new_status": "completed",
            "message": "步骤「变量」对应节点已掌握，建议标记为完成",
        }]
        assert data["updated_steps"][0]["status"] == "completed"
        assert data["updated_steps"][0]["mastery_current"] == 0.5
        assert data["updated_steps"][1]["status"] == "pending"
        assert data["completed_steps"] == 1
        assert data["total_steps"] == 2
        assert data["progress_pct"] == 50
        assert data["plan_status"] == "active"
        assert data["summary"] == "节点状态变更影响 1 个计划步骤"

    def test_a19_forgotten_schedules_review_with_decay(self, client):
        """PL-A19: forgotten → schedule_review + decayed_mastery（days_since_review=14）。

        掌握度输入只走 masteries（P1 §3.3：步骤 mastery_current 是展示快照，不作计算输入）。
        """
        steps = [_step(1, topic="变量"), _step(2, topic="循环")]
        r = client.post("/internal/plans/7/node-status-change", json=self._body(
            new_status="forgotten", steps=steps, masteries={"n1": 1.0},
        ))
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["plan_actions"] == [{
            "step_order": 1,
            "topic": "变量",
            "action": "schedule_review",
            "old_status": "pending",
            "new_status": "review",
            "decayed_mastery": 0.25,
            "message": "步骤「变量」对应节点已遗忘（掌握度 0.25），建议安排复习",
        }]
        assert data["updated_steps"][0]["status"] == "review"
        assert data["updated_steps"][0]["mastery_current"] == 1.0
        assert data["completed_steps"] == 0

    def test_a20_learning_unlocks_locked_step(self, client):
        """PL-A20: learning + old ∈ (locked, "") → unlock_step。"""
        steps = [_step(1, topic="变量", status="locked"), _step(2, topic="循环")]
        r = client.post("/internal/plans/7/node-status-change", json=self._body(
            new_status="learning", old_status="locked", steps=steps,
        ))
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["plan_actions"] == [{
            "step_order": 1,
            "topic": "变量",
            "action": "unlock_step",
            "old_status": "locked",
            "new_status": "pending",
            "message": "步骤「变量」前置条件满足，已解锁",
        }]
        assert data["updated_steps"][0]["status"] == "pending"

    def test_a21_learning_with_non_locked_old_status_is_noop(self, client):
        """PL-A21: learning 但 old_status 非 locked/"" → 不产生 action，也不改步骤。"""
        steps = [_step(1, topic="变量", status="in_progress"), _step(2, topic="循环")]
        r = client.post("/internal/plans/7/node-status-change", json=self._body(
            new_status="learning", old_status="in_progress", steps=steps,
        ))
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["plan_actions"] == []
        assert data["affected_steps_count"] == 1
        assert data["updated_steps"] == steps
        assert data["summary"] == "节点状态变更影响 1 个计划步骤"

    def test_a22_locked_relocks_step(self, client):
        """PL-A22: locked → lock_step。"""
        r = client.post("/internal/plans/7/node-status-change", json=self._body(
            new_status="locked", old_status="pending",
        ))
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["plan_actions"][0]["action"] == "lock_step"
        assert data["plan_actions"][0]["message"] == "步骤「变量」前置条件不满足，已重新锁定"
        assert data["updated_steps"][0]["status"] == "locked"

    def test_a23_all_completed_appends_complete_plan(self, client):
        """PL-A23: 全部步骤完成后追加 complete_plan，plan_status 置 completed。"""
        steps = [_step(1, topic="变量", status="completed"), _step(2, topic="循环")]
        r = client.post("/internal/plans/7/node-status-change", json=self._body(
            node_id="n2", new_status="mastered", steps=steps,
        ))
        assert r.status_code == 200
        data = r.json()["data"]
        assert [a["action"] for a in data["plan_actions"]] == ["mark_completed", "complete_plan"]
        assert data["plan_actions"][1] == {
            "step_order": 0,
            "topic": "",
            "action": "complete_plan",
            "old_status": "active",
            "new_status": "completed",
            "message": "所有步骤已完成，建议将计划标记为完成",
        }
        assert data["plan_status"] == "completed"
        assert data["progress_pct"] == 100

    def test_a24_unrelated_node_reports_no_impact(self, client):
        """PL-A24: node_id 未命中任何步骤 → 0 影响 + 兜底 summary。"""
        r = client.post("/internal/plans/7/node-status-change", json=self._body(
            node_id="n404",
        ))
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["affected_steps_count"] == 0
        assert data["plan_actions"] == []
        assert data["summary"] == "此节点状态变更不影响当前计划的步骤"

    def test_a25_missing_plan_or_steps_returns_404(self, client):
        """PL-A25: plan 或 steps 缺失 → 404「计划或步骤数据缺失」。"""
        for body in (self._body(plan={}), self._body(steps=[])):
            r = client.post("/internal/plans/7/node-status-change", json=body)
            assert r.status_code == 404
            assert r.json() == {
                "success": False, "errorCode": "NOT_FOUND",
                "error": "计划或步骤数据缺失",
            }

    def test_a26_unexpected_error_returns_500(self, client):
        """PL-A26: 路由体内异常 → 500「节点状态联动失败」。"""
        with _boom_success():
            r = client.post("/internal/plans/7/node-status-change", json=self._body())
        assert r.status_code == 500
        assert r.json() == {
            "success": False, "errorCode": "INTERNAL_ERROR", "error": "节点状态联动失败",
        }


# ═══════════════════════════════════════════════════════════════════
# Part A — status（PL-A27..A32）
# ═══════════════════════════════════════════════════════════════════

class TestPlanStatusContract:

    def _plan_with_activity(self, **over) -> dict:
        base = _plan(
            status="paused",
            total_steps=2,
            completed_steps=1,
            last_activity_at=(datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
            milestones=[{"milestone_id": "m1", "after_step": 2, "description": "第一阶段"}],
        )
        base.update(over)
        return base

    def _steps(self) -> list[dict]:
        return [
            _step(1, topic="变量", status="paused", difficulty=5, mastery_current=1.0,
                  review_count=0),
            _step(2, topic="循环", status="pending"),
        ]

    def test_a27_paused_plan_triggers_soft_landing(self, client):
        """PL-A27: paused + days_idle=5 → soft_landing（warmup）+ days_idle 注入。"""
        r = client.post("/internal/plans/7/status", json={
            "plan": self._plan_with_activity(), "steps": self._steps(),
            "masteries": {"n1": 1.0},
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert list(data.keys()) == [
            "plan_id", "user_id", "status", "total_steps", "completed_steps",
            "days_idle", "soft_landing", "steps", "next_milestone", "milestone_progress",
        ]
        assert data["days_idle"] == 5
        assert data["soft_landing"] == {
            "strategy": "warmup",
            "message": RETURN_MESSAGES["medium"],
            "review_nodes": ["变量"],
            "decay_results": {"变量": "review_light"},
            "days_idle": 5,
        }
        assert data["completed_steps"] == 1
        assert data["next_milestone"] == {
            "milestone_id": "m1", "description": "第一阶段",
            "after_step": 2, "steps_remaining": 1,
        }
        assert data["milestone_progress"] == {
            "current": 1, "target": 2, "remaining": 1, "pct": 50,
        }

    def test_a28_steps_payload_and_decayed_mastery(self, client):
        """PL-A28: steps 只回 7 个固定字段（步骤快照 mastery_current 不再回传）；paused/in_progress 且 days_idle>0 才加 decayed_mastery。"""
        r = client.post("/internal/plans/7/status", json={
            "plan": self._plan_with_activity(), "steps": self._steps(),
            "masteries": {"n1": 1.0},
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert list(data["steps"][0].keys()) == [
            "id", "step_order", "topic", "knowledge_node_id", "status",
            "topic_difficulty", "decayed_mastery",
        ]
        assert data["steps"][0]["decayed_mastery"] == 0.32
        assert data["steps"][1] == {
            "id": 2, "step_order": 2, "topic": "循环", "knowledge_node_id": "n2",
            "status": "pending", "topic_difficulty": 3,
        }

    def test_a29_active_plan_has_no_soft_landing(self, client):
        """PL-A29: 非 paused 计划即使 days_idle>0 也不触发 soft_landing（但仍算 decayed_mastery）。"""
        r = client.post("/internal/plans/7/status", json={
            "plan": self._plan_with_activity(status="active"),
            "steps": [_step(1, topic="变量", status="in_progress", mastery_current=1.0)],
            "masteries": {"n1": 1.0},
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["days_idle"] == 5
        assert data["soft_landing"] is None
        assert data["steps"][0]["decayed_mastery"] == 0.61

    def test_a30_no_activity_timestamp_yields_zero_idle(self, client):
        """PL-A30: 无 last_activity_at → days_idle=0，无 soft_landing，无 decayed_mastery。"""
        plan = _plan(status="paused", total_steps=1, completed_steps=0)
        r = client.post("/internal/plans/7/status", json={
            "plan": plan, "steps": [_step(1, topic="变量", status="paused")],
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["days_idle"] == 0
        assert data["soft_landing"] is None
        assert "decayed_mastery" not in data["steps"][0]

    def test_a31_invalid_activity_timestamp_is_silent(self, client):
        """PL-A31: last_activity_at 非法字符串 → 静默 days_idle=0（不抛 500）。"""
        r = client.post("/internal/plans/7/status", json={
            "plan": self._plan_with_activity(last_activity_at="not-a-timestamp"),
            "steps": [_step(1, topic="变量", status="paused")],
        })
        assert r.status_code == 200
        assert r.json()["data"]["days_idle"] == 0

    def test_a32_response_plan_id_comes_from_body_not_path(self, client):
        """PL-A32: 响应里的 plan_id 取 body.plan.id（路径参数不参与）。"""
        plan = _plan(status="active", total_steps=0, completed_steps=0)
        plan.pop("id")
        r = client.post("/internal/plans/7/status", json={"plan": plan, "steps": []})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["plan_id"] is None
        assert data["next_milestone"] is None
        assert data["milestone_progress"] is None

    def test_a33_legacy_path_extracts_plan_id_from_body(self, client):
        """PL-A33: 旧路径 /internal/plans/status 复用同一核心逻辑。"""
        r = client.post("/internal/plans/status", json={
            "plan": _plan(id=9, status="active", total_steps=1, completed_steps=0),
            "steps": [_step(1, topic="变量")],
        })
        assert r.status_code == 200
        assert r.json()["data"]["plan_id"] == 9

    def test_a34_plan_missing_returns_404(self, client):
        """PL-A34: plan 为空 → 404「计划不存在」（两条路径一致）。"""
        for path in ("/internal/plans/7/status", "/internal/plans/status"):
            r = client.post(path, json={"plan": {}, "steps": []})
            assert r.status_code == 404
            assert r.json()["error"] == "计划不存在"

    def test_a35_unexpected_error_returns_500(self, client):
        """PL-A35: 路由体内异常 → 500「查询计划状态失败」。"""
        with _boom_success():
            r = client.post("/internal/plans/7/status", json={
                "plan": self._plan_with_activity(), "steps": self._steps(),
            })
        assert r.status_code == 500
        assert r.json() == {
            "success": False, "errorCode": "INTERNAL_ERROR", "error": "查询计划状态失败",
        }

    def test_a36_soft_landing_service_failure_returns_500(self, client):
        """PL-A36: PlanService.soft_landing 抛错 → 500（收窄前后同一注入点）。"""
        def _raise(*args, **kwargs):
            raise RuntimeError("service down")

        with _patch_method(PlanService, "soft_landing", staticmethod(_raise)):
            r = client.post("/internal/plans/7/status", json={
                "plan": self._plan_with_activity(), "steps": self._steps(),
            })
        assert r.status_code == 500
        assert r.json()["error"] == "查询计划状态失败"


# ═══════════════════════════════════════════════════════════════════
# Part A — review-schedule（PL-A37..A39）
# ═══════════════════════════════════════════════════════════════════

class TestReviewScheduleContract:

    def _steps(self) -> list[dict]:
        return [
            _step(1, topic="高紧急", status="completed", difficulty=3, mastery_current=0.5),
            _step(2, topic="跳过", status="pending"),
            _step(3, topic="中紧急", status="review", difficulty=1, mastery_current=1.0,
                  last_review_at=(TODAY - timedelta(days=20)).isoformat()),
            _step(4, topic="低紧急", status="completed", difficulty=1, mastery_current=1.0,
                  last_review_at=(TODAY - timedelta(days=8)).isoformat()),
            _step(5, topic="未到期", status="completed", difficulty=1, mastery_current=1.0,
                  last_review_at=(TODAY - timedelta(days=1)).isoformat()),
        ]

    def test_a37_urgency_partition_and_payload(self, client):
        """PL-A37: 日程过滤（decayed<0.7）+ 三级 urgency + 计数 + 键序。"""
        r = client.post("/internal/plans/7/review-schedule", json={
            "steps": self._steps(), "days_ahead": 7,
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert list(data.keys()) == [
            "plan_id", "days_ahead", "total_reviews", "high_urgency",
            "medium_urgency", "schedule",
        ]
        assert data["plan_id"] == 7
        assert data["days_ahead"] == 7
        assert data["total_reviews"] == 3
        assert data["high_urgency"] == 1
        assert data["medium_urgency"] == 1
        assert data["schedule"] == [
            {
                "step_id": 1, "topic": "高紧急", "knowledge_node_id": "n1",
                "current_mastery": 0.5, "decayed_mastery": 0.0, "review_count": 0,
                "next_review_date": (TODAY + timedelta(days=1)).isoformat(),
                "days_until_review": 1, "urgency": "high",
            },
            {
                "step_id": 3, "topic": "中紧急", "knowledge_node_id": "n3",
                "current_mastery": 1.0, "decayed_mastery": 0.37, "review_count": 0,
                "next_review_date": (TODAY + timedelta(days=1)).isoformat(),
                "days_until_review": 1, "urgency": "medium",
            },
            {
                "step_id": 4, "topic": "低紧急", "knowledge_node_id": "n4",
                "current_mastery": 1.0, "decayed_mastery": 0.67, "review_count": 0,
                "next_review_date": (TODAY + timedelta(days=1)).isoformat(),
                "days_until_review": 1, "urgency": "low",
            },
        ]

    def test_a38_default_days_ahead_is_seven(self, client):
        """PL-A38: days_ahead 缺省为 7。"""
        r = client.post("/internal/plans/7/review-schedule", json={"steps": []})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["days_ahead"] == 7
        assert data["schedule"] == []
        assert data["total_reviews"] == 0

    def test_a39_unexpected_error_returns_500(self, client):
        """PL-A39: 路由体内异常 → 500「获取复习日程失败」。"""
        with _boom_success():
            r = client.post("/internal/plans/7/review-schedule", json={"steps": []})
        assert r.status_code == 500
        assert r.json() == {
            "success": False, "errorCode": "INTERNAL_ERROR", "error": "获取复习日程失败",
        }

    def test_a40_review_schedule_service_failure_returns_500(self, client):
        """PL-A40: PlanService.get_review_schedule 抛错 → 500（收窄前后同一注入点）。"""
        def _raise(*args, **kwargs):
            raise RuntimeError("service down")

        with _patch_method(PlanService, "get_review_schedule", staticmethod(_raise)):
            r = client.post("/internal/plans/7/review-schedule", json={"steps": self._steps()})
        assert r.status_code == 500
        assert r.json()["error"] == "获取复习日程失败"


# ═══════════════════════════════════════════════════════════════════
# Part A — complete-step（PL-A41..A44）
# ═══════════════════════════════════════════════════════════════════

class TestCompleteStepContract:

    def _consolidation_stub(self, questions: list[dict]):
        calls: list[dict] = []

        async def _fake(self, *, topic, knowledge_node_id, is_near_end):
            calls.append({
                "topic": topic,
                "knowledge_node_id": knowledge_node_id,
                "is_near_end": is_near_end,
            })
            return {"questions": list(questions)}

        return _patch_method(ExerciseCenter, "generate_consolidation", _fake), calls

    def test_a41_near_end_generates_comprehensive_review(self, client):
        """PL-A41: completed/total >= 0.8 → is_near_end=True + comprehensive_review。"""
        ctx, calls = self._consolidation_stub([{"question": "综合题"}])
        with ctx:
            r = client.post("/internal/plans/7/complete-step", json={
                "step": {"step_order": 5, "topic": "函数", "knowledge_node_id": "n3"},
                "plan": {"completed_steps": 4, "total_steps": 5},
                "steps": [],
            })
        assert r.status_code == 200
        assert calls == [{
            "topic": "函数", "knowledge_node_id": "n3", "is_near_end": True,
        }]
        assert r.json()["data"] == {
            "step_order": 5,
            "step_completed": True,
            "recommended_action": "comprehensive_review",
            "questions": [{"question": "综合题"}],
            "message": "你已经接近计划尾声，来做几道综合题检验整体掌握情况！",
        }

    def test_a42_not_near_end_uses_consolidation_action(self, client):
        """PL-A42: completed/total < 0.8 → consolidation + 题数文案。"""
        ctx, calls = self._consolidation_stub([{"question": "q1"}, {"question": "q2"}])
        with ctx:
            r = client.post("/internal/plans/7/complete-step", json={
                "step": {"step_order": 2, "topic": "循环", "knowledge_node_id": "n2"},
                "plan": {"completed_steps": 2, "total_steps": 5},
                "steps": [],
            })
        assert r.status_code == 200
        assert calls[0]["is_near_end"] is False
        assert r.json()["data"]["recommended_action"] == "consolidation"
        assert r.json()["data"]["message"] == "完成「循环」的学习，来做 2 道题巩固一下吧"

    def test_a43_total_steps_zero_is_not_near_end(self, client):
        """PL-A43: total_steps=0（steps 空且 plan 无 total）→ is_near_end=False。"""
        ctx, calls = self._consolidation_stub([])
        with ctx:
            r = client.post("/internal/plans/7/complete-step", json={
                "step": {"step_order": 1, "topic": "变量", "knowledge_node_id": "n1"},
                "plan": {},
                "steps": [],
            })
        assert r.status_code == 200
        assert calls[0]["is_near_end"] is False
        assert r.json()["data"]["message"] == "完成「变量」的学习，来做 0 道题巩固一下吧"

    def test_a44_generation_failure_returns_500(self, client):
        """PL-A44: 巩固题生成失败 → 500「生成巩固练习失败」。"""
        async def _raise(self, **kwargs):
            raise RuntimeError("llm down")

        with _patch_method(ExerciseCenter, "generate_consolidation", _raise):
            r = client.post("/internal/plans/7/complete-step", json={
                "step": {"step_order": 1, "topic": "变量"},
                "plan": {"completed_steps": 0, "total_steps": 3},
                "steps": [],
            })
        assert r.status_code == 500
        assert r.json() == {
            "success": False, "errorCode": "INTERNAL_ERROR", "error": "生成巩固练习失败",
        }


# ═══════════════════════════════════════════════════════════════════
# Part A — regression-check（PL-A45..A51）
# ═══════════════════════════════════════════════════════════════════

class TestRegressionCheckContract:

    def _agent_stub(self, results: dict):
        """按 topic 返回 questions 或抛错，记录调用。"""
        calls: list[dict] = []

        async def _fake(self, state):
            calls.append(state)
            outcome = results.get(state["topic"])
            if isinstance(outcome, Exception):
                raise outcome
            return {"questions": list(outcome)}

        return _patch_method(ExerciseAgent, "run", _fake), calls

    def test_a45_no_paused_steps_short_circuits(self, client):
        """PL-A45: 无 paused/in_progress 步骤 → continue + short 文案。"""
        r = client.post("/internal/plans/7/regression-check", json={
            "user_id": 1,
            "plan": _plan(),
            "steps": [_step(1, topic="变量", status="completed")],
            "days_idle": 30,
        })
        assert r.status_code == 200
        assert r.json()["data"] == {
            "plan_id": 7,
            "strategy": "continue",
            "message": RETURN_MESSAGES["short"],
            "questions": [],
        }

    def test_a46_short_idle_continues_without_questions(self, client):
        """PL-A46: days_idle<=3 → soft_landing=continue → 直接返回，不出题。"""
        ctx, calls = self._agent_stub({})
        with ctx:
            r = client.post("/internal/plans/7/regression-check", json={
                "user_id": 1,
                "plan": _plan(),
                "steps": [_step(1, topic="变量", status="paused", mastery_current=1.0)],
                "days_idle": 3,
            })
        assert r.status_code == 200
        assert calls == [], "continue 策略不应触发出题"
        assert r.json()["data"] == {
            "plan_id": 7,
            "strategy": "continue",
            "message": RETURN_MESSAGES["short"],
            "questions": [],
        }

    def test_a47_warmup_tags_each_question_with_review_node(self, client):
        """PL-A47: 出题时每道题带 review_node，且 Agent 参数固定 count=1/easy/warmup_not_exam。"""
        steps = [_step(1, topic="变量", status="paused", mastery_current=1.0, difficulty=5)]
        ctx, calls = self._agent_stub({"变量": [{"question": "热身题"}]})
        with ctx:
            r = client.post("/internal/plans/7/regression-check", json={
                "user_id": 1, "plan": _plan(), "steps": steps, "days_idle": 5,
            })
        assert r.status_code == 200
        assert calls == [{
            "topic": "变量", "count": 1, "difficulty": "easy", "purpose": "warmup_not_exam",
        }]
        data = r.json()["data"]
        assert data["strategy"] == "warmup"
        assert data["message"] == RETURN_MESSAGES["medium"]
        assert data["questions"] == [{"question": "热身题", "review_node": "变量"}]

    def test_a48_single_node_failure_degrades(self, client):
        """PL-A48: 单个节点出题异常 → 跳过该节点，其余节点照常返回。"""
        steps = [
            _step(1, topic="变量", status="paused", difficulty=3),
            _step(2, topic="循环", status="paused", difficulty=5),
        ]
        ctx, calls = self._agent_stub({
            "循环": RuntimeError("llm down"),
            "变量": [{"question": "q"}],
        })
        with ctx:
            r = client.post("/internal/plans/7/regression-check", json={
                "user_id": 1, "plan": _plan(), "steps": steps, "days_idle": 10,
                "masteries": {"n1": 0.2, "n2": 0.2},
            })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["strategy"] == "regression_check"
        assert data["message"] == RETURN_MESSAGES["long"]
        assert data["questions"] == [{"question": "q", "review_node": "变量"}]
        # 优先序按衰减值升序：循环(0.02) < 变量(0.07)
        assert [c["topic"] for c in calls] == ["循环", "变量"]

    def test_a49_grading_updates_mastery_and_reorders(self, client):
        """PL-A49: 阶段2 判分（choice + 简答）→ 掌握度更新 + 重排 + after_fail。"""
        steps = [_step(1, topic="变量", status="paused", knowledge_node_id="n1")]

        def _fake_choice(user_answer, correct_answer, choices=None, multi=False, points=1):
            return {"earned": 1.0}

        async def _fake_short(user_answer, reference_answer, rubric=""):
            return {"earned": 0.4}

        import app.services.evaluation_service as ev
        with _patch_method(PlanService, "estimate_decay", staticmethod(
            lambda *a, **k: 0.05,
        )), _patch_method(ev, "grade_choice", _fake_choice), \
                _patch_method(ev, "grade_short_answer", _fake_short):
            r = client.post("/internal/plans/7/regression-check", json={
                "user_id": 1,
                "plan": _plan(),
                "steps": steps,
                "days_idle": 10,
                "masteries": {"n1": 0.5},
                "answers": [
                    {"topic": "变量", "question_type": "choice",
                     "user_answer": "A", "correct_answer": "A", "choices": ["A", "B"]},
                    {"topic": "变量", "question_type": "short_answer",
                     "user_answer": "x", "correct_answer": "y"},
                ],
            })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["strategy"] == "regression_check"
        assert data["message"] == RETURN_MESSAGES["after_fail"]
        assert data["questions"] == []
        assert data["mastery_updates"] == {
            "变量": {
                "previous_mastery": 0.5,
                "new_mastery": 0.58,
                "step_id": 1,
            },
        }
        assert data["reordered_steps"] == [
            {"step_order": 1, "topic": "变量", "status": "review"},
            {"step_order": 2, "topic": "变量", "status": "paused"},
        ]

    def test_a50_all_pass_skips_reorder(self, client):
        """PL-A50: 无衰减 → reordered_steps=None + after_pass；avg>=0.6 走 exercise_done。"""
        steps = [_step(1, topic="变量", status="completed",
                       knowledge_node_id="n1")]

        def _fake_choice(user_answer, correct_answer, choices=None, multi=False, points=1):
            return {"earned": 1.0}

        import app.services.evaluation_service as ev
        with _patch_method(ev, "grade_choice", _fake_choice):
            r = client.post("/internal/plans/7/regression-check", json={
                "user_id": 1,
                "plan": _plan(),
                "steps": steps,
                "days_idle": 30,
                "masteries": {"n1": 0.5},
                "answers": [{"topic": "变量", "question_type": "choice",
                             "user_answer": "A", "correct_answer": "A"}],
            })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["message"] == RETURN_MESSAGES["after_pass"]
        assert data["reordered_steps"] is None
        assert data["mastery_updates"]["变量"]["new_mastery"] == 0.7

    def test_a51_plan_missing_returns_404(self, client):
        """PL-A51: plan 为空 → 404「计划不存在」。"""
        r = client.post("/internal/plans/7/regression-check", json={
            "user_id": 1, "plan": {}, "steps": [], "days_idle": 0,
        })
        assert r.status_code == 404
        assert r.json() == {
            "success": False, "errorCode": "NOT_FOUND", "error": "计划不存在",
        }

    def test_a52_unexpected_error_returns_500(self, client):
        """PL-A52: 路由体内异常 → 500「回归检测失败，请稍后重试」。"""
        with _boom_success():
            r = client.post("/internal/plans/7/regression-check", json={
                "user_id": 1, "plan": _plan(), "steps": [], "days_idle": 30,
            })
        assert r.status_code == 500
        assert r.json() == {
            "success": False, "errorCode": "INTERNAL_ERROR",
            "error": "回归检测失败，请稍后重试",
        }

    def test_a53_soft_landing_service_failure_returns_500(self, client):
        """PL-A53: PlanService.soft_landing 抛错 → 500（收窄前后同一注入点）。"""
        def _raise(*args, **kwargs):
            raise RuntimeError("service down")

        with _patch_method(PlanService, "soft_landing", staticmethod(_raise)):
            r = client.post("/internal/plans/7/regression-check", json={
                "user_id": 1,
                "plan": _plan(),
                "steps": [_step(1, topic="变量", status="paused", mastery_current=1.0)],
                "days_idle": 5,
            })
        assert r.status_code == 500
        assert r.json()["error"] == "回归检测失败，请稍后重试"


# ═══════════════════════════════════════════════════════════════════
# Part A — 路由集合与旧辅助的现状（收窄后 §结构断言会改，见 Task 5）
# ═══════════════════════════════════════════════════════════════════

class TestRouteSurfaceUnchanged:

    def test_a54_all_eight_paths_are_registered(self):
        """PL-A54: 8 个端点路径与方法在收口前后完全一致。"""
        routes = {
            (r.path, tuple(sorted(r.methods)))
            for r in router.routes
            if getattr(r, "methods", None)
        }
        for path in (
            "/internal/plans/create-from-path",
            "/internal/plans/{plan_id}/complete-step",
            "/internal/plans/{plan_id}/today",
            "/internal/plans/{plan_id}/progress",
            "/internal/plans/{plan_id}/node-status-change",
            "/internal/plans/{plan_id}/status",
            "/internal/plans/status",
            "/internal/plans/{plan_id}/regression-check",
            "/internal/plans/{plan_id}/review-schedule",
        ):
            assert (path, ("POST",)) in routes, f"缺少路由 {path}"


# ═══════════════════════════════════════════════════════════════════
# Part B — PlanService 纯算法契约（Task 2 前 RED）
# ═══════════════════════════════════════════════════════════════════

def _plan_center_module():
    """延迟导入：Task 2/3/4 落地前，Part B 预期 AttributeError → RED。"""
    import app.centers.plan_center as module

    return module


def _service():
    from app.services.plan_service import PlanService as svc

    return svc


class TestPlanServicePureHelpers:

    def test_b01_compute_next_milestone(self):
        """PL-B01: 里程碑计算（含字符串列表 → None）。"""
        svc = _service()
        plan = {"milestones": [
            {"milestone_id": "m2", "after_step": 5, "description": "第二阶段"},
            {"milestone_id": "m1", "after_step": 2, "description": "第一阶段"},
        ]}
        assert svc.compute_next_milestone(plan, 1) == {
            "milestone_id": "m1", "description": "第一阶段",
            "after_step": 2, "steps_remaining": 1,
        }
        assert svc.compute_next_milestone(plan, 2) == {
            "milestone_id": "m2", "description": "第二阶段",
            "after_step": 5, "steps_remaining": 3,
        }
        assert svc.compute_next_milestone(plan, 5) is None
        assert svc.compute_next_milestone({"milestones": ["里程碑一"]}, 0) is None
        assert svc.compute_next_milestone({}, 0) is None

    def test_b02_build_milestone_progress(self):
        """PL-B02: 里程碑进度组装（after_step<=0 → pct=100）。"""
        svc = _service()
        milestone = {
            "milestone_id": "m1", "description": "第一阶段",
            "after_step": 4, "steps_remaining": 1,
        }
        assert svc.build_milestone_progress(3, milestone) == {
            "current": 3, "target": 4, "remaining": 1, "pct": 75,
        }
        assert svc.build_milestone_progress(3, None) is None
        zero = {"milestone_id": "m0", "description": "", "after_step": 0, "steps_remaining": 0}
        assert svc.build_milestone_progress(0, zero)["pct"] == 100

    def test_b03_select_today_steps(self):
        """PL-B03: 分桶命中 + est 下限 1 + 兜底分支带 note。"""
        svc = _service()
        steps = [_step(1, est=1), _step(2, est=2), _step(3, est=1)]
        hit = svc.select_today_steps(
            steps, day_index=2, completed_steps=0, total_steps=3, masteries={"n2": 0.4},
        )
        assert hit == [{
            "step_order": 2, "topic": "主题", "knowledge_node_id": "n2",
            "status": "pending", "estimated_days": 2, "topic_difficulty": 3,
            "suggested_resource_types": ["document", "exercise"],
            "day_progress": 2, "day_total": 2, "current_mastery": 0.4,
        }]

        steps2 = [_step(1, est=0), _step(2, est=1)]
        zero_est = svc.select_today_steps(
            steps2, day_index=0, completed_steps=0, total_steps=2, masteries={},
        )
        assert zero_est[0]["estimated_days"] == 1
        assert zero_est[0]["day_total"] == 1

        steps3 = [_step(1, status="completed"), _step(2), _step(3)]
        fallback = svc.select_today_steps(
            steps3, day_index=99, completed_steps=1, total_steps=3, masteries={},
        )
        assert len(fallback) == 1
        assert fallback[0]["note"] == "计划进度落后，显示下一个待完成步骤"
        assert fallback[0]["day_progress"] == 1
        assert fallback[0]["day_total"] == 1

        assert svc.select_today_steps(
            steps3, day_index=99, completed_steps=3, total_steps=3, masteries={},
        ) == []

    def test_b04_build_resource_suggestions(self):
        """PL-B04: 资源建议文案由 today_steps 派生。"""
        svc = _service()
        assert svc.build_resource_suggestions([{
            "step_order": 2, "topic": "循环", "knowledge_node_id": "n2",
            "suggested_resource_types": ["document"], "topic_difficulty": 4,
        }]) == [{
            "step_order": 2, "topic": "循环", "knowledge_node_id": "n2",
            "resource_types": ["document"],
            "gen_prompt": "请为「循环」生成学习资源，难度等级 4/5",
        }]

    def test_b05_find_step(self):
        """PL-B05: step_id 优先；返回 (step, index)。"""
        svc = _service()
        steps = _steps_three()
        assert svc.find_step(steps, step_id=2, step_order=0) == (steps[1], 1)
        assert svc.find_step(steps, step_id=0, step_order=3) == (steps[2], 2)
        assert svc.find_step(steps, step_id=99, step_order=99) == (None, -1)

    def test_b06_apply_node_status_change(self):
        """PL-B06: 4 分支决策表 + 全完成判定。"""
        svc = _service()
        steps = [_step(1, topic="变量"), _step(2, topic="循环", status="completed")]
        result = svc.apply_node_status_change(
            steps=steps, node_id="n1", new_status="mastered", old_status="pending",
            masteries={}, plan_status="active",
        )
        assert result["completed_steps"] == 2
        assert result["plan_status"] == "completed"
        assert [a["action"] for a in result["plan_actions"]] == ["mark_completed", "complete_plan"]
        assert result["updated_steps"][0]["status"] == "completed"
        assert steps[0]["status"] == "pending", "原 steps 被就地修改"

        noop = svc.apply_node_status_change(
            steps=[_step(1, topic="变量", status="in_progress")], node_id="n1",
            new_status="learning", old_status="in_progress",
            masteries={}, plan_status="active",
        )
        assert noop["plan_actions"] == []
        assert noop["updated_steps"][0]["status"] == "in_progress"

        forgotten = svc.apply_node_status_change(
            steps=[_step(1, topic="变量")], node_id="n1",
            new_status="forgotten", old_status="pending",
            masteries={"n1": 1.0}, plan_status="active",
        )
        assert forgotten["plan_actions"][0]["decayed_mastery"] == 0.25
        assert forgotten["updated_steps"][0]["status"] == "review"

    def test_b07_summarize_review_schedule(self):
        """PL-B07: 复习日程紧急度统计。"""
        svc = _service()
        assert svc.summarize_review_schedule([
            {"urgency": "high"}, {"urgency": "medium"}, {"urgency": "low"},
        ]) == {"high": 1, "medium": 1}
        assert svc.summarize_review_schedule([]) == {"high": 0, "medium": 0}


# ═══════════════════════════════════════════════════════════════════
# Part B — PlanCenter 业务入口契约（Task 3/4/6 前 RED）
# ═══════════════════════════════════════════════════════════════════

class _StubExerciseCenter:
    def __init__(self, *, consolidation=None, warmup=None, error=None):
        self._consolidation = consolidation if consolidation is not None else {"questions": []}
        self._warmup = warmup if warmup is not None else {}
        self._error = error
        self.consolidation_calls: list[dict] = []
        self.warmup_calls: list[dict] = []

    async def generate_consolidation(self, *, topic, knowledge_node_id, is_near_end):
        self.consolidation_calls.append({
            "topic": topic, "knowledge_node_id": knowledge_node_id,
            "is_near_end": is_near_end,
        })
        if self._error is not None:
            raise self._error
        return self._consolidation

    async def generate_warmup(self, *, node_names):
        self.warmup_calls.append({"node_names": list(node_names)})
        return self._warmup


class TestPlanCenterEntries:

    @pytest.mark.asyncio
    async def test_b08_today_tasks_delegates_to_service(self):
        """PL-B08: PlanCenter.today_tasks 返回 API payload（不含 api_success 包装）。"""
        Center = _plan_center_module().PlanCenter
        center = Center()
        result = await center.today_tasks(
            plan_id=7,
            plan=_plan(start_date=TODAY.isoformat()),
            steps=_steps_three(),
            start_date=None,
            masteries={"n2": 0.4},
        )
        assert list(result.keys()) == [
            "plan_id", "today", "day_index", "total_days_elapsed",
            "steps_due_today", "resource_suggestions", "next_milestone", "summary",
        ]
        assert result["plan_id"] == 7
        assert result["day_index"] == 0
        assert [s["step_order"] for s in result["steps_due_today"]] == [1]

    @pytest.mark.asyncio
    async def test_b09_today_tasks_raises_not_found(self):
        """PL-B09: plan 为空 → PlanNotFoundError("计划不存在")。"""
        module = _plan_center_module()
        center = module.PlanCenter()
        with pytest.raises(module.PlanNotFoundError) as exc:
            await center.today_tasks(
                plan_id=7, plan={}, steps=[], start_date=None, masteries={},
            )
        assert str(exc.value) == "计划不存在"

    @pytest.mark.asyncio
    async def test_b10_update_progress_payload_and_not_found(self):
        """PL-B10: update_progress 命中 + 未命中抛 404 文案。"""
        module = _plan_center_module()
        center = module.PlanCenter()
        result = await center.update_progress(
            plan_id=7, plan=_plan(total_steps=3, completed_steps=0), steps=_steps_three(),
            masteries={"n2": 0.5}, step_id=0, step_order=2, status="completed",
            score=0.8, activity_type="exercise", duration_minutes=30,
        )
        assert result["mastery_updates"]["n2"]["new_mastery"] == 0.62
        assert result["mastery_updates"]["n2"]["delta"] == 0.12
        assert result["progress_pct"] == 33

        with pytest.raises(module.PlanNotFoundError) as exc:
            await center.update_progress(
                plan_id=7, plan=_plan(), steps=_steps_three(), masteries={},
                step_id=99, step_order=88, status="completed", score=None,
                activity_type="exercise", duration_minutes=0,
            )
        assert str(exc.value) == "步骤 step_id=99 step_order=88 不存在"

    @pytest.mark.asyncio
    async def test_b11_node_status_change_payload_and_not_found(self):
        """PL-B11: node_status_change 命中 + 数据缺失抛 404 文案。"""
        module = _plan_center_module()
        center = module.PlanCenter()
        result = await center.node_status_change(
            plan_id=7, plan=_plan(total_steps=2, completed_steps=0),
            steps=[_step(1, topic="变量"), _step(2, topic="循环")],
            masteries={}, node_id="n1", old_status="pending", new_status="mastered",
        )
        assert result["plan_actions"][0]["action"] == "mark_completed"
        assert result["progress_pct"] == 50

        with pytest.raises(module.PlanNotFoundError) as exc:
            await center.node_status_change(
                plan_id=7, plan={}, steps=[], masteries={},
                node_id="n1", old_status="", new_status="mastered",
            )
        assert str(exc.value) == "计划或步骤数据缺失"

    @pytest.mark.asyncio
    async def test_b12_plan_status_soft_landing(self):
        """PL-B12: plan_status 触发 soft_landing 并注入 days_idle。"""
        Center = _plan_center_module().PlanCenter
        center = Center()
        result = await center.plan_status(
            plan=_plan(
                status="paused", total_steps=1, completed_steps=0,
                last_activity_at=(datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
            ),
            steps=[_step(1, topic="变量", status="paused", difficulty=5)],
            masteries={"n1": 1.0},
        )
        assert result["days_idle"] == 5
        assert result["soft_landing"]["days_idle"] == 5
        assert result["steps"][0]["decayed_mastery"] == 0.32

    @pytest.mark.asyncio
    async def test_b13_review_schedule_payload(self):
        """PL-B13: review_schedule 不复用 StepProxy，dict 直传语义一致（None → or 默认值）。"""
        Center = _plan_center_module().PlanCenter
        center = Center()
        result = await center.review_schedule(
            plan_id=7,
            steps=[_step(1, topic="高紧急", status="completed", mastery_current=None,
                         difficulty=None, review_count=None)],
            days_ahead=7,
        )
        assert result["plan_id"] == 7
        assert result["days_ahead"] == 7
        assert result["total_reviews"] == 1
        assert result["high_urgency"] == 1
        assert result["schedule"][0]["urgency"] == "high"
        assert result["schedule"][0]["current_mastery"] == 0
        assert result["schedule"][0]["review_count"] == 0

    @pytest.mark.asyncio
    async def test_b14_complete_step_calls_exercise_center_once(self):
        """PL-B14: complete_step 恰好调用一次 generate_consolidation。"""
        Center = _plan_center_module().PlanCenter
        stub = _StubExerciseCenter(consolidation={"questions": [{"question": "综合题"}]})
        center = Center(exercise_center=stub)
        result = await center.complete_step(
            step={"step_order": 5, "topic": "函数", "knowledge_node_id": "n3"},
            plan={"completed_steps": 4, "total_steps": 5},
            steps=[],
        )
        assert stub.consolidation_calls == [{
            "topic": "函数", "knowledge_node_id": "n3", "is_near_end": True,
        }]
        assert result == {
            "step_order": 5,
            "step_completed": True,
            "recommended_action": "comprehensive_review",
            "questions": [{"question": "综合题"}],
            "message": "你已经接近计划尾声，来做几道综合题检验整体掌握情况！",
        }

    @pytest.mark.asyncio
    async def test_b15_regression_check_uses_exercise_center_warmup(self):
        """PL-B15: 阶段1 经 ExerciseCenter.generate_warmup，不再直连 ExerciseAgent。"""
        Center = _plan_center_module().PlanCenter
        stub = _StubExerciseCenter(warmup={"questions": [{"question": "热身", "review_node": "变量"}]})
        center = Center(exercise_center=stub)
        result = await center.regression_check(
            plan_id=7, plan=_plan(),
            steps=[_step(1, topic="变量", status="paused", difficulty=5)],
            days_idle=5, answers=None,
            masteries={"n1": 1.0},
        )
        assert stub.warmup_calls == [{"node_names": ["变量"]}]
        assert result == {
            "plan_id": 7,
            "strategy": "warmup",
            "message": RETURN_MESSAGES["medium"],
            "questions": [{"question": "热身", "review_node": "变量"}],
        }

    @pytest.mark.asyncio
    async def test_b16_regression_check_grading_path(self):
        """PL-B16: 阶段2 判分 + 重排（经 PlanCenter，不碰 HTTP）。"""
        Center = _plan_center_module().PlanCenter
        center = Center()
        import app.services.evaluation_service as ev

        def _fake_choice(user_answer, correct_answer, choices=None, multi=False, points=1):
            return {"earned": 1.0}

        with _patch_method(PlanService, "estimate_decay", staticmethod(lambda *a, **k: 0.05)):
            with _patch_method(ev, "grade_choice", _fake_choice):
                result = await center.regression_check(
                    plan_id=7, plan=_plan(),
                    steps=[_step(1, topic="变量", status="paused",
                                 knowledge_node_id="n1")],
                    days_idle=10,
                    answers=[{"topic": "变量", "question_type": "choice",
                              "user_answer": "A", "correct_answer": "A"}],
                    masteries={"n1": 0.5},
                )
        assert result["message"] == RETURN_MESSAGES["after_fail"]
        assert result["mastery_updates"]["变量"]["new_mastery"] == 0.7
        assert result["reordered_steps"] is not None


class TestPlanCenterStructure:

    def test_b17_center_and_service_do_not_import_fastapi(self):
        """PL-B17: Center / Service 层不含 Web 框架依赖。"""
        import inspect
        import app.services.plan_service as service_module

        center_source = inspect.getsource(_plan_center_module())
        service_source = inspect.getsource(service_module)
        for source, label in ((center_source, "plan_center"), (service_source, "plan_service")):
            assert "fastapi" not in source, f"{label} 引入了 fastapi"
            assert "StreamingResponse" not in source, f"{label} 引入了 StreamingResponse"
            assert "api_success" not in source, f"{label} 引用了 api_success"
