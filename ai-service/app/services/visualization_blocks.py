"""从 Markdown 正文中抽取 ```ui-block 围栏（T006，MVP 管线）。

约定（D-004 方案 A / D-010）：LLM 把结构化 UI block 写在正文里的
```ui-block 围栏中；后端在**最终正文下发前**把合法围栏剥离、转成独立
visualization SSE 事件（接线见 chat_task_dispatcher），正文仍是纯 Markdown。

失败不吞正文：JSON 解析失败或 parse_ui_block 校验不过（含 D-007 weights）
的围栏**原样保留**在返回文本里——前端最多看到一段 JSON 代码块，不会丢内容。
"""

import json
import re

from app.events.visualization import parse_ui_block

# 只认 3-backtick 围栏、info string 恰为 ui-block（允许两侧空白），
# 且开/闭围栏必须独立成行（行首，CommonMark fenced code 行为）。
# 闭围栏后的一个换行（及至多一个空行）随围栏一起剥掉——围栏通常独占
# 一段（前后各一空行），这样剥离后前后文之间恰保留一个空行分隔。
# 普通代码块（其他 info string / 无 info string）不匹配，不受影响。
_UI_BLOCK_RE = re.compile(
    r"^```[ \t]*ui-block[ \t]*\n"
    r"(?P<body>.*?)"
    r"^```[ \t]*(?:\n\n?|$)",
    re.DOTALL | re.MULTILINE,
)

# 最终正文 payload 中承载正文的键（ensure_user_visible_response 合同）
_PAYLOAD_TEXT_KEYS = ("response", "content")


def extract_ui_blocks(text: str) -> tuple[str, list[dict]]:
    """抽取正文中的 ```ui-block 围栏。

    返回 (清理后的文本, 合法 block 列表)：
    - 围栏内容 JSON 解析 + parse_ui_block 校验都通过 → 规范化 block 进列表，
      围栏从文本剥离；
    - 任一步失败 → 该围栏原样保留在文本中（失败不吞正文）；
    - 无围栏 → (原文, [])；多个围栏全部处理，block 按出现顺序排列。
    """
    blocks: list[dict] = []
    parts: list[str] = []
    last_end = 0
    for match in _UI_BLOCK_RE.finditer(text):
        try:
            candidate = json.loads(match.group("body"))
        except ValueError:
            continue  # JSON 非法：围栏保留
        parsed = parse_ui_block(candidate)
        if not parsed["ok"]:
            continue  # 校验不过（含 D-007）：围栏保留
        blocks.append(parsed["value"])
        parts.append(text[last_end:match.start()])
        last_end = match.end()
    parts.append(text[last_end:])
    return "".join(parts), blocks


def extract_ui_blocks_from_payload(payload: dict) -> list[dict]:
    """对最终正文 payload 抽取 ui-block：就地剥离合法围栏，返回 block 列表。

    正文可能在 response / content 两个键上（ensure_user_visible_response
    对 solution/summary 合成路径会写入同值双键）：同值文本只抽取一次、
    两个键同步替换，避免同一 block 发两次；两键文本不同则分别抽取、按序合并。
    """
    blocks: list[dict] = []
    cleaned_cache: dict[str, str] = {}
    for key in _PAYLOAD_TEXT_KEYS:
        text = payload.get(key)
        if not isinstance(text, str):
            continue
        if text in cleaned_cache:
            payload[key] = cleaned_cache[text]
            continue
        cleaned, extracted = extract_ui_blocks(text)
        cleaned_cache[text] = cleaned
        payload[key] = cleaned
        blocks.extend(extracted)
    return blocks
