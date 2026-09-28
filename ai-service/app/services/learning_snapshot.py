"""LearningSnapshot 只读读模型（P1 §二，P2 Task 3 落地）。

零状态：上下文**全部由请求体携带** —— 不读 DB、不调 Java、不落库、不改计划或掌握度
（P1 §二 性质 / P2 §五 边界规则 1）。

本模块是**纯函数**，没有任何 IO：图谱数据由 API 层取好后传入（`graph_nodes` /
`recommended`），契约测试因此可以在不碰图服务的前提下冻结口径。

冻结口径来源：
- 五级 level / 边界阈值 → `app.services.mastery_scale`（唯一真源，**不得重算**）；
- 掌握度增量算法 → `PlanService.update_mastery`（本模块只读，不算）；
- 复习窗口 → 复用 `PlanService.get_half_life` + `PlanService.estimate_decay`
  与 `get_review_schedule` 的间隔公式（不另立阈值）；
- 画像富化 → `exercise_profile_service.enrich_profile`（纯计算，无 LLM）；
- 试点范围 → `app.services.pilot_scope`（唯一真源，**不得在此重写白名单**）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.services import mastery_scale
from app.services import pilot_scope
from app.services.exercise_profile_service import enrich_profile
from app.services.next_action import build_next_action
from app.services.plan_service import PlanService

logger = logging.getLogger("learning_snapshot")

# ── V1 冻结常量 ────────────────────────────────────────────────────

RECENT_EVIDENCE_LIMIT = 5    # P1 §2.4：固定取最近 N=5 条
WEAK_POINTS_LIMIT = 3        # P1 §2.5：weak_points 最多 3 条
INTERRUPTED_IDLE_DAYS = 7    # P2 D1 V1 冻结：paused 或空闲 > 7 天 → interrupted
REVIEW_DECAY_FLOOR = 0.7     # 与 `get_review_schedule` 同源：衰减到该值以下才算该复习

# `mastery.source`（P1 §2.3）
SOURCE_NODE_MASTERIES = "node_masteries"
SOURCE_PLAN_STEP_SNAPSHOT = "plan_step_snapshot"
SOURCE_NONE = "none"

# `current_node.reason`（P1 §2.2 V1 冻结优先级）
REASON_CURRENT_STEP_NODE = "current_step_node"
REASON_REVIEW_DUE = "review_due"
REASON_WEAKEST = "weakest"
REASON_NEXT_READY = "next_ready"

# `freshness` 的来源名（P1 §2.6）。顺序即 `computed_from` 的固定输出顺序，
# 保证同一输入永远给出同一串，便于契约测试与人工审计。
SOURCE_ACTIVE_PLAN = "active_plan"
SOURCE_MASTERY = "mastery"
SOURCE_PROFILE = "profile"
SOURCE_GRAPH = "graph"
ALL_SOURCES = (SOURCE_ACTIVE_PLAN, SOURCE_MASTERY, SOURCE_PROFILE, SOURCE_GRAPH)

# 步骤终态：不再占用「当前步骤」名额。
_TERMINAL_STEP_STATUS = ("completed", "skipped")


# ── 取属性：请求体里 steps 既可能是 dict 也可能是对象 ────────────────


def _step_attr(step, name: str, default=None):
    if isinstance(step, dict):
        value = step.get(name, default)
    else:
        value = getattr(step, name, default)
    return default if value is None else value


def _parse_dt(value) -> datetime | None:
    """ISO8601 字符串 / datetime → aware datetime；不可解析返回 None。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _days_idle(plan: dict, now: datetime) -> int:
    """计划空闲天数。

    与 `PlanCenter._days_idle` 同语义（services 不得反向依赖 centers，故此处镜像实现）。
    无法解析时间戳时视为 0（不误判为中断）。
    """
    last_activity = (plan or {}).get("last_activity_at")
    dt = _parse_dt(last_activity)
    if dt is None:
        return 0
    return (now - dt).days


# ── §2.1 active_plan ───────────────────────────────────────────────


def _open_steps(steps: list[dict]) -> list[dict]:
    open_steps = [s for s in (steps or []) if _step_attr(s, "status", "") not in _TERMINAL_STEP_STATUS]
    return sorted(open_steps, key=lambda s: _step_attr(s, "step_order", 0) or 0)


