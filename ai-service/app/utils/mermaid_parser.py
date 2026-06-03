"""Mermaid 图表解析器

从 LLM 文本输出中提取 Mermaid 代码块，用于结构化 SSE 推送。
"""

import re
from dataclasses import dataclass


@dataclass
class MermaidBlock:
    code: str
    index: int


MERMAID_PATTERN = re.compile(
    r"```mermaid\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)

SUPPORTED_TYPES = {
    "graph TD", "graph LR", "graph RL", "graph BT",
    "flowchart TD", "flowchart LR",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "erDiagram",
    "gantt",
    "pie",
    "mindmap",
}


def extract_mermaid_blocks(text: str) -> list[MermaidBlock]:
    """从文本中提取所有 Mermaid 代码块。"""
    blocks = []
    for match in MERMAID_PATTERN.finditer(text):
        code = match.group(1).strip()
        if code and _is_valid_mermaid(code):
            blocks.append(MermaidBlock(code=code, index=match.start()))
    return blocks


def _is_valid_mermaid(code: str) -> bool:
    first_line = code.strip().split("\n")[0].strip().lower()
    for prefix in SUPPORTED_TYPES:
        if first_line.startswith(prefix.lower()):
            return True
    return False


def split_text_and_mermaid(text: str) -> list[dict]:
    """将文本分割为交替的文本块和 Mermaid 块。

    返回: [{"type": "text", "content": "..."}, {"type": "mermaid", "code": "..."}, ...]
    """
    matches = list(MERMAID_PATTERN.finditer(text))
    if not matches:
        return [{"type": "text", "content": text}]

    result = []
    last_end = 0

    for match in matches:
        code = match.group(1).strip()
        if not code or not _is_valid_mermaid(code):
            continue
        start = match.start()
        end = match.end()
        if start > last_end:
            text_part = text[last_end:start].strip()
            if text_part:
                result.append({"type": "text", "content": text_part})
        result.append({"type": "mermaid", "code": code})
        last_end = end

    if last_end < len(text):
        tail = text[last_end:].strip()
        if tail:
            result.append({"type": "text", "content": tail})

    return result


def strip_mermaid_from_text(text: str) -> str:
    """移除文本中的 Mermaid 代码块，返回纯文本。"""
    result = MERMAID_PATTERN.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", result).strip()