"""
Robust JSON parsing utilities with automatic repair and markdown extraction.

搬运自 DeepTutor: deeptutor/utils/json_parser.py
三层解析策略：markdown 提取 → 直接解析 → json_repair 修复
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


def parse_llm_json(
    response: str,
    fallback: Any = _UNSET,
    expected_key: str | None = None,
) -> Any:
    """
    安全解析 LLM 返回的 JSON，自动修复和容错。

    三层策略：
    1. 从 markdown 代码块提取 JSON
    2. 直接 JSON 解析
    3. json_repair 自动修复

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

    # 第一层：从 markdown 代码块提取
    extracted = response
    if "```" in response:
        match = re.search(r"```(?:json)?\s*\n?(.*?)```", response, re.DOTALL)
        if match:
            extracted = match.group(1).strip()
            logger.debug("Extracted JSON from markdown code block")

    # 第二层：直接解析
    try:
        result = json.loads(extracted)
        if expected_key is None or expected_key in result:
            return result
        logger.warning(f"JSON parsed but missing expected_key '{expected_key}', keys: {list(result.keys())}")
    except json.JSONDecodeError as e:
        logger.debug(f"Direct JSON parse failed: {e}")

    # 第三层：json_repair 修复
    if repair_json is None:
        logger.warning("json-repair library not installed")
        return fallback

    try:
        repaired = repair_json(extracted)
        result = json.loads(repaired)
        logger.info("Successfully repaired malformed JSON")
        if expected_key is None or expected_key in result:
            return result
        logger.warning(f"Repaired JSON missing expected_key '{expected_key}'")
    except Exception as e:
        logger.debug(f"JSON repair failed: {e}")

    return fallback