def _build_active_plan(plan: dict, steps: list[dict], now: datetime) -> dict | None:
    """计划元数据 + 当前未完成步骤 + 中断判定。空 plan → None。"""
    if not plan:
        return None

    current = _open_steps(steps)
    current = current[0] if current else None
    status = plan.get("status") or "in_progress"

    return {
        "plan_id": plan.get("id"),
        "title": plan.get("title") or "",
        "status": status,
        # 无未完成步骤 → null（P1 §2.1）
        "current_step": None if current is None else {
            "step_id": _step_attr(current, "id", 0) or 0,
            "order": _step_attr(current, "step_order", 0) or 0,
            "topic": _step_attr(current, "topic", "") or "",
            "node_id": _step_attr(current, "knowledge_node_id") or None,
            "status": _step_attr(current, "status", "") or "",
        },
        # paused 或空闲超阈值（P2 D1 = 7 天）
        "interrupted": status == "paused" or _days_idle(plan, now) > INTERRUPTED_IDLE_DAYS,
    }


# ── §2.2 current_node ──────────────────────────────────────────────


def _node_name(node_id: str, graph_nodes: list[dict]) -> str:
    for node in graph_nodes or []:
        if node.get("id") == node_id:
            return node.get("name") or node_id
    return node_id


def _review_due_candidates(
    steps: list[dict], masteries: dict[str, float], now: datetime,
) -> list[tuple[float, str]]:
    """已过复习窗口的节点 → `[(超期天数, node_id)]`，最紧急在前。

    衰减输入**只走请求级 map**（`masteries`，即 `node_masteries` 真源）：缺失 / 非数值
    记 `0.0`（未学习），**不读 `plan_steps.mastery_current` 快照**（D2 冻结：快照字段
    保留展示、不作计算输入，P1 §3.3 / P2 Task 1.5）。

    **与 `get_review_schedule` 同源但更严**（有意为之，非漂移）：

    - 同源部分：间隔公式（1 / 3 / `half_life * 1.3**(n-2)`）与
      `PlanService.get_half_life` 一致；衰减阈值 `decayed < REVIEW_DECAY_FLOOR`
      与 `get_review_schedule` 的 `decayed < 0.7` 同值。
    - **额外收紧**：本读模型还要求 `days_since >= interval`。
      `get_review_schedule` 的 `interval` 只进 `next_review_date`，而
      `days_until == interval <= days_ahead(7)` 恒真，故其**实际闸门仅为衰减**。
      差异场景：刚完成、掌握度低、衰减已 <0.7 但未满间隔的节点，
      `get_review_schedule` 会列、本读模型判「未到期」。
      收紧的理由：`current_node` 问的是「此刻最该做什么」，把一天内刚完成的
      节点报成「该复习了」对学习者没有意义（P1 §2.2 是**建议**而非台账）。

    只统计终态步骤（completed / review），避免把正在学的步骤误报为「该复习了」。
    `now` 由调用方注入（读模型整体可注入，便于契约测试与跨午夜稳定）。
    """
    today = now.date()
    overdue: list[tuple[float, str]] = []

    for step in steps or []:
        if _step_attr(step, "status", "") not in ("completed", "review"):
            continue
        node_id = _step_attr(step, "knowledge_node_id", "")
        if not node_id:
            continue
        last_review = _parse_dt(_step_attr(step, "last_review_at"))
        if last_review is None:
            continue

        difficulty = _step_attr(step, "topic_difficulty", 3) or 3
        review_count = _step_attr(step, "review_count", 0) or 0
        if review_count == 0:
            interval = 1
        elif review_count == 1:
            interval = 3
        else:
            interval = int(
                PlanService.get_half_life(difficulty, review_count) * (1.3 ** (review_count - 2))
            )

        days_since = (today - last_review.date()).days
        if days_since < interval:
            continue

        raw = (masteries or {}).get(node_id)
        mastery = float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else 0.0
        decayed = PlanService.estimate_decay(mastery, days_since, difficulty, review_count)
        if decayed >= REVIEW_DECAY_FLOOR:
            continue

        overdue.append((float(days_since - interval), node_id))

    overdue.sort(key=lambda item: (-item[0], item[1]))
    return overdue


def _weakest_node(masteries: dict[str, float]) -> str | None:
    """掌握度最低且 > 0 的节点（`<=0` 视为未学习，不进候选，P1 §3.5）。"""
    scored = [
        (float(v), nid)
        for nid, v in (masteries or {}).items()
        if isinstance(v, (int, float)) and not isinstance(v, bool) and float(v) > 0.0
    ]
    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], item[1]))
    return scored[0][1]


