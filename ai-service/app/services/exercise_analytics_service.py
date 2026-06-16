"""Exercise analytics service.

Analyzes practice sessions and generates dashboard data. Pure computation —
no LLM calls, no I/O. Java passes in all data, Python returns computed results.
"""

import logging
from typing import Any

from app.services.plan_service import PlanService

logger = logging.getLogger(__name__)


def analyze_session(
    records: list[dict],
    masteries: dict[str, float],
    course_id: str = "ai_intro",
) -> dict:
    """Analyze a single practice session.

    Args:
        records: List of practice records, each with keys:
            knowledge_node_id, question, question_type, user_answer,
            correct_answer, is_correct, time_spent_seconds, difficulty.
        masteries: Current mastery map {node_id: mastery_value}.
        course_id: Course identifier.

    Returns:
        Dict with overall_score, per_node breakdown, weak_nodes, strengths,
        suggestions, and mastery_updates.
    """
    if not records:
        return {
            "overall_score": 0,
            "total_questions": 0,
            "correct_count": 0,
            "accuracy_pct": 0,
            "per_node": [],
            "weak_nodes": [],
            "strengths": [],
            "suggestions": [],
            "mastery_updates": [],
        }

    total = len(records)
    correct_count = sum(1 for r in records if r.get("is_correct", False))
    accuracy_pct = round(correct_count / total * 100) if total > 0 else 0

    # Per-node aggregation
    node_stats: dict[str, dict] = {}
    for r in records:
        nid = r.get("knowledge_node_id", "unknown")
        if nid not in node_stats:
            node_stats[nid] = {"correct": 0, "total": 0, "difficulty_sum": 0}
        node_stats[nid]["total"] += 1
        node_stats[nid]["difficulty_sum"] += r.get("difficulty", 1)
        if r.get("is_correct", False):
            node_stats[nid]["correct"] += 1

    # Mastery updates via half-life decay model
    mastery_updates: list[dict] = []
    mastery_events: list[dict] = []
    for nid, stats in node_stats.items():
        old_mastery = masteries.get(nid, 0.0)
        node_records = [r for r in records if r.get("knowledge_node_id") == nid]

        current = old_mastery
        for r in node_records:
            if r.get("is_correct", False):
                current = PlanService.update_mastery(
                    current, "exercise_done", score=0.8
                )
                mastery_events.append({
                    "node_id": nid,
                    "event_type": "exercise_done",
                    "score": 0.8,
                })
            else:
                current = PlanService.update_mastery(current, "exercise_failed")
                mastery_events.append({
                    "node_id": nid,
                    "event_type": "exercise_failed",
                })

        current = round(current, 2)
        if abs(current - old_mastery) > 0.001:
            mastery_updates.append({
                "knowledge_node_id": nid,
                "old_mastery": old_mastery,
                "new_mastery": current,
            })

    # Per-node results
    per_node: list[dict] = []
    weak_nodes: list[dict] = []
    strengths: list[dict] = []
    for nid, stats in node_stats.items():
        node_accuracy = round(stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0
        avg_difficulty = round(stats["difficulty_sum"] / stats["total"], 1) if stats["total"] > 0 else 1
        current_mastery = masteries.get(nid, 0.0)

        entry = {
            "knowledge_node_id": nid,
            "accuracy": node_accuracy,
            "total": stats["total"],
            "correct": stats["correct"],
            "avg_difficulty": avg_difficulty,
            "current_mastery": current_mastery,
        }
        per_node.append(entry)

        if node_accuracy < 60:
            weak_nodes.append({"knowledge_node_id": nid, "current_mastery": current_mastery})
        elif node_accuracy >= 80:
            strengths.append({"knowledge_node_id": nid})

    # Suggestions
    suggestions: list[str] = []
    if accuracy_pct < 50:
        suggestions.append("建议重点复习薄弱知识点，重新学习基础内容后再练习")
    elif accuracy_pct < 75:
        suggestions.append("建议针对薄弱模块进行针对性练习")
    if weak_nodes:
        suggestions.append(f"薄弱知识点: {', '.join(n['knowledge_node_id'] for n in weak_nodes[:3])}")
    if accuracy_pct >= 85:
        suggestions.append("掌握良好，建议挑战更高难度的内容")

    return {
        "overall_score": accuracy_pct,
        "total_questions": total,
        "correct_count": correct_count,
        "accuracy_pct": accuracy_pct,
        "per_node": per_node,
        "weak_nodes": weak_nodes,
        "strengths": strengths,
        "suggestions": suggestions,
        "mastery_updates": mastery_updates,
        "mastery_events": mastery_events,  # 可直接喂给 POST /graph/masteries 的 events 字段
    }


def get_dashboard(
    user_id: int,
    masteries: dict[str, float],
    recent_records: list[dict],
    course_id: str = "ai_intro",
) -> dict:
    """Generate exercise dashboard overview.

    Args:
        user_id: User ID.
        masteries: Current mastery map.
        recent_records: Recent practice records (Java provides the time window).
        course_id: Course identifier.

    Returns:
        Dashboard dict with total stats, weak/strong nodes, mastery trend, recommendations.
    """
    total = len(recent_records)
    correct = sum(1 for r in recent_records if r.get("is_correct", False))
    avg_accuracy = round(correct / total * 100) if total > 0 else 0

    # Node-level aggregation
    node_correct: dict[str, int] = {}
    node_total: dict[str, int] = {}
    for r in recent_records:
        nid = r.get("knowledge_node_id", "unknown")
        node_correct[nid] = node_correct.get(nid, 0) + (1 if r.get("is_correct") else 0)
        node_total[nid] = node_total.get(nid, 0) + 1

    # Weak / strong split
    weak_nodes: list[dict] = []
    strong_nodes: list[dict] = []
    for nid in set(list(node_total.keys())):
        acc = round(node_correct.get(nid, 0) / max(node_total.get(nid, 0), 1) * 100)
        entry = {"knowledge_node_id": nid, "accuracy": acc, "total": node_total[nid]}
        if acc < 60:
            weak_nodes.append(entry)
        elif acc >= 80:
            strong_nodes.append(entry)

    # Simple mastery trend: average mastery across all nodes
    if masteries:
        avg_mastery = round(sum(masteries.values()) / len(masteries), 2)
    else:
        avg_mastery = 0.0

    # Recommended nodes: weak nodes sorted by lowest accuracy
    weak_sorted = sorted(weak_nodes, key=lambda x: x["accuracy"])
    recommended_nodes = [
        {"knowledge_node_id": n["knowledge_node_id"], "reason": f"正确率仅 {n['accuracy']}%，需要加强练习"}
        for n in weak_sorted[:5]
    ]

    # Streak (simplified — Java should compute real streak from DB timestamps)
    streak_days = _estimate_streak(recent_records)

    return {
        "total_exercises_done": total,
        "avg_accuracy": avg_accuracy,
        "avg_mastery": avg_mastery,
        "streak_days": streak_days,
        "weak_nodes": weak_sorted[:5],
        "strong_nodes": strong_nodes[:5],
        "recommended_nodes": recommended_nodes,
    }


def _estimate_streak(records: list[dict]) -> int:
    """Return 0 — streak computation requires timestamps from Java DB."""
    return 0
