"""P2 Task 4 契约测试：`next_action` 建议生成（P1 §五）。

对应验收项：
- **A6**：`next_action` **绝不**返回跨域执行指令 —— 一条建议 = 1 个 `action_kind` + 1 个 `entry`。

同时冻结：
1. §5.1 六个 `action_kind`（**不得扩展**）；
2. §5.2 输出形状六字段（文档表头写「5 字段」但表内含 6 行，此处按表实现 6 字段）；
   `entry` 必须是**既有路由**（取自 `frontend/src/router/index.ts` 的真实可导航路径）；
   `dismiss_policy` ∈ {snooze, alternative, manual_pick}；
3. §5.3 触发规则；
4. **V1 优先级** = §5.3 表行序（`resume_plan > review_current_node >
   practice_targeted_questions > check_prerequisite > study_assigned_resource >
   ask_for_explanation`）。文档把排序剪枝登记为 P2 待裁决项，故序由本模块裁决，取文档
   自身的表行序为该序最忠实的依据。（注：§6.2 样例 1/2 **不能**唯一钉死该序 —— 样例 1
   不存在命中行 3 的条件，样例 2 的期望集 `{practice, review}` 两种先后皆可；表行序是
   **唯一有文档依据**的排法，而非逻辑上唯一自洽的排法。）
5. 无规则命中 → `None`（「请从学习计划中选择下一项」的降级文案属既有业务域，**不是第 7 个
   `action_kind`** —— §5.1 冻结）；
6. 先修判定与 `GraphService.check_prerequisites` 的 **parity**（同规则，不是另立阈值）。
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import internal_api
from app.centers.graph_center import GraphCenter
from app.services import next_action as na
from app.services.graph_service import GraphService


SNAPSHOT_URL = "/internal/snapshot"

# 取自 frontend/src/router/index.ts 的**真实可导航**路径。
# 不收录纯 redirect 路径（''、dashboard、profile-chat），它们不可作为 entry。
ALLOWED_ENTRIES = frozenset({
    "/",
    "/resource-center",
    "/learning-path",
    "/ai-tutor",
    "/course-detail",
    "/exercise",
    "/learning-resource-network",
    "/learning-analysis",
    "/question-nav-chat",
})

REQUIRED_FIELDS = frozenset({
    "action_kind", "target", "reason", "expected_minutes", "entry", "dismiss_policy",
})


def _format_validation_error(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = [str(x) for x in err.get("loc", []) if x not in ("body", "query", "path")]
        field = ".".join(loc) or "(root)"
        parts.append(f"字段 '{field}' {err.get('msg', '')}")
    return "; ".join(parts)


class _RecordingCenter:
    def __init__(self, real, calls: list[tuple[str, dict]]):
        self._real = real
        self._calls = calls

    async def get_graph(self, **kwargs):
        self._calls.append(("get_graph", kwargs))
        return await self._real.get_graph(**kwargs)

    async def recommend_next_node(self, **kwargs):
        self._calls.append(("recommend_next_node", kwargs))
        return await self._real.recommend_next_node(**kwargs)


@pytest.fixture()
def graph_calls() -> list[tuple[str, dict]]:
    return []


@pytest.fixture()
def client(graph_calls, monkeypatch) -> TestClient:
    """真实路由 + 真实图谱（`ai_intro` 骨架，edges 真实可用）+ 记录式 Center。"""
    real = GraphCenter(graph_service=GraphService())
    monkeypatch.setattr(
        internal_api, "_graph_center_singleton", _RecordingCenter(real, graph_calls),
    )

    app = FastAPI()
    app.include_router(internal_api.router)

    @app.exception_handler(RequestValidationError)
    async def _handler(_request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "errorCode": "INVALID_REQUEST",
                "error": _format_validation_error(exc),
            },
        )

    return TestClient(app)


def _payload(**overrides) -> dict:
    base = {
        "student_id": 7,
        "course_id": "ai_intro",
        "plan": {},
        "steps": [],
        "masteries": {},
        "recent_evidence": [],
        "student_profile": {},
        "recent_records": [],
        "session_analysis": {},
    }
    base.update(overrides)
    return base


def _plan(**overrides) -> dict:
    """默认活跃计划（空闲 0 天）→ 恒不 interrupted。相对当下，避免日期炸弹。"""
    active_at = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    base = {"id": 42, "title": "AI 入门 30 天", "status": "in_progress",
            "last_activity_at": active_at}
    base.update(overrides)
    return base


def _step(**overrides) -> dict:
    base = {
        "id": 1, "step_order": 1, "topic": "机器学习基础",
        "knowledge_node_id": "ml_basics", "status": "in_progress",
        "mastery_current": None, "mastery_after": None,
    }
    base.update(overrides)
    return base


def _evidence(**overrides) -> dict:
    base = {
        "evidence_id": "exercise:1001:ml_basics",
        "student_id": 7,
        "course_id": "ai_intro",
        "node_id": "ml_basics",
        "type": "exercise_done",
        "occurred_at": "2026-09-27T20:00:00+08:00",
        "source_action": "exercise",
        "source_record_id": "1001",
        "score_or_result": 1.0,
        "confidence": None,
        "effect_hint": "exercise_done",
        "explanation": "学生在练习域完成第 1001 题并答对",
    }
    base.update(overrides)
    return base


def _data(resp) -> dict:
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    return body["data"]


def _make(inputs: dict) -> dict | None:
    """直接调用纯函数（优先级 / 单规则用例走这里，不经 HTTP）。"""
    return na.build_next_action(**inputs)


def _base_inputs(**overrides) -> dict:
    """一组「无任何规则命中」的最小输入 → 默认返回 None。"""
    base = {
        "active_plan": None,
        "current_node": None,
        "mastery": None,
        "recent_evidence": [],
        "steps": [],
        "graph_edges": [],
        "masteries": {},
    }
    base.update(overrides)
    return base


# ═══════════════════════════════════════════════════════════════════
# Part 1 —— 纯函数：六条规则逐条触发 / 不触发
# ═══════════════════════════════════════════════════════════════════


class TestRules:
    def test_na_r01_resume_plan_when_interrupted(self):
        """§5.3 行 1：`active_plan.interrupted == true` → `resume_plan`。"""
        action = _make(_base_inputs(
            active_plan={"interrupted": True,
                         "current_step": {"step_id": 1, "node_id": "ml_basics"}},
            current_node={"node_id": "ml_basics", "reason": "current_step_node"},
        ))
        assert action["action_kind"] == na.ACTION_RESUME_PLAN

    def test_na_r01_resume_plan_not_fired_when_active(self):
        action = _make(_base_inputs(
            active_plan={"interrupted": False,
                         "current_step": {"step_id": 1, "node_id": "ml_basics"}},
            current_node={"node_id": "ml_basics", "reason": "current_step_node"},
            mastery={"node_id": "ml_basics", "value": 0.9, "level": "mastered"},
        ))
        assert action is None

    def test_na_r02_review_on_review_due_reason(self):
        """§5.3 行 2 分支 a：`current_node.reason == review_due` → `review_current_node`。"""
        action = _make(_base_inputs(
            current_node={"node_id": "ml_basics", "reason": "review_due"},
            mastery={"node_id": "ml_basics", "value": 0.4, "level": "learning"},
        ))
        assert action["action_kind"] == na.ACTION_REVIEW_CURRENT_NODE

    def test_na_r02_review_on_low_level_at_current_step(self):
        """§5.3 行 2 分支 b：`level ∈ {beginner, learning}` 且 reason == current_step_node。"""
        action = _make(_base_inputs(
            active_plan={"interrupted": False, "current_step": {"step_id": 1, "node_id": "ml_basics"}},
            current_node={"node_id": "ml_basics", "reason": "current_step_node"},
            mastery={"node_id": "ml_basics", "value": 0.1, "level": "beginner"},
        ))
        assert action["action_kind"] == na.ACTION_REVIEW_CURRENT_NODE

    def test_na_r02_review_not_fired_for_mastered_at_current_step(self):
        action = _make(_base_inputs(
            current_node={"node_id": "ml_basics", "reason": "current_step_node"},
            mastery={"node_id": "ml_basics", "value": 0.9, "level": "mastered"},
        ))
        assert action is None

    def test_na_r03_practice_on_recent_failure(self):
        """§5.3 行 3 分支 a：最近 5 条证据含 `exercise_failed` → `practice_targeted_questions`。"""
        action = _make(_base_inputs(
            current_node={"node_id": "ml_basics", "reason": "current_step_node"},
            mastery={"node_id": "ml_basics", "value": None, "level": "not_started"},
            recent_evidence=[_evidence(type="exercise_failed",
                                       evidence_id="exercise:1002:ml_basics")],
        ))
        assert action["action_kind"] == na.ACTION_PRACTICE_TARGETED_QUESTIONS

    def test_na_r03_practice_on_learning_level(self):
        """§5.3 行 3 分支 b：`level == learning`（且行 2 未先命中）→ 针对性练习。"""
        action = _make(_base_inputs(
            current_node={"node_id": "ml_basics", "reason": "weakest"},
            mastery={"node_id": "ml_basics", "value": 0.45, "level": "learning"},
        ))
        assert action["action_kind"] == na.ACTION_PRACTICE_TARGETED_QUESTIONS

    def test_na_r04_check_prerequisite_on_unmet(self):
        """§5.3 行 4：当前节点存在未满足先修 → `check_prerequisite`。"""
        action = _make(_base_inputs(
            current_node={"node_id": "ml_basics", "reason": "current_step_node"},
            mastery={"node_id": "ml_basics", "value": None, "level": "not_started"},
            graph_edges=[{"source": "ai_overview", "target": "ml_basics", "relation": "depends_on"}],
            masteries={},
        ))
        assert action["action_kind"] == na.ACTION_CHECK_PREREQUISITE

    def test_na_r04_check_prerequisite_not_fired_when_met(self):
        action = _make(_base_inputs(
            current_node={"node_id": "ml_basics", "reason": "current_step_node"},
            mastery={"node_id": "ml_basics", "value": None, "level": "not_started"},
            graph_edges=[{"source": "ai_overview", "target": "ml_basics", "relation": "depends_on"}],
            masteries={"ai_overview": 0.9},
        ))
        # 先修已满足 → 落到行 6（纯陌生节点）
        assert action["action_kind"] == na.ACTION_ASK_FOR_EXPLANATION

    def test_na_r04_ignores_non_depends_on_edges(self):
        """`extends` / `parallel` 不算先修（与 check_prerequisites 同规则）。"""
        action = _make(_base_inputs(
            current_node={"node_id": "transformer", "reason": "current_step_node"},
            mastery={"node_id": "transformer", "value": 0.9, "level": "mastered"},
            graph_edges=[{"source": "dl_basics", "target": "transformer", "relation": "extends"},
                         {"source": "cnn", "target": "transformer", "relation": "extends"}],
            masteries={},
        ))
        assert action is None

    def test_na_r05_study_resource_when_bound_and_unviewed(self):
        """§5.3 行 5：计划当前步骤有绑定资源且未浏览 → `study_assigned_resource`。"""
        action = _make(_base_inputs(
            current_node={"node_id": "ml_basics", "reason": "current_step_node"},
            mastery={"node_id": "ml_basics", "value": None, "level": "not_started"},
            steps=[_step(resource_id=555)],
            masteries={"ai_overview": 0.9},
        ))
        assert action["action_kind"] == na.ACTION_STUDY_ASSIGNED_RESOURCE
        assert action["target"]["resource_topic"] == "机器学习基础"

    def test_na_r05_not_fired_when_resource_already_viewed(self):
        action = _make(_base_inputs(
            current_node={"node_id": "ml_basics", "reason": "current_step_node"},
            mastery={"node_id": "ml_basics", "value": None, "level": "not_started"},
            steps=[_step(resource_id=555)],
            masteries={"ai_overview": 0.9},
            recent_evidence=[_evidence(type="resource_viewed",
                                       evidence_id="resource:555:ml_basics")],
        ))
        assert action["action_kind"] == na.ACTION_ASK_FOR_EXPLANATION

    def test_na_r06_ask_explanation_for_stranger_node(self):
        """§5.3 行 6：`level ∈ {not_started, beginner}` 且无 `exercise_*` 证据。"""
        action = _make(_base_inputs(
            current_node={"node_id": "ml_basics", "reason": "next_ready"},
            mastery={"node_id": "ml_basics", "value": None, "level": "not_started"},
        ))
        assert action["action_kind"] == na.ACTION_ASK_FOR_EXPLANATION

    def test_na_r06_not_fired_when_exercise_evidence_exists(self):
        action = _make(_base_inputs(
            current_node={"node_id": "ml_basics", "reason": "current_step_node"},
            mastery={"node_id": "ml_basics", "value": 0.2, "level": "beginner"},
            recent_evidence=[_evidence(type="exercise_done",
                                       evidence_id="exercise:1001:ml_basics")],
        ))
        # 行 2 会先命中（beginner + current_step_node）→ 复习优先于「请求讲解」
        assert action["action_kind"] == na.ACTION_REVIEW_CURRENT_NODE

    def test_na_degrade_to_none_when_nothing_fires(self):
        """无规则命中 → None（降级文案属既有业务域，不是第 7 个 action_kind）。"""
        assert _make(_base_inputs()) is None

    def test_na_degrade_to_none_when_no_current_node(self):
        assert _make(_base_inputs(
            mastery={"node_id": None, "value": None, "level": "not_started"},
        )) is None


# ═══════════════════════════════════════════════════════════════════
# Part 2 —— V1 优先级（表行序）
# ═══════════════════════════════════════════════════════════════════


class TestPrecedence:

    def _all_fire(self) -> dict:
        """构造一条让**六条规则同时成立**的输入。"""
        return _base_inputs(
            active_plan={"interrupted": True,
                         "current_step": {"step_id": 1, "node_id": "ml_basics"}},
            current_node={"node_id": "ml_basics", "reason": "current_step_node"},
            mastery={"node_id": "ml_basics", "value": 0.45, "level": "learning"},
            recent_evidence=[_evidence(type="exercise_failed",
                                       evidence_id="exercise:1002:ml_basics")],
            steps=[_step(resource_id=555)],
            graph_edges=[{"source": "ai_overview", "target": "ml_basics", "relation": "depends_on"}],
            masteries={},
        )

    def test_na_precedence_row_order_is_the_frozen_order(self):
        assert na.ACTION_KINDS == (
            na.ACTION_RESUME_PLAN,
            na.ACTION_REVIEW_CURRENT_NODE,
            na.ACTION_PRACTICE_TARGETED_QUESTIONS,
            na.ACTION_CHECK_PREREQUISITE,
            na.ACTION_STUDY_ASSIGNED_RESOURCE,
            na.ACTION_ASK_FOR_EXPLANATION,
        )

    def test_na_precedence_resume_plan_wins(self):
        assert _make(self._all_fire())["action_kind"] == na.ACTION_RESUME_PLAN

    def test_na_precedence_review_wins_over_the_rest(self):
        inputs = self._all_fire()
        inputs["active_plan"]["interrupted"] = False
        assert _make(inputs)["action_kind"] == na.ACTION_REVIEW_CURRENT_NODE

    def test_na_precedence_practice_wins_over_prereq_resource_explain(self):
        inputs = self._all_fire()
        inputs["active_plan"]["interrupted"] = False
        # 让行 2 落空：level 非 {beginner, learning} 且 reason != review_due
        inputs["mastery"]["level"] = "not_started"
        assert _make(inputs)["action_kind"] == na.ACTION_PRACTICE_TARGETED_QUESTIONS

    def test_na_precedence_prereq_wins_over_resource_explain(self):
        inputs = self._all_fire()
        inputs["active_plan"]["interrupted"] = False
        inputs["mastery"]["level"] = "not_started"
        inputs["recent_evidence"] = []
        assert _make(inputs)["action_kind"] == na.ACTION_CHECK_PREREQUISITE

    def test_na_precedence_resource_wins_over_explain(self):
        inputs = self._all_fire()
        inputs["active_plan"]["interrupted"] = False
        inputs["mastery"]["level"] = "not_started"
        inputs["recent_evidence"] = []
        inputs["masteries"] = {"ai_overview": 0.9}
        assert _make(inputs)["action_kind"] == na.ACTION_STUDY_ASSIGNED_RESOURCE

    def test_na_only_one_action_is_returned(self):
        action = _make(self._all_fire())
        assert isinstance(action, dict)
        assert "action_kind" in action and isinstance(action["action_kind"], str)


# ═══════════════════════════════════════════════════════════════════
# Part 3 —— A6 硬红线：绝不跨域执行 + 形状冻结
# ═══════════════════════════════════════════════════════════════════


class TestHardRedLineA6:

    def _case_inputs(self):
        """六条规则各造一例，逐个检查红线。"""
        yield "resume_plan", _base_inputs(
            active_plan={"interrupted": True, "current_step": {"step_id": 1, "node_id": "ml_basics"}},
            current_node={"node_id": "ml_basics", "reason": "current_step_node"},
        )
        yield "review_current_node", _base_inputs(
            current_node={"node_id": "ml_basics", "reason": "review_due"},
            mastery={"node_id": "ml_basics", "value": 0.4, "level": "learning"},
        )
        yield "practice_targeted_questions", _base_inputs(
            current_node={"node_id": "ml_basics", "reason": "current_step_node"},
            mastery={"node_id": "ml_basics", "value": None, "level": "not_started"},
            recent_evidence=[_evidence(type="exercise_failed", evidence_id="exercise:9:ml_basics")],
        )
        yield "check_prerequisite", _base_inputs(
            current_node={"node_id": "ml_basics", "reason": "current_step_node"},
            mastery={"node_id": "ml_basics", "value": None, "level": "not_started"},
            graph_edges=[{"source": "ai_overview", "target": "ml_basics", "relation": "depends_on"}],
        )
        yield "study_assigned_resource", _base_inputs(
            current_node={"node_id": "ml_basics", "reason": "current_step_node"},
            mastery={"node_id": "ml_basics", "value": None, "level": "not_started"},
            steps=[_step(resource_id=555)],
            masteries={"ai_overview": 0.9},
        )
        yield "ask_for_explanation", _base_inputs(
            current_node={"node_id": "ml_basics", "reason": "next_ready"},
            mastery={"node_id": "ml_basics", "value": None, "level": "not_started"},
        )

    def test_na_a06_every_action_has_exactly_the_six_fields(self):
        """A6 形状：六字段齐全，不多不少（§5.2）。"""
        for name, inputs in self._case_inputs():
            action = _make(inputs)
            assert action is not None, name
            assert set(action.keys()) == REQUIRED_FIELDS, name

    def test_na_a06_action_kind_is_in_frozen_set(self):
        for name, inputs in self._case_inputs():
            assert _make(inputs)["action_kind"] in na.ACTION_KINDS, name

    def test_na_a06_entry_is_exactly_one_existing_route(self):
        """A6 红线：**一条建议 = 一个 action_kind + 一个 entry**，且 entry 是既有真实路由。"""
        for name, inputs in self._case_inputs():
            entry = _make(inputs)["entry"]
            assert isinstance(entry, str), name
            assert entry in ALLOWED_ENTRIES, f"{name}: {entry} 不是既有可导航路由"
            assert entry.count("/") >= 1, name

    def test_na_a06_target_never_carries_cross_domain_steps(self):
        """A6 红线：`target` 只含 node_id/step_id/resource_topic，**不得**携带执行步骤序列。"""
        forbidden = {"steps", "calls", "sequence", "actions", "pipeline", "then"}
        allowed_target_keys = {"node_id", "step_id", "resource_topic"}
        for name, inputs in self._case_inputs():
            target = _make(inputs)["target"]
            assert isinstance(target, dict), name
            assert set(target.keys()) <= allowed_target_keys, f"{name}: {set(target.keys())}"
            assert not (set(target.keys()) & forbidden), name
            # 不能混入 entry / action_kind 之类的执行指令
            assert "entry" not in target and "action_kind" not in target, name

    def test_na_a06_reason_is_list_of_evidence_ids(self):
        for name, inputs in self._case_inputs():
            reason = _make(inputs)["reason"]
            assert isinstance(reason, list), name
            assert all(isinstance(r, str) for r in reason), name

    def test_na_a06_dismiss_policy_is_one_of_three(self):
        for name, inputs in self._case_inputs():
            policy = _make(inputs)["dismiss_policy"]
            assert policy in (na.DISMISS_SNOOZE, na.DISMISS_ALTERNATIVE,
                              na.DISMISS_MANUAL_PICK), name

    def test_na_a06_expected_minutes_is_int_or_none(self):
        for name, inputs in self._case_inputs():
            minutes = _make(inputs)["expected_minutes"]
            assert minutes is None or (isinstance(minutes, int) and minutes > 0), name

    def test_na_a06_reason_cites_only_evidence_on_the_node(self):
        """`reason` 只能引用当前节点的证据 id（可追溯，P1 §二）。"""
        inputs = _base_inputs(
            current_node={"node_id": "ml_basics", "reason": "current_step_node"},
            mastery={"node_id": "ml_basics", "value": None, "level": "not_started"},
            recent_evidence=[
                _evidence(type="exercise_failed", node_id="ml_basics",
                          evidence_id="exercise:9:ml_basics"),
                _evidence(type="exercise_failed", node_id="cnn",
                          evidence_id="exercise:8:cnn"),
            ],
        )
        action = _make(inputs)
        assert action["reason"] == ["exercise:9:ml_basics"]

    def test_na_a06_entry_values_are_the_documented_business_domains(self):
        """逐动作核对 entry 落点（都必须是既有业务域，非新页面）。"""
        expected = {
            na.ACTION_RESUME_PLAN: na.ENTRY_LEARNING_PATH,
            na.ACTION_REVIEW_CURRENT_NODE: na.ENTRY_LEARNING_PATH,
            na.ACTION_PRACTICE_TARGETED_QUESTIONS: na.ENTRY_EXERCISE,
            na.ACTION_CHECK_PREREQUISITE: na.ENTRY_GRAPH,
            na.ACTION_STUDY_ASSIGNED_RESOURCE: na.ENTRY_RESOURCE_CENTER,
            na.ACTION_ASK_FOR_EXPLANATION: na.ENTRY_AI_TUTOR,
        }
        for name, inputs in self._case_inputs():
            action = _make(inputs)
            assert action["entry"] == expected[action["action_kind"]], name


# ═══════════════════════════════════════════════════════════════════
# Part 4 —— §6.2 样例 1 / 2 对 next_action 的期望
# ═══════════════════════════════════════════════════════════════════


class TestSample62:

    def test_na_sample1_exercise_done_high_score_is_not_practice(self):
        """§6.2 样例 1：练习正确 score=0.9 → `next_action` **非** `practice_targeted`。"""
        action = _make(_base_inputs(
            active_plan={"interrupted": False, "current_step": {"step_id": 1, "node_id": "ml_basics"}},
            current_node={"node_id": "ml_basics", "reason": "current_step_node"},
            mastery={"node_id": "ml_basics", "value": 0.9, "level": "mastered"},
            recent_evidence=[_evidence(type="exercise_done", score_or_result=0.9,
                                       evidence_id="exercise:1001:ml_basics")],
            steps=[_step(resource_id=555)],
            masteries={"ai_overview": 0.9},
        ))
        # 该输入下所有规则落空 → None（None 当然「非 practice_targeted」）
        assert action is None or action["action_kind"] != na.ACTION_PRACTICE_TARGETED_QUESTIONS

    def test_na_sample2_exercise_failed_is_practice_or_review(self):
        """§6.2 样例 2：练习错误 → `next_action ∈ {practice_targeted_questions, review_current_node}`。"""
        action = _make(_base_inputs(
            active_plan={"interrupted": False, "current_step": {"step_id": 1, "node_id": "ml_basics"}},
            current_node={"node_id": "ml_basics", "reason": "current_step_node"},
            mastery={"node_id": "ml_basics", "value": 0.2, "level": "beginner"},
            recent_evidence=[_evidence(type="exercise_failed", evidence_id="exercise:1002:ml_basics")],
        ))
        assert action["action_kind"] in (
            na.ACTION_PRACTICE_TARGETED_QUESTIONS, na.ACTION_REVIEW_CURRENT_NODE,
        )


# ═══════════════════════════════════════════════════════════════════
# Part 5 —— 先修判定与 GraphService.check_prerequisites parity
# ═══════════════════════════════════════════════════════════════════


class TestPrereqParity:
    """`next_action._unmet_prerequisites` 必须与既有 `check_prerequisites` 同规则。

    这是「复用 check_prerequisites」的可执行化证明：同一份真实 `ai_intro` 骨架上，
    两边给出的「未满足先修集合」必须逐节点一致（不是另立阈值）。
    """

    # ai_intro 的 depends_on 先修结构（取自 data/knowledge_graph_skeleton.json）
    NODE_IDS = ("ai_overview", "ml_basics", "dl_basics", "transformer", "nlp_llm",
                "backprop", "overfitting", "self_attention", "gradient_variants", "cnn")

    @pytest.mark.asyncio
    async def test_na_prereq_parity_with_graph_service(self):
        service = GraphService()
        skeleton = service.load_skeleton()
        edges = skeleton["edges"]
        masteries = {
            "ai_overview": 0.9,     # met（>=0.6）
            "ml_basics": 0.4,       # unmet
            "dl_basics": 0.7,       # met
            "gradient_variants": 0.1,  # unmet
        }

        for node_id in self.NODE_IDS:
            official = service.check_prerequisites(node_id, masteries, na.PREREQ_THRESHOLD)
            official_unmet = sorted(p["node_id"] for p in official["unmet"])
            mine = sorted(p["node_id"] for p in
                          na._unmet_prerequisites(node_id, edges, masteries, na.PREREQ_THRESHOLD))
            assert official_unmet == mine, f"{node_id}: {official_unmet} != {mine}"

    def test_na_transformer_has_zero_prereqs(self):
        """transformer 的入边全是 `extends` → depends_on 先修为空。"""
        service = GraphService()
        edges = service.load_skeleton()["edges"]
        assert na._unmet_prerequisites("transformer", edges, {}, na.PREREQ_THRESHOLD) == []

    def test_na_ml_basics_prereq_is_ai_overview(self):
        service = GraphService()
        edges = service.load_skeleton()["edges"]
        unmet = na._unmet_prerequisites("ml_basics", edges, {}, na.PREREQ_THRESHOLD)
        assert [p["node_id"] for p in unmet] == ["ai_overview"]
        assert unmet[0]["gap"] == 0.6


# ═══════════════════════════════════════════════════════════════════
# Part 6 —— 端到端：/internal/snapshot 真的回出 next_action
# ═══════════════════════════════════════════════════════════════════


class TestSnapshotEndpoint:

    def test_na_endpoint_emits_check_prerequisite_for_unmet_prereq(self, client):
        """真实 ai_intro 图谱：当前步骤 ml_basics 先修 ai_overview 未满足 → check_prerequisite。"""
        data = _data(client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(), steps=[_step()], masteries={},
        )))
        action = data["next_action"]
        assert action is not None
        assert action["action_kind"] == na.ACTION_CHECK_PREREQUISITE
        assert action["target"]["node_id"] == "ml_basics"
        assert action["entry"] == na.ENTRY_GRAPH

    def test_na_endpoint_emits_ask_explanation_for_prereq_met_stranger(self, client):
        data = _data(client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(), steps=[_step()], masteries={"ai_overview": 0.9},
        )))
        assert data["next_action"]["action_kind"] == na.ACTION_ASK_FOR_EXPLANATION

    def test_na_endpoint_emits_resume_plan_for_paused_plan(self, client):
        data = _data(client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(status="paused"), steps=[_step()], masteries={"ai_overview": 0.9},
        )))
        assert data["next_action"]["action_kind"] == na.ACTION_RESUME_PLAN

    def test_na_endpoint_emits_study_resource_when_bound(self, client):
        data = _data(client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(), steps=[_step(resource_id=555)], masteries={"ai_overview": 0.9},
        )))
        action = data["next_action"]
        assert action["action_kind"] == na.ACTION_STUDY_ASSIGNED_RESOURCE
        assert action["entry"] == na.ENTRY_RESOURCE_CENTER

    def test_na_endpoint_next_action_for_stranger_node_no_plan(self, client):
        """无计划、无掌握度、无证据 → `current_node` 落到图谱推荐根节点 `ai_overview`
        （`reason=next_ready`，Task 3 已冻结）且该节点档位为 `not_started` → 命中 §5.3 行 6
        「纯陌生节点」→ `ask_for_explanation`。空载荷不等于无信号：无信号的判据是
        `current_node` 缺失，而非掌握度为 0。
        """
        data = _data(client.post(SNAPSHOT_URL, json=_payload()))
        assert data["next_action"] is not None
        assert data["next_action"]["action_kind"] == na.ACTION_ASK_FOR_EXPLANATION

    def test_na_endpoint_next_action_shape_is_frozen(self, client):
        data = _data(client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(), steps=[_step()], masteries={},
        )))
        assert set(data["next_action"].keys()) == REQUIRED_FIELDS

    def test_na_endpoint_never_returns_cross_domain_instruction(self, client):
        """A6：HTTP 层也不得出现执行序列 —— 响应里不得含 calls/steps/pipeline 之类键。"""
        data = _data(client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(), steps=[_step()], masteries={},
        )))
        target = data["next_action"]["target"]
        assert not ({"calls", "steps", "pipeline", "sequence", "then"} & set(target.keys()))
