"""能力映射真源契约：数值与 T0 冻结快照一致，且各消费方引用同一对象。"""

from app.centers.chat_task_dispatcher import ChatTaskDispatcher
from app.centers.router_agent import RouterAgent
from app.services import capability_map
from app.services.capability_gate import _MODE_TO_KIND, CapabilityKind


def test_intent_center_map_matches_t0_snapshot():
    assert capability_map.INTENT_CENTER_MAP == {
        "tutor_question": "auto",
        "solve_problem": "auto",
        "diagnose": "auto",
        "learning_path": "plan",
        "exercise_gen": "exercise",
        "resource_gen": "resource",
        "code_example": "resource",
        "visualize": "visualization",
        "knowledge_graph": "visualization",
        "flashcard_gen": "resource",
        "profile_building": "auto",
        "unknown": "auto",
    }


def test_center_execution_order_matches_t0_snapshot():
    assert capability_map.CENTER_EXECUTION_ORDER == {
        "auto": 1,
        "visualization": 2,
        "resource": 3,
        "exercise": 4,
        "plan": 5,
    }


def test_mode_intent_kind_center_tables_match_t0_snapshot():
    assert capability_map.MODE_TO_INTENT == {
        "plan": "learning_path",
        "resource": "resource_gen",
        "exercise": "exercise_gen",
        "visualization": "visualize",
    }
    assert capability_map.KIND_TO_CENTER == {
        "PLAN": "plan",
        "RESOURCE": "resource",
        "EXERCISE": "exercise",
        "VISUALIZATION": "visualization",
    }
    assert capability_map.ON_TOKEN_CENTERS == frozenset({"auto", "exercise"})


def test_consumers_reference_the_single_source():
    assert RouterAgent.MODE_TO_INTENT is capability_map.MODE_TO_INTENT
    assert ChatTaskDispatcher._ON_TOKEN_MODES is capability_map.ON_TOKEN_CENTERS


def test_gate_mode_to_kind_is_derived_from_source():
    assert {m: k.value for m, k in _MODE_TO_KIND.items()} == capability_map.MODE_TO_KIND
    assert all(isinstance(k, CapabilityKind) for k in _MODE_TO_KIND.values())
