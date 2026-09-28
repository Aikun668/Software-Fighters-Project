"""`next_action` 建议生成（P1 §五，P2 Task 4 落地）。

纯函数：零 IO、零状态。`LearningSnapshot` 把已经算好的上下文传进来（计划中断标记 / 当前
节点 / 五级 level / 最近证据 / 计划步骤 / 图谱边 / 各节点掌握度），本模块只做一件事 ——
按 P1 §5.3 的表行序挑出**一条**建议。它不读 DB、不调 Center、不落库。

V1 冻结（P1 §五）：
- §5.1 六个 `action_kind`，**不得扩展**；
- §5.2 输出六字段；`entry` 必须是**既有业务域路由**；
- §5.3 触发规则 + 「同时只返回 1 条」；
- **硬红线**：一条建议 = 一个 `action_kind` + 一个 `entry`，绝不返回跨域执行指令。

V1 裁决（P1 把排序剪枝登记为「P2 待裁决项」，此处落地）：

1. **优先级 = §5.3 表行序**（`resume_plan > review_current_node >
   practice_targeted_questions > check_prerequisite > study_assigned_resource >
   ask_for_explanation`）。§5.3 只给条件不给序，故序是本模块的**裁决**，取文档自身的
   表行序作为最忠实的 tiebreak。**诚实说明其约束力**：§6.2 样例 1 / 2 并**不能**唯一
   钉死该序 —— 样例 1 的节点既非 `learning` 又无 `exercise_failed`，行 3 无论排第几都不
   会命中；样例 2 的期望集是 `{practice, review}`，两种先后都满足。真正被裁掉的是
   「`practice` 之后才轮到 `review`」这类与表序相悖的排法；表行序是其中**唯一有文档依据**
   的一个，而非逻辑上唯一自洽的一个。
2. **先修阈值 = `PREREQ_THRESHOLD = 0.6`** —— 与 `check_prerequisites` 路由默认值一致，
   也是 §5.3「复用 `check_prerequisites`」的字面含义。**不采用**
   `recommend_next_node` 里硬编码的 0.85（那是既有不一致，登记待裁决，不在此处悄悄改）。
3. **无规则命中 → `None`**：降级文案「请从学习计划中选择下一项」属既有业务域，
   **不是第 7 个 `action_kind`**（§5.1 冻结）。
4. **回落语义**：命中某 `action_kind` 但其附加闸门不满足时，**继续评估下一条规则**，
   而不是直接返回 `None` —— 否则「先修已满足的陌生节点」会被行 4 吞掉。
5. **`target.resource_topic` 取自步骤的 `topic`**（§5.2 指定了该键，但
   `plan_steps` 里并没有 `resource_topic` 字段，绑定字段是 `resource_id`）。
6. **`expected_minutes` V1 恒为 `null`**：没有时间模型，不造数字（§5.2 允许可为空）。
7. **`dismiss_policy` 按动作性质**：时间型 → `snooze`；有替代动作 → `alternative`；
   结构性受阻（先修未满足，暂不可跳过）→ `manual_pick`。
8. **`reason` 只引用**触发该建议的**节点内证据 id**（P1 §二 可追溯）；纯时间/结构判据
   无证据可引 → `[]`。
"""

from __future__ import annotations

from typing import Final

from app.services.mastery_scale import LEVEL_BEGINNER, LEVEL_LEARNING, LEVEL_NOT_STARTED

# ── §5.1 动作集合（V1 冻结 = 6 个，不得扩展） ──────────────────────

ACTION_RESUME_PLAN: Final = "resume_plan"
ACTION_REVIEW_CURRENT_NODE: Final = "review_current_node"
ACTION_PRACTICE_TARGETED_QUESTIONS: Final = "practice_targeted_questions"
ACTION_CHECK_PREREQUISITE: Final = "check_prerequisite"
ACTION_STUDY_ASSIGNED_RESOURCE: Final = "study_assigned_resource"
ACTION_ASK_FOR_EXPLANATION: Final = "ask_for_explanation"

# 顺序 = §5.3 表行序 = V1 优先级（见模块 docstring 裁决 1）。
ACTION_KINDS: Final = (
    ACTION_RESUME_PLAN,
    ACTION_REVIEW_CURRENT_NODE,
    ACTION_PRACTICE_TARGETED_QUESTIONS,
    ACTION_CHECK_PREREQUISITE,
    ACTION_STUDY_ASSIGNED_RESOURCE,
    ACTION_ASK_FOR_EXPLANATION,
)

# ── §5.2 `dismiss_policy` 枚举 ─────────────────────────────────────

DISMISS_SNOOZE: Final = "snooze"
DISMISS_ALTERNATIVE: Final = "alternative"
DISMISS_MANUAL_PICK: Final = "manual_pick"

