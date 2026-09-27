"""学习证据契约（P1 §四，P2 Task 2 落地）。

职责边界（严格保持 Python「零状态」原则）：
- 本模块**不读 DB、不调 Java、不落长期状态**；
- `apply_evidence` 是**计算**：给当前掌握度 → 算出 `new_mastery`，与 `GraphCenter.update_masteries`
  走的是同一个 `PlanService.update_mastery`，口径唯一；
- 幂等去重是**进程内的有界去重**，仅用于契约层防重复记账（决策点 4：本阶段不开退化键）。
  JVM 侧的重启/多实例幂等由 Java 落库负责，Python 不承担。
"""

import logging
from datetime import datetime
from typing import Final

from app.services.mastery_scale import mastery_to_level

logger = logging.getLogger(__name__)


# ── 冻结枚举（P1 §4.2 / §4.3）─────────────────────────────────

TYPE_RESOURCE_VIEWED: Final = "resource_viewed"
TYPE_EXERCISE_DONE: Final = "exercise_done"
TYPE_EXERCISE_FAILED: Final = "exercise_failed"
TYPE_TUTOR_QUESTION_ASKED: Final = "tutor_question_asked"
TYPE_MANUAL_CORRECTION: Final = "manual_correction"

EVIDENCE_TYPES: Final = (
    TYPE_RESOURCE_VIEWED,
    TYPE_EXERCISE_DONE,
    TYPE_EXERCISE_FAILED,
    TYPE_TUTOR_QUESTION_ASKED,
    TYPE_MANUAL_CORRECTION,
)

SOURCE_ACTION_EXERCISE: Final = "exercise"
SOURCE_ACTION_PLAN: Final = "plan"
SOURCE_ACTION_RESOURCE: Final = "resource"
SOURCE_ACTION_TUTOR: Final = "tutor"
SOURCE_ACTION_MANUAL: Final = "manual"

SOURCE_ACTIONS: Final = (
    SOURCE_ACTION_EXERCISE,
    SOURCE_ACTION_PLAN,
    SOURCE_ACTION_RESOURCE,
    SOURCE_ACTION_TUTOR,
    SOURCE_ACTION_MANUAL,
)

# 映射矩阵（P1 §4.3 V1 冻结）：不合法的组合必须被拒绝（快速失败）。
SOURCE_ACTION_TO_TYPES: Final[dict[str, tuple[str, ...]]] = {
    SOURCE_ACTION_EXERCISE: (TYPE_EXERCISE_DONE, TYPE_EXERCISE_FAILED),
    SOURCE_ACTION_PLAN: (TYPE_EXERCISE_DONE, TYPE_EXERCISE_FAILED, TYPE_RESOURCE_VIEWED),
    SOURCE_ACTION_RESOURCE: (TYPE_RESOURCE_VIEWED,),
    SOURCE_ACTION_TUTOR: (TYPE_TUTOR_QUESTION_ASKED,),
    SOURCE_ACTION_MANUAL: (TYPE_MANUAL_CORRECTION,),
}

# `effect_hint` 的取值域：文档未冻结具体枚举，先斩后奏裁决为「与 type 同域」——
# 它表达的正是「这条证据对应哪种累积语义」，复用 type 值域可让前端/Java 无需第二套词表。
EFFECT_HINTS: Final = EVIDENCE_TYPES

# 强证据（P1 §4.5）：可改掌握度且改动显著。
STRONG_TYPES: Final = (TYPE_EXERCISE_DONE, TYPE_EXERCISE_FAILED, TYPE_MANUAL_CORRECTION)
# 弱证据：可改掌握度，但算法增幅极小。
WEAK_TYPES: Final = (TYPE_RESOURCE_VIEWED, TYPE_TUTOR_QUESTION_ASKED)

# 无节点归属的保留值（P1 §4.1）：不得为 null。
NODE_NONE: Final = "__none__"

# 进程内去重容量上限：超出后整体清空，最坏情况是「重放的历史证据可能被二次记账」，
# 而不是无界内存增长。契约层只防「同一次点击重试」，不承担跨进程/跨重启幂等。
MAX_SEEN_KEYS: Final = 4096

_seen_keys: set[str] = set()


class EvidenceContractError(ValueError):
    """非法证据（组合不合法 / 关键字段缺失）。边界校验，快速失败。"""


def allowed_types(source_action: str) -> tuple[str, ...]:
    """返回某 `source_action` 允许的 `type` 列表；未知 source_action 返回空元组。"""
    return SOURCE_ACTION_TO_TYPES.get(source_action, ())


def validate_combination(source_action: str, evidence_type: str) -> None:
    """校验 `(source_action, type)` 组合合法性（P1 §4.3）。

    Raises:
        EvidenceContractError: 组合不合法或枚举值未知。
    """
    if source_action not in SOURCE_ACTION_TO_TYPES:
        raise EvidenceContractError(
            f"未知 source_action='{source_action}'，允许值：{', '.join(SOURCE_ACTIONS)}"
        )
    if evidence_type not in EVIDENCE_TYPES:
        raise EvidenceContractError(
            f"未知 type='{evidence_type}'，允许值：{', '.join(EVIDENCE_TYPES)}"
        )
    permitted = SOURCE_ACTION_TO_TYPES[source_action]
    if evidence_type not in permitted:
        raise EvidenceContractError(
            f"非法组合：(source_action='{source_action}', type='{evidence_type}') 不被允许；"
            f"source_action='{source_action}' 仅允许 {', '.join(permitted)}"
        )


