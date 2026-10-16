"""T4-B 复合语义多意图建 plan（_compound_plan_from_semantic）契约。"""

import pytest

from app.centers.chat_center import ChatCenter
from app.centers.router_agent import RouterAgent
from app.services.intent_extractor import IntentExtractor


def _center(enabled=True):
    return ChatCenter(
        router_agent=RouterAgent(intent_extractor=IntentExtractor(use_mock=True)),
        t4b_enabled=enabled,
    )


# semantic_result 七元组: (intents, confidences, is_clear, inquiry, latency, err, params)
def _sr(intents, confidences=None, is_clear=True, err=None, params=None):
    if confidences is None:
        confidences = [0.9] * len(intents)
    if params is None:
        params = [{} for _ in intents]
    return (intents, confidences, is_clear, "", 10.0, err, params)


class TestCompoundPlanFromSemantic:
    def test_two_intents_build_two_tasks_in_order(self):
        cc = _center()
        plan = cc._compound_plan_from_semantic(
            "解释B+树然后出5题",
            _sr(["tutor_question", "exercise_gen"]),
            None, None, 3,
        )
        assert plan is not None
        assert [t.intent for t in plan.tasks] == ["tutor_question", "exercise_gen"]
        assert [t.mode for t in plan.tasks] == ["auto", "exercise"]

    def test_disabled_returns_none(self):
        cc = _center(enabled=False)
        plan = cc._compound_plan_from_semantic(
            "x", _sr(["tutor_question", "exercise_gen"]), None, None, 3,
        )
        assert plan is None

    def test_single_intent_returns_none(self):
        cc = _center()
        assert cc._compound_plan_from_semantic("x", _sr(["exercise_gen"]), None, None, 3) is None

    def test_error_returns_none(self):
        cc = _center()
        assert cc._compound_plan_from_semantic("x", _sr(["tutor_question", "exercise_gen"], err="timeout"), None, None, 3) is None

    def test_not_clear_returns_none(self):
        cc = _center()
        assert cc._compound_plan_from_semantic("x", _sr(["tutor_question", "exercise_gen"], is_clear=False), None, None, 3) is None

    def test_unknown_intent_returns_none(self):
        cc = _center()
        assert cc._compound_plan_from_semantic("x", _sr(["tutor_question", "not_a_real_intent"]), None, None, 3) is None


class TestDependencyEdges:
    def test_diagnose_then_exercise_sets_depends_on(self):
        cc = _center()
        plan = cc._compound_plan_from_semantic(
            "诊断一下薄弱点，然后生成针对性练习",
            _sr(["diagnose", "exercise_gen"]),
            None, None, 3,
        )
        assert plan is not None
        # exercise_gen 依赖 diagnose
        ex = [t for t in plan.tasks if t.intent == "exercise_gen"][0]
        diag = [t for t in plan.tasks if t.intent == "diagnose"][0]
        assert diag.sequence in ex.depends_on

    def test_solve_then_exercise_sets_depends_on(self):
        cc = _center()
        plan = cc._compound_plan_from_semantic(
            "求解这道题，然后找几个类似题",
            _sr(["solve_problem", "exercise_gen"]),
            None, None, 3,
        )
        ex = [t for t in plan.tasks if t.intent == "exercise_gen"][0]
        solve = [t for t in plan.tasks if t.intent == "solve_problem"][0]
        assert solve.sequence in ex.depends_on

    def test_no_dependency_pair_gets_empty(self):
        cc = _center()
        plan = cc._compound_plan_from_semantic(
            "先讲解再出题",
            _sr(["tutor_question", "exercise_gen"]),
            None, None, 3,
        )
        ex = [t for t in plan.tasks if t.intent == "exercise_gen"][0]
        # tutor_question 不在依赖表，exercise_gen 不应依赖它
        assert ex.depends_on == []
