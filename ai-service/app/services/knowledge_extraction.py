"""Knowledge node extraction service.

Extracts structured knowledge nodes from a single user/assistant exchange using
an LLM, normalizes identifiers, filters duplicates and low-confidence results,
and returns a cleaned list of node dictionaries.
"""

import hashlib
import logging
import re
from typing import Any

from app.services.llm_service import get_llm_service
from app.utils.json_parser import parse_llm_json
from app.utils.prompt_loader import build_prompt, interpolate_variables, load_prompt_file

logger = logging.getLogger(__name__)

__all__ = ["extract_knowledge_nodes"]

_VALID_TYPES = {"concept", "skill", "fact"}
_VALID_CATEGORIES = {"foundational", "intermediate", "advanced"}
_VALID_SUBTYPES = {"core", "related", "broad"}
_MIN_CONFIDENCE = 0.85


def _node_id_from_name(name: str) -> str:
    """生成节点 ID：先用 graph_service 规范化，纯中文输入转拼音，失败则 hash 兜底。

    统一使用 app.utils.graph_id.normalize_node_id 确保骨架节点和动态节点 ID 一致。
    纯英文名（如 "ai_overview"）保留原样；纯中文名（"反向传播"）用 pypinyin
    转拼音（fan_xiang_chuan_bo）；混合名（"Transformer 架构"）拆分后各转拼音。
    """
    from app.utils.graph_id import normalize_node_id

    try:
        return normalize_node_id(name)
    except ValueError:
        pass

    pinyin_id = _to_pinyin_id(name)
    if pinyin_id:
        return pinyin_id

    digest = hashlib.md5(name.encode("utf-8")).hexdigest()[:4]
    return f"node_{digest}"


def _to_pinyin_id(name: str) -> str:
    """用 pypinyin 将中文名转为拼音 ID，失败返回空字符串。"""
    try:
        from pypinyin import lazy_pinyin
    except ImportError:
        return ""

    tokens = re.split(r"[^一-鿿\w]+", name)
    result: list[str] = []
    for token in tokens:
        if not token:
            continue
        if re.search(r"[一-鿿]", token):
            py = lazy_pinyin(token, errors="ignore")
            result.extend(py)
        else:
            result.append(token.lower())
    if not result:
        return ""
    raw = "_".join(result)
    raw = re.sub(r"[^a-z0-9_]+", "", raw)
    raw = re.sub(r"_+", "_", raw)
    return raw.strip("_") or ""


def _normalize_value(value: Any, field: str) -> Any:
    """Validate and coerce a single node field value."""
    if field == "type":
        value = str(value).lower().strip() if value is not None else ""
        return value if value in _VALID_TYPES else "concept"

    if field == "subtype":
        value = str(value).lower().strip() if value is not None else ""
        return value if value in _VALID_SUBTYPES else "related"

    if field == "category":
        value = str(value).lower().strip() if value is not None else ""
        return value if value in _VALID_CATEGORIES else "intermediate"

    if field == "difficulty":
        try:
            difficulty = int(value)
        except (TypeError, ValueError):
            difficulty = 3
        return max(1, min(5, difficulty))

    if field == "confidence":
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            confidence = 0.0
        return max(0.0, min(1.0, confidence))

    return value


_MAX_EXTRACTED_NODES = 5
_TYPE_PRIORITY = {"core": 0, "related": 1, "broad": 2}


def _truncate_nodes(nodes: list[dict[str, Any]], max_count: int = _MAX_EXTRACTED_NODES) -> list[dict[str, Any]]:
    """Backend hard cap: keep core first, then related, then broad."""
    if len(nodes) <= max_count:
        return nodes

    def _sort_key(node: dict[str, Any]) -> tuple[int, float]:
        subtype = str(node.get("subtype", "")).lower()
        priority = _TYPE_PRIORITY.get(subtype, 3)
        return (priority, -float(node.get("confidence", 0.0)))

    sorted_nodes = sorted(nodes, key=_sort_key)
    return sorted_nodes[:max_count]


