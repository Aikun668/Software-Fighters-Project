"""计划引擎服务 — 动态半衰期、软着陆、穿插重排、掌握度更新（纯算法）"""

import logging
import math
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.services.plan_constants import RETURN_MESSAGES

logger = logging.getLogger(__name__)

_HALF_LIFE_BASE = {1: 14, 2: 10, 3: 7, 4: 5, 5: 3}


def _step_attr(step, name: str, default=None):
    """安全获取 step 属性/键，兼容 dict 和 object"""
    if isinstance(step, dict):
        return step.get(name, default)
    return getattr(step, name, default)


class PlanService:
    """计划引擎 — 纯算法（不调 LLM，不调 Java）"""

    # ── 5.4.1 动态半衰期 ──────────────────────────────────────

    @staticmethod
    def get_half_life(topic_difficulty: int, review_count: int = 0) -> float:
        base = _HALF_LIFE_BASE.get(topic_difficulty, 7)
        repetition_bonus = min(review_count * 0.5, 7)
        return base + repetition_bonus

    @staticmethod
    def estimate_decay(initial_mastery: float, days_since_review: int,
                       topic_difficulty: int = 3, review_count: int = 0) -> float:
        half_life = PlanService.get_half_life(topic_difficulty, review_count)
        decay = math.exp(-0.693 * days_since_review / half_life)
        return round(max(0.0, min(1.0, initial_mastery * decay)), 2)

    # ── 5.4.2 软着陆机制 ──────────────────────────────────────

    @staticmethod
    def soft_landing(paused_steps: list, days_idle: int) -> dict:
        if days_idle <= 3:
            return {
                "strategy": "continue", "message": RETURN_MESSAGES["short"],
                "review_nodes": [], "decay_results": {},
            }

        decay_results = {}
        for s in paused_steps:
            topic_name = _step_attr(s, "topic", "")
            mastery = _step_attr(s, "mastery", 0) or 0
            difficulty = _step_attr(s, "topic_difficulty", 3) or 3
            review_count = _step_attr(s, "review_count", 0) or 0

            decayed = PlanService.estimate_decay(mastery, days_idle, difficulty, review_count)
            if decayed < 0.6:
                decay_results[topic_name] = "review" if decayed < 0.3 else "review_light"

        if days_idle <= 7:
            key_node = PlanService._find_most_critical(paused_steps)
            return {
                "strategy": "warmup", "message": RETURN_MESSAGES["medium"],
                "review_nodes": [key_node], "decay_results": decay_results,
            }

        def _get_step_data(topic_name: str):
            for s in paused_steps:
                if _step_attr(s, "topic", "") == topic_name:
                    return (_step_attr(s, "mastery", 0) or 0,
                            _step_attr(s, "topic_difficulty", 3) or 3)
            return 0, 3

        priority = sorted(
            decay_results.keys(),
            key=lambda t: PlanService.estimate_decay(
                initial_mastery=_get_step_data(t)[0],
                days_since_review=days_idle,
                topic_difficulty=_get_step_data(t)[1],
            ),
        )[:3]

        return {
            "strategy": "regression_check", "message": RETURN_MESSAGES["long"],
            "review_nodes": priority, "decay_results": decay_results,
        }

    @staticmethod
    def _find_most_critical(paused_steps: list) -> str:
        best = None
        best_score = -1
        for s in paused_steps:
            topic = _step_attr(s, "topic", "")
            difficulty = _step_attr(s, "topic_difficulty", 3) or 3
            if difficulty > best_score:
                best_score = difficulty
                best = topic
        return best or ""

    # ── 5.4.3 动态重排 ────────────────────────────────────────

    @staticmethod
    def reorder_plan(plan_steps: list, decay_results: dict,
                     days_idle: int, user_daily_capacity: int = 5,
                     current_topic: str = "", goal_topic: str = "") -> list:
        review_needed = [t for t, r in decay_results.items() if r in ("review", "review_light")]

        severe = [t for t in review_needed if decay_results[t] == "review"]
        light = [t for t in review_needed if decay_results[t] == "review_light"]

        if days_idle <= 7:
            review_steps = PlanService._build_review_steps(light, mode="quick")
            return PlanService._interleave(review_steps, plan_steps, ratio=1 / 3)
        elif days_idle <= 21:
            severe_steps = PlanService._build_review_steps(severe, mode="full")
            light_steps = PlanService._build_review_steps(light, mode="quick")
            return severe_steps + PlanService._interleave(light_steps, plan_steps, ratio=1 / 4)
        else:
            if current_topic and goal_topic:
                try:
                    from app.services.graph_service import get_graph_service
                    gs = get_graph_service()
                    critical_path = gs.get_critical_path(current_topic, goal_topic)
                    if critical_path:
                        topic_to_node = {}
                        for s in plan_steps:
                            node_id = _step_attr(s, "knowledge_node_id", "")
                            topic = _step_attr(s, "topic", "")
                            if node_id:
                                topic_to_node[topic] = node_id

                        critical_review = []
                        other_review = []
                        for t in review_needed:
                            node_id = topic_to_node.get(t, "")
                            if node_id in critical_path:
                                critical_review.append(t)
                            else:
                                other_review.append(t)

                        critical_steps = PlanService._build_review_steps(critical_review, mode="full")
                        other_steps = PlanService._build_review_steps(other_review, mode="quick")
                        return critical_steps + PlanService._interleave(other_steps, plan_steps, ratio=1 / 3)
                except (ImportError, AttributeError, ValueError):
                    logger.warning("Failed to use critical_path for reorder, falling back", exc_info=True)
            all_review = PlanService._build_review_steps(severe + light, mode="full")
            return all_review + plan_steps

    @staticmethod
    def _interleave(review_steps: list, plan_steps: list, ratio: float = 1 / 3) -> list:
        result = []
        r_idx = 0
        insert_every = int(1 / ratio)

        for i, step in enumerate(plan_steps):
            if i > 0 and i % insert_every == 0 and r_idx < len(review_steps):
                result.append(review_steps[r_idx])
                r_idx += 1
            result.append(step)

        if r_idx < len(review_steps):
            result.extend(review_steps[r_idx:])

        return result

    @staticmethod
    def _build_review_steps(topics: list, mode: str = "quick") -> list:
        steps = []
        for topic in topics:
            if mode == "quick":
                steps.append({
                    "topic": topic, "type": "quick_review",
                    "description": f"快速回顾 {topic}", "status": "review",
                })
            else:
                steps.append({
                    "topic": topic, "type": "full_review",
                    "description": f"重新学习 {topic}", "status": "review",
                })
        return steps

    # ── 5.4.4 多事件掌握度更新 ─────────────────────────────────

    @staticmethod
    def update_mastery(current: float, event_type: str, score: Optional[float] = None) -> float:
        if event_type == "resource_viewed":
            return round(min(current + 0.1, 0.6), 2)
        elif event_type == "exercise_done":
            target = score if score is not None else current
            return round(current + (target - current) * 0.4, 2)
        elif event_type == "exercise_failed":
            return round(max(current - 0.2, 0.0), 2)
        elif event_type == "tutor_question_asked":
            return round(min(current + 0.05, 1.0), 2)
        return current

    # ── Phase 3: 间隔重复提醒 ─────────────────────────────────

    @staticmethod
    def get_review_schedule(steps: list, days_ahead: int = 7) -> list[dict]:
        today = datetime.now(timezone.utc).date()
        schedule = []

        for step in steps:
            status = _step_attr(step, "status", "")
            if status not in ("completed", "review"):
                continue

            topic = _step_attr(step, "topic", "")
            difficulty = _step_attr(step, "topic_difficulty", 3) or 3
            review_count = _step_attr(step, "review_count", 0) or 0
            mastery = _step_attr(step, "mastery_current", 0) or 0
            last_review = _step_attr(step, "last_review_at")
            node_id = _step_attr(step, "knowledge_node_id", "")
            step_id = _step_attr(step, "id", 0)

            if last_review and hasattr(last_review, "date"):
                days_since = (today - last_review.date()).days
            elif isinstance(last_review, datetime):
                days_since = (today - last_review.date()).days
            elif isinstance(last_review, str):
                try:
                    dt = datetime.fromisoformat(last_review)
                    days_since = (today - dt.date()).days
                except (ValueError, TypeError):
                    days_since = 999
            else:
                days_since = 999

            half_life = PlanService.get_half_life(difficulty, review_count)

            if review_count == 0:
                interval = 1
            elif review_count == 1:
                interval = 3
            else:
                interval = int(half_life * (1.3 ** (review_count - 2)))

            next_review_date = today + timedelta(days=interval)
            decayed = PlanService.estimate_decay(mastery, days_since, difficulty, review_count)

            if decayed < 0.7:
                days_until = (next_review_date - today).days
                if 0 <= days_until <= days_ahead:
                    schedule.append({
                        "step_id": step_id,
                        "topic": topic,
                        "knowledge_node_id": node_id,
                        "current_mastery": mastery,
                        "decayed_mastery": decayed,
                        "review_count": review_count,
                        "next_review_date": next_review_date.isoformat(),
                        "days_until_review": days_until,
                        "urgency": "high" if decayed < 0.3 else ("medium" if decayed < 0.6 else "low"),
                    })

        return sorted(schedule, key=lambda s: s["days_until_review"])

    # ── 计划端点纯算法（从 internal_api 收口迁入） ──────────────

    @staticmethod
    def compute_next_milestone(plan: dict, completed_steps: int) -> dict | None:
        """下一个里程碑信息。兼容字符串格式 milestone（无法定位顺序 → None）。"""
        milestones = plan.get("milestones") or []
        if not milestones:
            return None
        if isinstance(milestones[0], str):
            return None
        for m in sorted(
            milestones,
            key=lambda x: x.get("after_step", 999) if isinstance(x, dict) else 999,
        ):
            if not isinstance(m, dict):
                continue
            if m.get("after_step", 0) > completed_steps:
                return {
                    "milestone_id": m.get("milestone_id", ""),
                    "description": m.get("description", ""),
                    "after_step": m.get("after_step", 0),
                    "steps_remaining": m.get("after_step", 0) - completed_steps,
                }
        return None

    @staticmethod
    def build_milestone_progress(completed_steps: int, next_milestone: dict | None) -> dict | None:
        if not next_milestone:
            return None
        target = next_milestone["after_step"]
        return {
            "current": completed_steps,
            "target": target,
            "remaining": next_milestone["steps_remaining"],
            "pct": round(completed_steps / target * 100) if target > 0 else 100,
        }

    @staticmethod
    def _today_step_entry(
        step: dict, *, estimated_days: int, day_progress: int, day_total: int,
        masteries: dict,
    ) -> dict:
        nid = step.get("knowledge_node_id", "")
        return {
            "step_order": step.get("step_order", 0),
            "topic": step.get("topic", ""),
            "knowledge_node_id": nid,
            "status": step.get("status", "pending"),
            "estimated_days": estimated_days,
            "topic_difficulty": step.get("topic_difficulty", 3),
            "suggested_resource_types": step.get("suggested_resource_types", ["document", "exercise"]),
            "day_progress": day_progress,
            "day_total": day_total,
            "current_mastery": masteries.get(nid) if nid else None,
        }

    @staticmethod
    def select_today_steps(
        steps: list[dict], *, day_index: int, completed_steps: int, total_steps: int,
        masteries: dict,
    ) -> list[dict]:
        """按累计 estimated_days 划分每日步骤，返回 day_index 当天应做的步骤。

        无命中且计划未完成时兜底返回下一个待完成步骤（带 note 标记）。
        """
        cumulative = 0
        today_steps: list[dict] = []
        for s in sorted(steps, key=lambda x: x.get("step_order", 999)):
            est = max(s.get("estimated_days", 1), 1)
            step_start_day = cumulative
            step_end_day = cumulative + est
            if step_start_day <= day_index < step_end_day:
                today_steps.append(PlanService._today_step_entry(
                    s, estimated_days=est,
                    day_progress=day_index - step_start_day + 1, day_total=est,
                    masteries=masteries,
                ))
            cumulative = step_end_day

        if not today_steps and completed_steps < total_steps:
            pending = [s for s in steps if s.get("status") not in ("completed",)]
            if pending:
                entry = PlanService._today_step_entry(
                    pending[0], estimated_days=pending[0].get("estimated_days", 1),
                    day_progress=1, day_total=1, masteries=masteries,
                )
                entry["note"] = "计划进度落后，显示下一个待完成步骤"
                today_steps.append(entry)
        return today_steps

    @staticmethod
    def build_resource_suggestions(today_steps: list[dict]) -> list[dict]:
        """为今日步骤生成可直接调用的资源生成 prompt。"""
        return [
            {
                "step_order": ts["step_order"],
                "topic": ts["topic"],
                "knowledge_node_id": ts.get("knowledge_node_id"),
                "resource_types": ts.get("suggested_resource_types", []),
                "gen_prompt": (
                    f"请为「{ts['topic']}」生成学习资源，"
                    f"难度等级 {ts.get('topic_difficulty', 3)}/5"
                ),
            }
            for ts in today_steps
        ]

    @staticmethod
    def find_step(steps: list[dict], *, step_id: int, step_order: int) -> tuple[dict | None, int]:
        """定位目标步骤，step_id 优先于 step_order。返回 (step, index)。"""
        for i, s in enumerate(steps):
            if step_id and step_id > 0 and s.get("id") == step_id:
                return s, i
            if step_order and step_order > 0 and s.get("step_order") == step_order:
                return s, i
        return None, -1

    @staticmethod
    def apply_node_status_change(
        *, steps: list[dict], node_id: str, new_status: str, old_status: str,
        masteries: dict, plan_status: str,
    ) -> dict:
        """图谱节点状态变化 → 计划步骤联动（4 分支决策表 + 计划完成判定）。"""
        affected_steps = [s for s in steps if s.get("knowledge_node_id", "") == node_id]
        plan_actions: list[dict] = []
        updated_steps = list(steps)

        for s in affected_steps:
            old_step_status = s.get("status", "")
            current_mastery = masteries.get(node_id, 0.0)

            if new_status == "mastered":
                new_step_status = "completed"
                action = "mark_completed"
                action_msg = f"步骤「{s.get('topic')}」对应节点已掌握，建议标记为完成"
                extra = {}
            elif new_status == "forgotten":
                new_step_status = "review"
                action = "schedule_review"
                decayed = PlanService.estimate_decay(
                    current_mastery, days_since_review=14,
                    topic_difficulty=s.get("topic_difficulty", 3),
                )
                action_msg = f"步骤「{s.get('topic')}」对应节点已遗忘（掌握度 {decayed}），建议安排复习"
                extra = {"decayed_mastery": decayed}
            elif new_status == "learning" and old_status in ("locked", ""):
                new_step_status = "pending"
                action = "unlock_step"
                action_msg = f"步骤「{s.get('topic')}」前置条件满足，已解锁"
                extra = {}
            elif new_status == "locked":
                new_step_status = "locked"
                action = "lock_step"
                action_msg = f"步骤「{s.get('topic')}」前置条件不满足，已重新锁定"
                extra = {}
            else:
                continue

            plan_actions.append({
                "step_order": s.get("step_order"),
                "topic": s.get("topic"),
                "action": action,
                "old_status": old_step_status,
                "new_status": new_step_status,
                **extra,
                "message": action_msg,
            })

            for i, us in enumerate(updated_steps):
                if us.get("step_order") == s.get("step_order"):
                    updated_steps[i] = {
                        **us, "status": new_step_status, "mastery_current": current_mastery,
                    }
                    break

        completed_count = sum(1 for s in updated_steps if s.get("status") == "completed")
        total = len(updated_steps)
        final_status = plan_status
        if completed_count >= total and plan_status != "completed":
            final_status = "completed"
            plan_actions.append({
                "step_order": 0,
                "topic": "",
                "action": "complete_plan",
                "old_status": plan_status,
                "new_status": "completed",
                "message": "所有步骤已完成，建议将计划标记为完成",
            })

        return {
            "affected_steps_count": len(affected_steps),
            "plan_actions": plan_actions,
            "updated_steps": updated_steps,
            "plan_status": final_status,
            "completed_steps": completed_count,
            "total_steps": total,
        }

    @staticmethod
    def summarize_review_schedule(schedule: list[dict]) -> dict:
        return {
            "high": sum(1 for s in schedule if s.get("urgency") == "high"),
            "medium": sum(1 for s in schedule if s.get("urgency") == "medium"),
        }


_plan_service_singleton = None
_plan_service_lock = threading.Lock()


def get_plan_service() -> PlanService:
    global _plan_service_singleton
    if _plan_service_singleton is None:
        with _plan_service_lock:
            if _plan_service_singleton is None:
                _plan_service_singleton = PlanService()
    return _plan_service_singleton
