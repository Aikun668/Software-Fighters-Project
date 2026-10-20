"""从 Markdown 正文中抽取 ```ui-block 围栏（T006，MVP 管线）。

约定（D-004 方案 A / D-010）：LLM 把结构化 UI block 写在正文里的
```ui-block 围栏中；后端在**最终正文下发前**把围栏剥离、合法的转成独立
visualization SSE 事件（接线见 chat_task_dispatcher），正文仍是纯 Markdown。

失败围栏的降级（D-014）：
- JSON 解析失败 → 围栏**原样保留**在正文（无法断定意图，不吞内容）；
- JSON 可解析但 parse_ui_block 校验不过（未注册类型 / 非法 props）→ 围栏
  仍从正文**剥离**并记 warning 日志，不下发事件。围栏是机器配置而非给用户
  的正文，留在正文里用户只会看到一段裸 JSON（旧 T006"失败不吞正文"就此
  收窄为"JSON 解析失败的围栏保留"）。
"""

import json
import logging
import re

from app.events.visualization import parse_ui_block

logger = logging.getLogger(__name__)

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
    - JSON 解析 + parse_ui_block 校验都通过 → 规范化 block 进列表，
      围栏从文本剥离；
    - JSON 解析失败 → 围栏原样保留在文本中（无法断定意图，不吞内容）；
    - JSON 可解析但校验不过（未注册类型 / 非法 props）→ 围栏剥离、
      记 warning 日志、不产生 block（D-014，正文不留裸 JSON）；
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
        if parsed["ok"]:
            blocks.append(parsed["value"])
        else:
            # 校验不过：围栏是机器配置而非用户正文，剥离 + 日志，不裸留（D-014）
            logger.warning("ui-block 校验失败，已从正文剥离：%s", parsed["error"])
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