def _group_nodes(nodes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    primary = [n for n in nodes if n.get("subtype") == "core"]
    related = [n for n in nodes if n.get("subtype") == "related"]
    broad = [n for n in nodes if n.get("subtype") == "broad"]
    return {
        "primary": primary,
        "related": related,
        "broad": broad,
        "all": nodes,
    }


async def extract_knowledge_nodes(
    course_id: str,
    user_message: str,
    assistant_reply: str,
    existing_node_ids: set[str] | list[str] | None = None,
    llm: Any | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Extract knowledge nodes from a user/assistant exchange.

    Args:
        course_id: The course identifier (currently unused but kept for API symmetry).
        user_message: The user's message.
        assistant_reply: The assistant's reply.
        existing_node_ids: Optional ids to exclude from the result.
        llm: Optional LLM instance with an async ``chat`` method. If not
            provided, the default LLM service is used.

    Returns:
        A dict with keys "primary", "related", "broad", "all" listing cleaned
        knowledge-node dictionaries. Returns empty lists if parsing fails or
        the LLM call fails.
    """
    if not user_message or not assistant_reply:
        return {"primary": [], "related": [], "broad": [], "all": []}

    if existing_node_ids is None:
        existing_node_ids = set()
    existing_set = {str(node_id).strip().lower() for node_id in existing_node_ids}

    variables = {
        "user_message": user_message,
        "assistant_reply": assistant_reply,
        "existing_node_ids": list(existing_set),
    }

    try:
        system_prompt = build_prompt("knowledge_extraction", key="system")
        user_template = load_prompt_file("knowledge_extraction", key="user_template")
        user_prompt = interpolate_variables(user_template, variables)
    except Exception as exc:
        logger.warning(f"Failed to build knowledge extraction prompt: {exc}")
        return {"primary": [], "related": [], "broad": [], "all": []}

    try:
        llm_instance = llm if llm is not None else get_llm_service()
        response = await llm_instance.chat(
            [{"role": "user", "content": user_prompt}],
            system_prompt=system_prompt,
        )
    except Exception as exc:
        logger.warning(f"LLM call failed during knowledge extraction: {exc}")
        return {"primary": [], "related": [], "broad": [], "all": []}

    try:
        data = parse_llm_json(response, fallback={}, expected_key="nodes")
    except Exception as exc:
        logger.warning(f"Failed to parse LLM response as JSON: {exc}")
        return {"primary": [], "related": [], "broad": [], "all": []}

    if not isinstance(data, dict):
        return {"primary": [], "related": [], "broad": [], "all": []}

    raw_nodes = data.get("nodes", [])
    if not isinstance(raw_nodes, list):
        logger.warning(f"Unexpected 'nodes' type: {type(raw_nodes).__name__}")
        return {"primary": [], "related": [], "broad": [], "all": []}

    cleaned_nodes: list[dict] = []
    seen_ids: set[str] = set()

    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict):
            continue

        name = str(raw_node.get("name", "")).strip()
        if not name:
            continue

        node_id = _node_id_from_name(str(raw_node.get("id", name)))
        if not node_id or node_id in existing_set or node_id in seen_ids:
            continue

        confidence = _normalize_value(raw_node.get("confidence"), "confidence")
        if confidence < _MIN_CONFIDENCE:
            continue

        description = str(raw_node.get("description", "")).strip()
        if not description:
            description = name

        node = {
            "id": node_id,
            "name": name,
            "type": _normalize_value(raw_node.get("type"), "type"),
            "subtype": _normalize_value(raw_node.get("subtype"), "subtype"),
            "description": description,
            "category": _normalize_value(raw_node.get("category"), "category"),
            "difficulty": _normalize_value(raw_node.get("difficulty"), "difficulty"),
            "confidence": confidence,
            "suggested_prerequisites": _clean_prerequisites(
                raw_node.get("suggested_prerequisites", [])
            ),
            "suggested_relations": _clean_relations(
                raw_node.get("suggested_relations", [])
            ),
        }

        seen_ids.add(node_id)
        cleaned_nodes.append(node)

    truncated = _truncate_nodes(cleaned_nodes)
    return _group_nodes(truncated)


def _clean_prerequisites(value: Any) -> list[str]:
    """Return a list of non-empty prerequisite strings."""
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if item is not None and str(item).strip()]


def _clean_relations(value: Any) -> list[dict]:
    """Return a list of sanitized relation dictionaries."""
    if not isinstance(value, list):
        return []
    relations: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "")).strip()
        target = str(item.get("target", "")).strip()
        relation = str(item.get("relation", "")).strip()
        if source and target and relation:
            relations.append({"source": source, "target": target, "relation": relation})
    return relations