def _build_current_node(
    *, active_plan: dict | None, steps: list[dict], masteries: dict,
    graph_nodes: list[dict], recommended: list[dict], now: datetime,
) -> dict | None:
    """按 P1 §2.2 的 V1 冻结优先级取「当前或最需要处理的节点」。

    1. `current_step_node` —— 计划当前步骤绑定的 node_id（最优先）
    2. `review_due`        —— 已过复习窗口的节点
    3. `weakest`           —— 掌握度最低且 > 0 的节点
    4. `next_ready`        —— 先修已满足、排序最靠前的未学节点
    全部落空 → None（图谱为空或全部已掌握）。
    """
    # 1. 计划当前步骤绑定的节点
    if active_plan and active_plan.get("current_step"):
        node_id = active_plan["current_step"].get("node_id")
        if node_id:
            return {"node_id": node_id, "name": _node_name(node_id, graph_nodes),
                    "reason": REASON_CURRENT_STEP_NODE}

    # 2. 复习到期
    overdue = _review_due_candidates(steps, masteries, now)
    if overdue:
        node_id = overdue[0][1]
        return {"node_id": node_id, "name": _node_name(node_id, graph_nodes),
                "reason": REASON_REVIEW_DUE}

    # 3. 最薄弱
    weakest = _weakest_node(masteries)
    if weakest:
        return {"node_id": weakest, "name": _node_name(weakest, graph_nodes),
                "reason": REASON_WEAKEST}

    # 4. 可学的下一个（复用 GraphService.recommend_next_node 输出，已按排序给好）
    for candidate in recommended or []:
        node_id = candidate.get("node_id")
        if node_id:
            return {"node_id": node_id, "name": candidate.get("name") or _node_name(node_id, graph_nodes),
                    "reason": REASON_NEXT_READY}

    return None


# ── §2.3 mastery ───────────────────────────────────────────────────


