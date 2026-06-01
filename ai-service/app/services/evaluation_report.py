import logging
from typing import Optional

logger = logging.getLogger(__name__)


def generate_report(evaluation_results: dict, student_profile: Optional[dict] = None) -> dict:
    results = evaluation_results.get("results", [])
    overall = evaluation_results.get("overall_score", 0)
    weak_modules = evaluation_results.get("weak_modules", [])

    dimension_scores = {}
    for r in results:
        mod = r.get("module", "general")
        if mod not in dimension_scores:
            dimension_scores[mod] = {"earned": 0, "max": 0}
        dimension_scores[mod]["earned"] += r.get("earned", 0)
        dimension_scores[mod]["max"] += r.get("max_score", 0)

    dimensions = {
        mod: round(scores["earned"] / scores["max"] * 100) if scores["max"] > 0 else 0
        for mod, scores in dimension_scores.items()
    }

    suggestions = []
    if overall < 60:
        suggestions.append("整体掌握程度较低，建议重新学习基础内容")
    elif overall < 80:
        suggestions.append("整体掌握良好，建议针对弱项模块深入练习")
    else:
        suggestions.append("整体掌握优秀，可以挑战更高难度的内容")

    for mod in weak_modules:
        mod_score = dimensions.get(mod, 0)
        suggestions.append(f"模块「{mod}」得分较低({mod_score}分)，建议重点复习相关知识点")

    profile_weak_points = []
    if student_profile:
        existing = student_profile.get("weak_points") or []
        profile_weak_points = list(existing)
        for mod in weak_modules:
            if mod not in profile_weak_points:
                profile_weak_points.append(mod)

    report = {
        "overall_score": overall,
        "dimension_scores": dimensions,
        "weak_modules": weak_modules,
        "suggestions": suggestions,
        "results": results,
        "total_questions": len(results),
        "correct_count": sum(
            1 for r in results
            if (r["correct"] if "correct" in r else r.get("score", 0) >= 60)
        ),
        "recommended_weak_points": profile_weak_points,
    }

    return report