def idempotent_key(
    *, student_id: int, course_id: str, node_id: str, source_action: str, source_record_id: str,
) -> str:
    """幂等键（P1 §4.4）：`(student_id, course_id, node_id, source_action, source_record_id)`。"""
    return "|".join([
        str(student_id), course_id, node_id, source_action, source_record_id,
    ])


def _evict_if_full() -> None:
    if len(_seen_keys) >= MAX_SEEN_KEYS:
        logger.info("evidence idempotency store full (%d), clearing", len(_seen_keys))
        _seen_keys.clear()


def is_duplicate(key: str) -> bool:
    """该幂等键是否已记账。"""
    return key in _seen_keys


def mark_seen(key: str) -> None:
    """记账该幂等键。"""
    _evict_if_full()
    _seen_keys.add(key)


def reset_seen() -> None:
    """清空进程内去重表（测试用；生产不调用）。"""
    _seen_keys.clear()


def compute_new_mastery(current: float, evidence_type: str, score_or_result) -> float:
    """按证据类型算出新掌握度。

    复用 `PlanService.update_mastery`（与 `GraphCenter.update_masteries` 同一口径），
    只在其上补一个 `manual_correction` 分支的取值规则（先斩后奏裁决见返回值下方注释）：

    - `manual_correction`：人工纠正携带权威值 → **直接覆盖**（`score_or_result` 为准，
      缺省则保持原值）。P1 §4.5 把人工纠正列为强证据、`confidence=1.0`，语义是「覆盖」而非「累积」。
    """
    from app.services.plan_service import PlanService

    if evidence_type == TYPE_MANUAL_CORRECTION:
        if score_or_result is None:
            return current
        # bool 是 int 子类，`float(True)==1.0` 会静默把「打勾」当成掌握度 1.0；
        # 权威掌握度必须是数值，拒绝布尔（练习域的对错布尔另走下方分支）。
        if isinstance(score_or_result, bool):
            raise EvidenceContractError(
                "manual_correction 的 score_or_result 必须是数值（权威掌握度 0-1），不接受布尔"
            )
        try:
            asserted = float(score_or_result)
        except (TypeError, ValueError):
            raise EvidenceContractError(
                "manual_correction 的 score_or_result 必须是数值（权威掌握度 0-1）"
            )
        return round(min(max(asserted, 0.0), 1.0), 2)

    score = None
    if isinstance(score_or_result, bool):
        # 对错 → 演练算法语义：答对按当前值（不抬），答错由 exercise_failed 分支降。
        score = 1.0 if score_or_result else 0.0
    elif isinstance(score_or_result, (int, float)):
        score = float(score_or_result)

    return PlanService.update_mastery(current, evidence_type, score)


def apply_evidence(
    *,
    evidence_id: str,
    student_id: int,
    course_id: str,
    node_id: str,
    evidence_type: str,
    source_action: str,
    source_record_id: str,
    score_or_result=None,
    confidence=None,
    occurred_at: datetime | None = None,
    current_mastery: float = 0.0,
) -> dict:
    """校验 → 幂等判重 → 计算新掌握度，返回记账结果。

    幂等语义（P1 §4.4 规则 1）：重复提交 → **丢弃、不重复记账、不报错**，幂等返回首次结果。

    Returns:
        {evidence_id, idempotent_key, node_id, type, source_action, applied, effect,
         new_mastery, mastery_level, weak_evidence, explanation}
    """
    validate_combination(source_action, evidence_type)

    key = idempotent_key(
        student_id=student_id, course_id=course_id, node_id=node_id,
        source_action=source_action, source_record_id=source_record_id,
    )

    if is_duplicate(key):
        return {
            "evidence_id": evidence_id,
            "idempotent_key": key,
            "node_id": node_id,
            "type": evidence_type,
            "source_action": source_action,
            "applied": False,
            "effect": "duplicate_discarded",
            "new_mastery": None,
            "mastery_level": mastery_to_level(current_mastery),
            "weak_evidence": evidence_type in WEAK_TYPES,
            "explanation": (
                f"幂等命中：source_action={source_action} / source_record_id={source_record_id} "
                f"已记账，本次丢弃不重复计入掌握度。"
            ),
        }

    # 无节点归属的保留值：只记事实，不改掌握度。
    if node_id == NODE_NONE:
        mark_seen(key)
        return {
            "evidence_id": evidence_id,
            "idempotent_key": key,
            "node_id": node_id,
            "type": evidence_type,
            "source_action": source_action,
            "applied": True,
            "effect": "recorded_without_mastery",
            "new_mastery": None,
            "mastery_level": mastery_to_level(None),
            "weak_evidence": evidence_type in WEAK_TYPES,
            "explanation": f"证据无节点归属（node_id={NODE_NONE}），只记录事实，不影响任何节点掌握度。",
        }

    # 先算后记：`compute_new_mastery` 可能抛错（如 manual_correction 非数值），
    # 若先 `mark_seen` 会让被拒请求污染幂等表，改正后重提被误判为重复而静默丢弃。
    new_mastery = compute_new_mastery(current_mastery, evidence_type, score_or_result)
    mark_seen(key)

    return {
        "evidence_id": evidence_id,
        "idempotent_key": key,
        "node_id": node_id,
        "type": evidence_type,
        "source_action": source_action,
        "applied": True,
        "effect": "mastery_updated",
        "new_mastery": new_mastery,
        "mastery_level": mastery_to_level(new_mastery),
        "weak_evidence": evidence_type in WEAK_TYPES,
        "explanation": (
            f"来自 {source_action} 的 {evidence_type} 证据已记账："
            f"节点 {node_id} 掌握度 {round(current_mastery, 2)} → {new_mastery}。"
        ),
    }
