"""对话历史 LLM 摘要压缩工具 — 纯函数，供 Java 按需调用"""

import logging

from app.services.llm_service import create_llm

logger = logging.getLogger(__name__)

SUMMARY_MAX_CHARS = 800
SUMMARY_SELF_COMPRESS_AT = 2000


def estimate_tokens(messages: list[dict]) -> int:
    """估算消息列表的 token 数（字符数 / 2 的粗略估计）"""
    total = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            total += sum(
                len(p.get("text", "")) for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
    return total // 2


def format_messages_for_compress(messages: list[dict]) -> str:
    """将消息列表格式化为 LLM 摘要所需的文本"""
    lines = []
    for m in messages:
        role = "学生" if m.get("role") == "user" else "AI"
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "") for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
        if content:
            lines.append(f"[{role}]: {content}")
    return "\n".join(lines)


async def llm_summarize(existing_summary: str, new_messages_text: str) -> str | None:
    """用 LLM 对新消息进行增量摘要压缩"""
    if not new_messages_text.strip():
        return existing_summary or None

    llm = create_llm(temperature=0.2)

    if existing_summary:
        prompt = (
            "你是一个对话摘要助手。以下是已有的对话摘要和新的对话内容。"
            "请将新内容合并到摘要中，保持简洁（不超过 800 字）。\n\n"
            f"## 已有摘要\n{existing_summary}\n\n"
            f"## 新对话内容\n{new_messages_text}\n\n"
            "请输出合并后的摘要（纯文本，不要 JSON，不超过 800 字）："
        )
    else:
        prompt = (
            "你是一个对话摘要助手。请对以下对话内容进行摘要，保持简洁（不超过 800 字）。\n\n"
            f"{new_messages_text}\n\n"
            "请输出摘要（纯文本，不要 JSON，不超过 800 字）："
        )

    try:
        result = await llm.chat([{"role": "user", "content": prompt}])
        if result:
            summary = result.strip()
            if len(summary) > SUMMARY_SELF_COMPRESS_AT:
                summary = await self_compress(summary)
            return summary[:SUMMARY_MAX_CHARS]
    except Exception as e:
        logger.warning(f"LLM summarize failed: {e}")

    return existing_summary or None


async def self_compress(summary: str) -> str:
    """对过长摘要进行自我压缩"""
    llm = create_llm(temperature=0.1)
    prompt = (
        "你是一个文本压缩助手。请将以下文本压缩到 400 字以内，保留关键信息。\n\n"
        f"{summary}\n\n"
        "请输出压缩后的文本（纯文本，不超过 400 字）："
    )

    try:
        result = await llm.chat([{"role": "user", "content": prompt}])
        if result:
            return result.strip()[:SUMMARY_MAX_CHARS]
    except Exception as e:
        logger.warning(f"Self-compress failed: {e}")

    # Fallback: 简单截断
    return summary[:SUMMARY_MAX_CHARS]
