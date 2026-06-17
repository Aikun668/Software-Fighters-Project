"""LLM prompt 注入防护 — 清理用户输入中的常见注入模式"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_MAX_USER_INPUT_CHARS = 4000

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|directives?)", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?)", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+(are|must|should|will|now)", re.IGNORECASE),
    re.compile(r"\[system\][\s\S]*?\[/system\]", re.IGNORECASE),
    re.compile(r"<\|im_start\|>|<\|im_end\|>", re.IGNORECASE),
    re.compile(r"\[INST\][\s\S]*?\[/INST\]", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an|the)\s+different", re.IGNORECASE),
    re.compile(r"new\s+system\s+prompt", re.IGNORECASE),
]


_SKIP_SANITIZE_FIELDS = frozenset({
    "type", "mode", "status", "stage", "domain", "mime_type",
    "role", "resource_type", "node_type", "cognitive_style",
    "learning_pace", "difficulty", "strategy", "style",
    "course_id", "user_id", "conversation_id", "node_id",
    "knowledge_node_id", "plan_id", "step_id",
})


def sanitize_for_llm(text: str) -> str:
    """清理用户文本中的常见 prompt 注入模式。"""
    if not text:
        return text
    text = text[:_MAX_USER_INPUT_CHARS]
    for pattern in _INJECTION_PATTERNS:
        text = pattern.sub("[filtered]", text)
    return text


def sanitize_model(obj: Any) -> Any:
    """递归遍历 Pydantic 模型 / dict / list，对所有 str 字段执行 sanitize_for_llm()。

    跳过 _SKIP_SANITIZE_FIELDS 中的字段名（这些是标识符/枚举值，注入无意义）。
    返回原类型（修改在对象上就地完成）。
    """
    try:
        if hasattr(obj, "model_dump") and callable(obj.model_dump):
            data = obj.model_dump()
            _sanitize_dict(data)
            # write back sanitized strings into the model fields
            for field_name, value in data.items():
                if isinstance(value, str) and hasattr(obj, field_name):
                    setattr(obj, field_name, value)
                elif isinstance(value, (dict, list)):
                    _sanitize_dict(value)
            return obj
        elif isinstance(obj, dict):
            _sanitize_dict(obj)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, str):
                    obj[i] = sanitize_for_llm(item)
                else:
                    sanitize_model(item)
    except Exception:
        logger.warning("sanitize_model failed, returning original", exc_info=True)
    return obj


def _sanitize_dict(data: dict) -> None:
    for k, v in list(data.items()):
        if isinstance(v, str) and k not in _SKIP_SANITIZE_FIELDS:
            data[k] = sanitize_for_llm(v)
        elif isinstance(v, dict):
            _sanitize_dict(v)
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, str) and k not in _SKIP_SANITIZE_FIELDS:
                    v[i] = sanitize_for_llm(item)
                elif isinstance(item, dict):
                    _sanitize_dict(item)
                elif isinstance(item, list):
                    sanitize_model(item)