DISMISS_POLICIES: Final = (DISMISS_SNOOZE, DISMISS_ALTERNATIVE, DISMISS_MANUAL_PICK)

# ── §5.2 `entry`：既有业务域路由（取自 frontend/src/router/index.ts） ──

ENTRY_LEARNING_PATH: Final = "/learning-path"
ENTRY_EXERCISE: Final = "/exercise"
ENTRY_GRAPH: Final = "/learning-resource-network"
ENTRY_RESOURCE_CENTER: Final = "/resource-center"
ENTRY_AI_TUTOR: Final = "/ai-tutor"

ENTRY_BY_KIND: Final = {
    ACTION_RESUME_PLAN: ENTRY_LEARNING_PATH,
    ACTION_REVIEW_CURRENT_NODE: ENTRY_LEARNING_PATH,
    ACTION_PRACTICE_TARGETED_QUESTIONS: ENTRY_EXERCISE,
    ACTION_CHECK_PREREQUISITE: ENTRY_GRAPH,
    ACTION_STUDY_ASSIGNED_RESOURCE: ENTRY_RESOURCE_CENTER,
    ACTION_ASK_FOR_EXPLANATION: ENTRY_AI_TUTOR,
}

# 裁决 7：时间型 → snooze；有替代 → alternative；结构性受阻 → manual_pick。
DISMISS_BY_KIND: Final = {
    ACTION_RESUME_PLAN: DISMISS_SNOOZE,
    ACTION_REVIEW_CURRENT_NODE: DISMISS_SNOOZE,
    ACTION_PRACTICE_TARGETED_QUESTIONS: DISMISS_ALTERNATIVE,
    ACTION_CHECK_PREREQUISITE: DISMISS_MANUAL_PICK,
    ACTION_STUDY_ASSIGNED_RESOURCE: DISMISS_ALTERNATIVE,
    ACTION_ASK_FOR_EXPLANATION: DISMISS_ALTERNATIVE,
}

# 先修达标阈值（裁决 2）。
PREREQ_THRESHOLD: Final = 0.6

# §5.3 行 2 的低档位触发集 / 行 6 的陌生档位集 / 练习证据集。
_REVIEW_LEVELS: Final = (LEVEL_BEGINNER, LEVEL_LEARNING)
_STRANGER_LEVELS: Final = (LEVEL_NOT_STARTED, LEVEL_BEGINNER)
_EXERCISE_EVIDENCE_TYPES: Final = ("exercise_done", "exercise_failed")
_RESOURCE_VIEWED = "resource_viewed"
_RELATION_DEPENDS_ON = "depends_on"

# 步骤终态：不再占用「计划当前步骤」名额（与 learning_snapshot 同语义）。
_TERMINAL_STEP_STATUS: Final = ("completed", "skipped")


# ── 取属性：steps 既可能是 dict 也可能是对象（镜像 learning_snapshot） ──


def _step_attr(step, name: str, default=None):
    if isinstance(step, dict):
        value = step.get(name, default)
    else:
        value = getattr(step, name, default)
    return default if value is None else value


def _open_steps(steps: list[dict] | None) -> list[dict]:
    """未完成步骤，按 `step_order` 升序。

    **有意镜像** `learning_snapshot._open_steps`（不能 import —— 那边会反向 import 本模块，
    构成循环依赖；services 之间不得反向依赖，故此处照抄语义）。
    """
    opened = [s for s in (steps or [])
              if _step_attr(s, "status", "") not in _TERMINAL_STEP_STATUS]
    return sorted(opened, key=lambda s: _step_attr(s, "step_order", 0) or 0)


# ── §5.3 行 4：先修判定（与 GraphService.check_prerequisites 同规则） ──


def _unmet_prerequisites(node_id: str, edges: list[dict] | None,
                         masteries: dict | None, threshold: float = PREREQ_THRESHOLD) -> list[dict]:
    """未满足先修列表 `[{node_id, mastery, gap}]`。

    **同规则来源** = `GraphService.check_prerequisites`：只认 `relation == "depends_on"`
    的入边（`extends` / `parallel` 不算先修），`masteries.get(pid, 0.0) >= threshold` 视为
    满足，未满足时 `gap = round(max(0.0, threshold - m), 2)`。
    """
    unmet: list[dict] = []
    for edge in edges or []:
        if edge.get("relation") != _RELATION_DEPENDS_ON or edge.get("target") != node_id:
            continue
        prereq_id = edge.get("source")
        if not prereq_id:
            continue
        value = (masteries or {}).get(prereq_id, 0.0)
        mastery = value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0
        if mastery >= threshold:
            continue
        unmet.append({
            "node_id": prereq_id,
            "mastery": mastery,
            "gap": round(max(0.0, threshold - mastery), 2),
        })
    return unmet


# ── 证据检索（节点内，裁决 8） ─────────────────────────────────────


