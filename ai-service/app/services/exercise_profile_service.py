"""Exercise profile enrichment service.

Merges exercise analytics results into the student profile, refining weak_points,
strong_points, skill_levels, and suggested_focus for better personalization.
Pure computation — no LLM calls.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

_MIN_MASTERY_DELTA = 0.02  # Minimum change to consider a mastery update meaningful


def enrich_profile(
    user_id: int,
    student_profile: dict | None = None,
    recent_records: list[dict] | None = None,
    session_analysis: dict | None = None,
) -> dict:
    """Enrich student profile with exercise-derived signals.

    Args:
        user_id: User ID.
        student_profile: Current student profile dict (from Java).
        recent_records: Recent practice records.
        session_analysis: Output from analyze_session().

    Returns:
        Dict with updated_profile containing:
            weak_points, strong_points, skill_levels, suggested_focus.
    """
    profile = student_profile or {}
    records = recent_records or []
    analysis = session_analysis or {}

    # ── Extract existing state ──────────────────────────────
    existing_weak = profile.get("weak_points") or []
    if not isinstance(existing_weak, list):
        existing_weak = []
    existing_strong = profile.get("strong_points") or []
    if not isinstance(existing_strong, list):
        existing_strong = []
    skill_levels = profile.get("skill_levels") or {}
    if not isinstance(skill_levels, dict):
        skill_levels = {}

    # ── Merge weak_points ───────────────────────────────────
    analysis_weak = analysis.get("weak_nodes", [])
    new_weak_ids = {w.get("knowledge_node_id", "") for w in analysis_weak if w.get("knowledge_node_id")}
    existing_weak_ids = {
        w if isinstance(w, str) else w.get("knowledge_node_id", "")
        for w in existing_weak
    }
    merged_weak_ids = existing_weak_ids | new_weak_ids
    # Remove nodes that became strong
    analysis_strong_ids = {s.get("knowledge_node_id", "") for s in analysis.get("strengths", [])}
    final_weak_ids = merged_weak_ids - analysis_strong_ids

    # ── Merge strong_points ─────────────────────────────────
    new_strong_ids = {s.get("knowledge_node_id", "") for s in analysis.get("strengths", []) if s.get("knowledge_node_id")}
    existing_strong_ids = {
        s if isinstance(s, str) else s.get("knowledge_node_id", "")
        for s in existing_strong
    }
    final_strong_ids = existing_strong_ids | new_strong_ids
    # Remove nodes that became weak
    final_strong_ids = final_strong_ids - final_weak_ids

    # ── Update skill_levels by category ─────────────────────
    per_node = analysis.get("per_node", [])
    for pn in per_node:
        nid = pn.get("knowledge_node_id", "")
        acc = pn.get("accuracy", 0)
        # Simple mapping: accuracy-based level
        # 阈值与 P1 §3.4 的 proficient 下界 0.6 / mastered 下界 0.85 对齐（百分制）
        if acc >= 85:
            level = "proficient"
        elif acc >= 60:
            level = "developing"
        else:
            level = "beginner"
        skill_levels[nid] = {
            "level": level,
            "accuracy": acc,
            "total_exercises": pn.get("total", 0),
        }

    # ── Generate suggested_focus ────────────────────────────
    mastery_updates = analysis.get("mastery_updates", [])
    suggested_focus: list[dict] = []

    # Weak nodes first (lowest mastery first)
    for w in sorted(
        [w for w in analysis_weak if w.get("knowledge_node_id") in final_weak_ids],
        key=lambda x: x.get("current_mastery", 0),
    )[:5]:
        suggested_focus.append({
            "knowledge_node_id": w["knowledge_node_id"],
            "reason": "薄弱环节，需要重点复习",
            "priority": "high",
        })

    # Nodes with significant positive mastery change → keep reinforcing
    for mu in mastery_updates:
        delta = mu.get("new_mastery", 0) - mu.get("old_mastery", 0)
        nid = mu.get("knowledge_node_id", "")
        if delta > _MIN_MASTERY_DELTA and nid not in {s["knowledge_node_id"] for s in suggested_focus}:
            suggested_focus.append({
                "knowledge_node_id": nid,
                "reason": f"正在进步中（+{delta:.0%}），建议继续巩固",
                "priority": "medium",
            })

    return {
        "updated_profile": {
            "weak_points": sorted(final_weak_ids),
            "strong_points": sorted(final_strong_ids),
            "skill_levels": skill_levels,
            "suggested_focus": suggested_focus[:5],
        }
    }