def _step_mastery_snapshot(node_id: str, steps: list[dict]) -> float | None:
    """计划内冗余快照降级源（P1 §3.3：只作展示，非计算输入）。"""
    for step in steps or []:
        if _step_attr(step, "knowledge_node_id", "") != node_id:
            continue
        for key in ("mastery_current", "mastery_after"):
            value = _step_attr(step, key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
    return None


def _last_evidence_at(node_id: str | None, evidence: list[dict]) -> str | None:
    if not node_id:
        return None
    stamps = [
        _parse_dt(ev.get("occurred_at"))
        for ev in evidence or []
        if ev.get("node_id") == node_id
    ]
    stamps = [s for s in stamps if s is not None]
    if not stamps:
        return None
    return max(stamps).isoformat()


def _build_mastery(
    *, current_node: dict | None, steps: list[dict], masteries: dict, evidence: list[dict],
) -> dict:
    """当前节点的掌握度读值。

    `value == null` 表示**无记录 = 未学习**；与 `0.0` 在 level 上合并为
    `not_started`，但在 value 上保持可区分（P1 §3.4 注 / §3.5）。
    主源 = `node_masteries`；仅当主源无该键且计划内有快照时降级并如实标注（P1 §2.3）。
    """
    node_id = (current_node or {}).get("node_id")
    value: float | None = None

    if node_id:
        if node_id in (masteries or {}):
            raw = masteries[node_id]
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                value, source = float(raw), SOURCE_NODE_MASTERIES
            else:
                value, source = None, SOURCE_NONE
        else:
            snapshot = _step_mastery_snapshot(node_id, steps)
            if snapshot is None:
                value, source = None, SOURCE_NONE
            else:
                value, source = snapshot, SOURCE_PLAN_STEP_SNAPSHOT
    else:
        source = SOURCE_NONE

    return {
        "node_id": node_id,
        "value": value,
        "level": mastery_scale.mastery_to_level(value),
        "source": source,
        "last_evidence_at": _last_evidence_at(node_id, evidence),
    }


# ── §2.4 recent_evidence ───────────────────────────────────────────

# 无法解析（或缺失）occurred_at 的证据排到最后，而不是被丢弃。
_MIN_DT = datetime.min.replace(tzinfo=timezone.utc)


def _recent_evidence(evidence: list[dict], limit: int = RECENT_EVIDENCE_LIMIT) -> list[dict]:
    """按发生时刻倒序取最近 N 条（P1 §2.4：只含已落库、可追溯记录）。"""
    indexed = list(enumerate(evidence or []))
    indexed.sort(key=lambda pair: (_parse_dt(pair[1].get("occurred_at")) or _MIN_DT, -pair[0]),
                 reverse=True)
    return [item for _, item in indexed[:limit]]


# ── §2.5 profile_context ───────────────────────────────────────────


def _build_profile_context(
    *, student_id: int, student_profile: dict, recent_records: list[dict],
    session_analysis: dict, current_node_id: str | None,
) -> dict | None:
    """只取本次推荐真正需要的偏好/困难信息；**禁止**塞入完整画像（P1 §2.5）。"""
    has_input = bool(student_profile) or bool(recent_records) or bool(session_analysis)
    if not has_input:
        return None

    enriched = enrich_profile(
        user_id=student_id,
        student_profile=student_profile,
        recent_records=recent_records,
        session_analysis=session_analysis,
    )
    updated = enriched.get("updated_profile", {})

    skill_level = None
    node_skill = (updated.get("skill_levels") or {}).get(current_node_id or "", {})
    if isinstance(node_skill, dict):
        skill_level = node_skill.get("level")

    return {
        "weak_points": sorted(updated.get("weak_points") or [])[:WEAK_POINTS_LIMIT],
        "preferred_style": (student_profile or {}).get("preferred_style"),
        "skill_level": skill_level,
    }


# ── §2.6 freshness ─────────────────────────────────────────────────


def _build_freshness(
    *, plan: dict, masteries: dict, profile_context: dict | None,
    graph_nodes: list[dict], active_plan: dict | None, mastery: dict,
) -> dict:
    """如实反映数据来源与缺口（P1 §2.6）。

    `computed_from` 是 P1 可解释性的核心：回答「这个数字怎么来的」。
    `graph` 缺失的含义是「该课程的图谱不可用/为空」，不是「请求体没带这个字段」。
    """
    present = {
        SOURCE_ACTIVE_PLAN: bool(plan),
        SOURCE_MASTERY: bool(masteries),
        SOURCE_PROFILE: profile_context is not None,
        SOURCE_GRAPH: bool(graph_nodes),
    }
    # 中断的计划 + 降级快照源都意味着「手上的数不是当下的数」
    stale = bool(
        (active_plan and active_plan.get("interrupted"))
        or mastery.get("source") == SOURCE_PLAN_STEP_SNAPSHOT
    )
    return {
        "stale": stale,
        "missing_sources": [s for s in ALL_SOURCES if not present[s]],
        "computed_from": [s for s in ALL_SOURCES if present[s]],
    }


# ── 组装 ───────────────────────────────────────────────────────────


def build_snapshot(
    *,
    student_id: int,
    course_id: str,
    plan: dict,
    steps: list[dict],
    masteries: dict,
    recent_evidence: list[dict],
    student_profile: dict,
    recent_records: list[dict],
    session_analysis: dict,
    graph_nodes: list[dict] | None = None,
    graph_edges: list[dict] | None = None,
    recommended: list[dict] | None = None,
    now: datetime | None = None,
) -> dict:
    """组装只读读模型 `LearningSnapshot`（P1 §二）。纯函数，无副作用。"""
    now = now or datetime.now(timezone.utc)
    graph_nodes = graph_nodes or []
    evidence = _recent_evidence(recent_evidence)

    active_plan = _build_active_plan(plan, steps, now)
    current_node = _build_current_node(
        active_plan=active_plan, steps=steps, masteries=masteries,
        graph_nodes=graph_nodes, recommended=recommended or [], now=now,
    )
    mastery = _build_mastery(
        current_node=current_node, steps=steps, masteries=masteries, evidence=evidence,
    )
    profile_context = _build_profile_context(
        student_id=student_id, student_profile=student_profile,
        recent_records=recent_records, session_analysis=session_analysis,
        current_node_id=(current_node or {}).get("node_id"),
    )

    # P1 §五 的 next_action（Task 4）。入参全部复用上面的既有计算结果，
    # 图谱边由 API 层随 `graph_nodes` 一并传入（零新增 IO）。
    next_action = build_next_action(
        active_plan=active_plan,
        current_node=current_node,
        mastery=mastery,
        recent_evidence=evidence,
        steps=steps,
        graph_edges=graph_edges,
        masteries=masteries,
    )
    # 试点闸门（P2 Task 5 / 总纲 §5.5 第 1 条）：白名单外课程降级为旧行为 ——
    # 只置空建议，其余 9 键照常计算。判定是纯集合成员测试，不产生任何 IO。
    if not pilot_scope.is_pilot_course(course_id):
        next_action = None

    return {
        "student_id": student_id,
        "course_id": course_id,
        "generated_at": now.isoformat(),
        "active_plan": active_plan,
        "current_node": current_node,
        "mastery": mastery,
        "recent_evidence": evidence,
        "profile_context": profile_context,
        "freshness": _build_freshness(
            plan=plan, masteries=masteries, profile_context=profile_context,
            graph_nodes=graph_nodes, active_plan=active_plan, mastery=mastery,
        ),
        "next_action": next_action,
    }
