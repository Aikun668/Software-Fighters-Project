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

# T4-C：意图级数据依赖（下游 intent → 依赖的上游 intent）。
# 仅声明「下游产物确实需要上游内容」的真依赖；顺序关系不在此表（那是 execution order）。
# 例："诊断薄弱点→生成针对性练习" exercise_gen 依赖 diagnose 的 mastery_vector；
#     "解这道题→找类似题" exercise_gen 依赖 solve_problem 的题目内容。
INTENT_DEPENDENCIES: dict[str, list[str]] = {
    "exercise_gen": ["diagnose", "solve_problem"],
    "learning_path": ["diagnose"],
}

ON_TOKEN_CENTERS: frozenset[str] = frozenset({"auto", "exercise"})
