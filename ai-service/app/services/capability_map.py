"""能力映射唯一真源：意图 → 业务中心 → 执行顺序；模式 ↔ 能力 ↔ 中心。

纯数据、无 import，避免与 intent_extractor / capability_gate / router_agent 循环依赖。
消费方只读取本模块，不得在别处再定义同一映射。
"""

INTENT_CENTER_MAP: dict[str, str] = {
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

CENTER_EXECUTION_ORDER: dict[str, int] = {
    "auto": 1,
    "visualization": 2,
    "resource": 3,
    "exercise": 4,
    "plan": 5,
}

MODE_TO_INTENT: dict[str, str] = {
    "plan": "learning_path",
    "resource": "resource_gen",
    "exercise": "exercise_gen",
    "visualization": "visualize",
}

MODE_TO_KIND: dict[str, str] = {
    "plan": "PLAN",
    "resource": "RESOURCE",
    "exercise": "EXERCISE",
    "visualization": "VISUALIZATION",
}

KIND_TO_CENTER: dict[str, str] = {
    "PLAN": "plan",
    "RESOURCE": "resource",
    "EXERCISE": "exercise",
    "VISUALIZATION": "visualization",
}

ON_TOKEN_CENTERS: frozenset[str] = frozenset({"auto", "exercise"})
