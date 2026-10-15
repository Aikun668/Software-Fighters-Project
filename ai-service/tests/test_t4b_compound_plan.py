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


# semantic_result 六元组: (intents, confidences, is_clear, inquiry, latency, err)
def _sr(intents, confidences=None, is_clear=True, err=None):
    if confidences is None:
        confidences = [0.9] * len(intents)
    return (intents, confidences, is_clear, "", 10.0, err)


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
