"""LLM prompt 注入防护 — 清理用户输入中的常见注入模式"""

import re

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


def sanitize_for_llm(text: str) -> str:
    """清理用户文本中的常见 prompt 注入模式。"""
    if not text:
        return text
    text = text[:_MAX_USER_INPUT_CHARS]
    for pattern in _INJECTION_PATTERNS:
        text = pattern.sub("[filtered]", text)
    return text
