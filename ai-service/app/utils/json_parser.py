"""
Robust JSON parsing utilities with automatic repair and markdown extraction.

借鉴 OpenMAIC lib/generation/json-repair.ts 的 4 次尝试模式:
  Layer A (提取层): code block → bracket match → raw text
  Layer B (修复层): direct parse → common fix → jsonrepair → control char strip
"""

import json
import logging
import re
from typing import Any

_repair_json_fn: Any = None

try:
    from json_repair import repair_json as _repair_json_import
except ImportError:
    pass
else:
    _repair_json_fn = _repair_json_import

repair_json = _repair_json_fn
logger = logging.getLogger(__name__)

_UNSET = object()


# ═══════════════════════════════════════════════════════════════
# Layer B: Parse-level helpers
# ═══════════════════════════════════════════════════════════════


def _fix_common_json_issues(text: str) -> str:
    """修复常见的 JSON 格式问题。

    按顺序应用:
    1. 未加引号的属性名: {key: "val"} → {"key": "val"}
    2. 双重转义反斜杠
    3. 尾部逗号: ,} → }, ,] → ]
    4. 补齐截断的括号/花括号
    """
    # 1. 引用未加引号的属性名 ({key: → {"key":)
    fixed = re.sub(
        r'([\{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:',
        r'\1"\2":',
        text,
    )

    # 2. 修复双重转义反斜杠 (LLM 常见错误)
    #    先处理 \\\\ → \\, 再用精确正则处理 \\n→\\n 等
    #    不触碰正常路径中的合法 JSON 转义 (如 C:\\Users)
    fixed = re.sub(r'\\\\\\\\', r'\\\\', fixed)
    fixed = re.sub(r'\\\\([ntr"/bf])', r'\\\1', fixed)

    # 3. 尾部逗号
    fixed = re.sub(r",\s*([}\]])", r"\1", fixed)

    # 4. 补齐截断: 用栈跟踪括号类型，按 LIFO 顺序补齐
    opens_stack: list[str] = []
    for ch in fixed:
        if ch == "{":
            opens_stack.append("{")
        elif ch == "[":
            opens_stack.append("[")
        elif ch == "}":
            if opens_stack and opens_stack[-1] == "{":
                opens_stack.pop()
        elif ch == "]":
            if opens_stack and opens_stack[-1] == "[":
                opens_stack.pop()
    for bracket in reversed(opens_stack):
        fixed += "}" if bracket == "{" else "]"

    return fixed


def _try_parse_json(text: str) -> Any:
    """4 次修复尝试链，首次成功即返回。

    1. 直接解析
    2. _fix_common_json_issues + 解析
    3. json_repair 库修复
    4. 控制字符剥离后解析
    """
    attempts: list[tuple[str, str]] = [
        ("direct", text),
        ("common_fix", _fix_common_json_issues(text)),
    ]

    if repair_json is not None:
        attempts.append(("jsonrepair", repair_json(text)))

    # 控制字符剥离: 将常见控制字符替换为空或转义形式
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    if cleaned != text:
        attempts.append(("control_strip", cleaned))

    for label, candidate in attempts:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            logger.debug(f"JSON parse attempt '{label}' failed")

    raise ValueError(f"All parse strategies failed for text: {text[:200]}")


# ═══════════════════════════════════════════════════════════════
# Layer A: Extraction helpers
# ═══════════════════════════════════════════════════════════════


def _extract_bracket_balanced(text: str) -> str | None:
    """从混合文本中提取第一个平衡的 JSON 对象/数组。

    逐字符扫描，跟踪字符串状态和括号深度。
    返回提取的子串，或 None 表示未找到有效的 JSON 括号段。
    """
    # 找到第一个 { 或 [
    start = -1
    for i, ch in enumerate(text):
        if ch in ("{", "["):
            start = i
            break
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape_next:
            escape_next = False
            continue

        if ch == "\\" and in_string:
            escape_next = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch in ("{", "["):
            depth += 1
        elif ch in ("}", "]"):
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None  # 未闭合


# ═══════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════


def parse_llm_json(
    response: str,
    fallback: Any = _UNSET,
    expected_key: str | None = None,
) -> Any:
    """安全解析 LLM 返回的 JSON，3 种提取 × 4 种修复。

    提取策略（按顺序尝试，首次成功即返回）:
    1. Markdown 代码块提取
    2. 括号平衡匹配提取
    3. 原始文本

    每种提取结果依次经过 4 层修复:
    direct → common_fix → jsonrepair → control_strip

    Args:
        response: LLM 原始返回字符串
        fallback: 解析失败时的返回值（默认 {}）
        expected_key: 期望结果中包含的关键字段（用于校验）

    Returns:
        解析后的 JSON 对象，或 fallback
    """
    if fallback is _UNSET:
        fallback = {}

    if not response or not response.strip():
        logger.warning("LLM returned empty response")
        return fallback

    extractions: list[tuple[str, str | None]] = []

    # A: markdown 代码块
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", response, re.DOTALL)
    extractions.append(("markdown_codeblock", match.group(1).strip() if match else None))

    # B: 括号平衡匹配
    extractions.append(("bracket_balanced", _extract_bracket_balanced(response)))

    # C: 原始文本
    extractions.append(("raw_text", response.strip()))

    for strategy, text in extractions:
        if text is None:
            continue
        try:
            result = _try_parse_json(text)
            if expected_key is None or (
                isinstance(result, dict) and expected_key in result
            ):
                logger.debug(f"JSON parsed via {strategy}")
                return result
            logger.warning(
                f"JSON parsed via {strategy} but missing expected_key "
                f"'{expected_key}', got keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}"
            )
        except ValueError:
            logger.debug(f"Parse chain exhausted for strategy '{strategy}'")

    logger.warning(
        f"All extraction + parse strategies failed for response "
        f"(len={len(response)}): {response[:200]}"
    )
    return fallback