def _node_evidence(node_id: str, evidence: list[dict] | None,
                   types: tuple[str, ...] | None = None) -> list[dict]:
    """当前节点上的证据（可再按类型过滤）。`reason` 只从此处取 id。"""
    hits = [ev for ev in (evidence or []) if ev.get("node_id") == node_id]
    if types is not None:
        hits = [ev for ev in hits if ev.get("type") in types]
    return hits


def _evidence_ids(evidence: list[dict]) -> list[str]:
    return [ev["evidence_id"] for ev in evidence if ev.get("evidence_id")]


# ── 组装（形状冻结，六字段） ───────────────────────────────────────


def _action(action_kind: str, *, target: dict, reason: list[str] | None = None) -> dict:
    """按 §5.2 生成一条建议。

    `expected_minutes` 恒为 `null`（裁决 6）。`entry` / `dismiss_policy` 由 `action_kind`
    唯一决定（单一真源在 `ENTRY_BY_KIND` / `DISMISS_BY_KIND`，避免散落）。
    """
    return {
        "action_kind": action_kind,
        "target": target,
        "reason": reason or [],
        "expected_minutes": None,
        "entry": ENTRY_BY_KIND[action_kind],
        "dismiss_policy": DISMISS_BY_KIND[action_kind],
    }


def _node_target(node_id: str) -> dict:
    return {"node_id": node_id}


# ── 主函数 ────────────────────────────────────────────────────────


def build_next_action(
    *,
    active_plan: dict | None,
    current_node: dict | None,
    mastery: dict | None,
    recent_evidence: list[dict] | None,
    steps: list[dict] | None,
    graph_edges: list[dict] | None,
    masteries: dict | None,
) -> dict | None:
    """按 §5.3 表行序返回**一条** `next_action`；无规则命中 → `None`。

    入参全部来自 `LearningSnapshot` 的既有计算结果（`mastery.level` 已由
    `mastery_scale.mastery_to_level` 算好，本模块**不重算**口径）。
    """
    active_plan = active_plan or {}
    current_node = current_node or {}
    mastery = mastery or {}
    node_id = current_node.get("node_id")
    level = mastery.get("level")
    reason_code = current_node.get("reason")

    if not node_id:
        return None

    # 行 1：计划中断（裁决 4：闸门不满足时继续往下看，而非直接返回 None）
    if active_plan.get("interrupted") is True:
        step = active_plan.get("current_step") or {}
        step_id = step.get("step_id")
        return _action(ACTION_RESUME_PLAN,
                       target={"step_id": step_id} if step_id is not None else {})

    # 行 2：该复习了（到期，或当前步骤处于低档位）
    if reason_code == "review_due" or (
        level in _REVIEW_LEVELS and reason_code == "current_step_node"
    ):
        return _action(ACTION_REVIEW_CURRENT_NODE, target=_node_target(node_id),
                       reason=_evidence_ids(_node_evidence(node_id, recent_evidence)))

    # 行 3：针对性练习（近期练错过，或档位在 learning）
    failures = _node_evidence(node_id, recent_evidence, _EXERCISE_EVIDENCE_TYPES)
    failed = [ev for ev in failures if ev.get("type") == "exercise_failed"]
    if failed or level == LEVEL_LEARNING:
        return _action(ACTION_PRACTICE_TARGETED_QUESTIONS, target=_node_target(node_id),
                       reason=_evidence_ids(failed))

    # 行 4：先修未满足（复用 check_prerequisites 规则）
    if _unmet_prerequisites(node_id, graph_edges, masteries, PREREQ_THRESHOLD):
        return _action(ACTION_CHECK_PREREQUISITE, target=_node_target(node_id))

    # 行 5：计划步骤绑定了资源且尚未浏览。
    # §5.3 措辞是「当前步骤」，实现取**首个已绑定资源的未完成步骤**：resource_id 为空的
    # 步骤跳过而非终止（否则前面挂了空资源步骤就能把整条规则静音）。已在首步看到
    # `resource_viewed` 时 `break` —— 该步「已浏览」不再需要建议，交由行 6 兜底。
    for step in _open_steps(steps):
        resource_id = _step_attr(step, "resource_id")
        if resource_id is None:
            continue
        step_node = _step_attr(step, "knowledge_node_id")
        if _node_evidence(step_node, recent_evidence, (_RESOURCE_VIEWED,)):
            break
        topic = _step_attr(step, "topic", "") or ""
        return _action(ACTION_STUDY_ASSIGNED_RESOURCE, target={
            "step_id": _step_attr(step, "id"),
            "resource_topic": topic,
        })

    # 行 6：纯陌生节点（未开始 / 初学，且没练过）
    if level in _STRANGER_LEVELS and not failures:
        return _action(ACTION_ASK_FOR_EXPLANATION, target=_node_target(node_id))

    # 无规则命中 → 降级（裁决 3：不是第 7 个 action_kind）
    return None
