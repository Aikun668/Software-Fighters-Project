"""可视化代码确定性验证器 —— 零 LLM 成本的质量检查。

在 CodeGenerator 产出代码后、ReviewAgent 调用前执行。
通过则直接使用，失败才调 ReviewAgent 修复。
"""

import json
import re
import xml.etree.ElementTree as ET

# Mermaid 有效首行关键字
_MERMAID_KEYWORDS = frozenset({
    "graph", "flowchart", "sequenceDiagram", "classDiagram",
    "stateDiagram", "stateDiagram-v2", "erDiagram", "gantt",
    "mindmap", "pie", "journey", "timeline", "gitGraph",
    "quadrantChart", "xychart-beta", "block-beta",
    "C4Context", "C4Container", "C4Component",
})

# SVG 中可执行代码的检测模式（校验通过会跳过 ReviewAgent，必须拦截）
_XSS_DANGEROUS = [
    re.compile(r"<\s*script[\s>/]", re.IGNORECASE),
    re.compile(r"\son\w+\s*=", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"<\s*foreignObject[\s>/]", re.IGNORECASE),
]


def validate_visualization(code: str, render_type: str) -> tuple[bool, str]:
    """确定性验证可视化代码。返回 (ok, error_reason)。"""
    if not code or not code.strip():
        return False, "代码为空"

    validators = {
        "svg": _validate_svg,
        "chartjs": _validate_chartjs,
        "mermaid": _validate_mermaid,
        "html": _validate_html,
    }

    validator = validators.get(render_type)
    if validator is None:
        return True, ""  # 未知类型不过滤

    return validator(code)


def _validate_svg(code: str) -> tuple[bool, str]:
    code_lower = code.lower()

    if "<svg" not in code_lower or "</svg>" not in code_lower:
        return False, "缺少 <svg> 标签"

    if "viewbox" not in code_lower:
        return False, "缺少 viewBox 属性"

    if code_lower.count("<svg") != code_lower.count("</svg>"):
        return False, "svg 标签数量不匹配"

    # XML 格式检查
    try:
        ET.fromstring(code)
    except ET.ParseError as e:
        return False, f"XML 解析失败: {e}"

    # XSS 可执行代码检测
    for pattern in _XSS_DANGEROUS:
        if pattern.search(code):
            return False, f"SVG 包含危险内容: {pattern.pattern}"

    return True, ""


def _validate_chartjs(code: str) -> tuple[bool, str]:
    try:
        data = json.loads(code)
    except json.JSONDecodeError as e:
        return False, f"JSON 解析失败: {e}"

    if not isinstance(data, dict):
        return False, "Chart.js 配置必须是 JSON 对象"

    if "type" not in data:
        return False, "缺少 type 字段"

    if "data" not in data:
        return False, "缺少 data 字段"

    return True, ""


def _validate_mermaid(code: str) -> tuple[bool, str]:
    first_line = ""
    for line in code.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("%%"):
            first_line = stripped
            break

    if not first_line:
        return False, "Mermaid 代码为空"

    first_word = first_line.split()[0] if first_line.split() else ""
    if first_word not in _MERMAID_KEYWORDS:
        return False, f"Mermaid 首行关键字无效: {first_word}"

    return True, ""


def _validate_html(code: str) -> tuple[bool, str]:
    code_lower = code.lower()
    indicators = ("<html", "<!doctype", "<body", "<div")

    if not any(ind in code_lower for ind in indicators):
        return False, "HTML 缺少可渲染元素"

    return True, ""
