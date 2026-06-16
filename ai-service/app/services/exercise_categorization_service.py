"""Exercise categorization service.

Matches exercises to knowledge graph nodes using LLM semantic matching.
Used by Java when saving exercises from chat to the exercise library.
"""

import json
import logging
from typing import Any

from app.services.llm_service import get_llm_service
from app.utils.json_parser import parse_llm_json
from app.utils.prompt_loader import build_prompt, load_prompt_file, interpolate_variables

logger = logging.getLogger(__name__)

_VALID_TYPES = {"choice", "short_answer"}


def _normalize_result(raw: dict, index: int) -> dict:
    """Validate and coerce a single categorization result."""
    raw_id = raw.get("knowledge_node_id")
    knowledge_node_id = str(raw_id).strip() if raw_id is not None else ""
    if not knowledge_node_id or knowledge_node_id.lower() == "none":
        knowledge_node_id = "unknown"

    try:
        difficulty = int(raw.get("difficulty", 3))
    except (TypeError, ValueError):
        difficulty = 3
    difficulty = max(1, min(5, difficulty))

    question_type = str(raw.get("question_type", "choice")).lower().strip()
    if question_type not in _VALID_TYPES:
        question_type = "choice"

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return {
        "index": index,
        "knowledge_node_id": knowledge_node_id,
        "difficulty": difficulty,
        "question_type": question_type,
        "confidence": round(confidence, 4),
    }


async def categorize_exercises(
    exercises: list[dict],
    knowledge_nodes: list[dict],
    course_id: str = "ai_intro",
) -> list[dict]:
    """Match each exercise to the best-fit knowledge graph node.

    Args:
        exercises: List of exercise dicts with keys: question, answer, question_type, options.
        knowledge_nodes: List of knowledge node dicts with keys: id, name, description.
        course_id: Course identifier (currently unused, kept for API symmetry).

    Returns:
        List of result dicts with keys: index, knowledge_node_id, difficulty,
        question_type, confidence.
    """
    if not exercises:
        return []

    slim_nodes = [
        {"id": n.get("id", ""), "name": n.get("name", ""), "description": n.get("description", "")}
        for n in knowledge_nodes
    ]

    variables = {
        "exercises_json": json.dumps(exercises, ensure_ascii=False, indent=2),
        "knowledge_nodes_json": json.dumps(slim_nodes, ensure_ascii=False, indent=2),
    }

    try:
        system_prompt = build_prompt("exercise_categorize", key="system")
        user_template = load_prompt_file("exercise_categorize", key="user_template")
        user_prompt = interpolate_variables(user_template, variables)
    except Exception as exc:
        logger.warning(f"Failed to build categorization prompt: {exc}")
        return _fallback_results(exercises)

    try:
        llm = get_llm_service()
        response = await llm.chat(
            [{"role": "user", "content": user_prompt}],
            system_prompt=system_prompt,
        )
    except Exception as exc:
        logger.warning(f"LLM call failed during exercise categorization: {exc}")
        return _fallback_results(exercises)

    try:
        data = parse_llm_json(response, fallback={}, expected_key="results")
    except Exception as exc:
        logger.warning(f"Failed to parse categorization response: {exc}")
        return _fallback_results(exercises)

    if not isinstance(data, dict):
        return _fallback_results(exercises)

    raw_results = data.get("results", [])
    if not isinstance(raw_results, list):
        return _fallback_results(exercises)

    results: list[dict] = []
    for i, raw in enumerate(raw_results):
        if isinstance(raw, dict):
            results.append(_normalize_result(raw, i))

    # Fill gaps for any missing indices
    covered = {r["index"] for r in results}
    for i in range(len(exercises)):
        if i not in covered:
            results.append({
                "index": i,
                "knowledge_node_id": "unknown",
                "difficulty": 3,
                "question_type": exercises[i].get("question_type", "choice"),
                "confidence": 0.0,
            })

    return results


def _fallback_results(exercises: list[dict]) -> list[dict]:
    return [
        {
            "index": i,
            "knowledge_node_id": "unknown",
            "difficulty": 3,
            "question_type": ex.get("question_type", "choice"),
            "confidence": 0.0,
        }
        for i, ex in enumerate(exercises)
    ]
