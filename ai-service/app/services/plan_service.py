"""计划引擎服务 — 动态半衰期、软着陆、穿插重排、掌握度更新、联动机制"""

import logging
import math
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.services.java_api_client import get_java_client
from app.services.plan_constants import RETURN_MESSAGES

logger = logging.getLogger(__name__)

_HALF_LIFE_BASE = {1: 14, 2: 10, 3: 7, 4: 5, 5: 3}


def _step_attr(step, name: str, default=None):
    """安全获取 step 属性/键，兼容 dict 和 object"""
    if isinstance(step, dict):
        return step.get(name, default)
    return getattr(step, name, default)


class PlanService:
    """计划引擎 — 纯算法 + Java API 调用（不调 LLM）"""

    def __init__(self):
        self._client = get_java_client()

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
            mastery = _step_attr(s, "mastery_current", 0) or 0
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
                    return (_step_attr(s, "mastery_current", 0) or 0,
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

    # ── 6.2 联动机制 ──────────────────────────────────────────

    async def on_node_status_change(self, user_id: int, node_id: str,
                                     old_status: str, new_status: str,
                                     plan_id: int = None) -> dict:
        if new_status != "forgotten":
            return {"action": "none", "reason": f"status {new_status} 不需要调整计划"}

        try:
            result = await self._client.on_node_status_change(
                user_id, node_id, old_status, new_status, plan_id,
            )
            if result:
                return result
            return {"action": "none", "reason": "Java API 返回空"}
        except Exception as e:
            logger.error(f"Failed to handle node status change: {e}")
            return {"action": "none", "reason": f"调用 Java API 失败: {e}"}


_plan_service_singleton = None
_plan_service_lock = threading.Lock()


def get_plan_service() -> PlanService:
    global _plan_service_singleton
    if _plan_service_singleton is None:
        with _plan_service_lock:
            if _plan_service_singleton is None:
                _plan_service_singleton = PlanService()
    return _plan_service_singleton
