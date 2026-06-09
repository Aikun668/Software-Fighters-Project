"""会话持久化服务 — 通过 Java API 加载/保存对话历史 + LLM 摘要压缩"""

import logging
import threading
from typing import Optional

from app.services.java_api_client import get_java_client
from app.services.llm_service import create_llm

logger = logging.getLogger(__name__)

MAX_LOAD_MESSAGES = 50
COMPRESS_MIN_MSG_COUNT = 20
COMPRESS_TOKEN_THRESHOLD = 8000
RECENT_KEEP = 15
SUMMARY_MAX_CHARS = 800
SUMMARY_SELF_COMPRESS_AT = 2000


def _estimate_tokens(messages: list[dict]) -> int:
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


def _format_messages_for_compress(messages: list[dict]) -> str:
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


class ConversationService:
    """会话持久化服务 — 委托 Java API 进行数据操作"""

    def __init__(self):
        self._client = get_java_client()

    async def get_or_create_conversation(
        self, user_id: int, conversation_id: Optional[int] = None
    ) -> dict:
        """获取已有会话或创建新会话，返回 conv dict"""
        if conversation_id:
            conv = await self._client.get_conversation(conversation_id, user_id)
            if conv:
                return conv
            logger.info(
                f"Conversation {conversation_id} not found for user {user_id}, creating new"
            )

        conv = await self._client.create_conversation(user_id)
        if conv is None:
            raise RuntimeError(f"无法为用户 {user_id} 创建会话，Java API 返回空")
        return conv

    async def load_history(
        self, conversation_id: int, mode_filter: str | None = None
    ) -> list[dict]:
        """从 Java API 加载会话历史"""
        try:
            messages = await self._client.load_messages(
                conversation_id, mode_filter=mode_filter, limit=MAX_LOAD_MESSAGES
            )
            return messages
        except Exception as e:
            logger.warning(f"Failed to load history for conv {conversation_id}: {e}")
            return []

    async def _get_messages_raw(
        self, conversation_id: int, offset: int = 0, limit: int = 200
    ) -> list[dict]:
        """加载消息字典列表（内部使用，支持偏移）"""
        try:
            return await self._client.load_messages_raw(conversation_id, offset, limit)
        except Exception as e:
            logger.warning(f"Failed to load raw messages: {e}")
            return []

    async def compress_history(self, conversation_id: int, user_id: int = 0) -> bool:
        """增量压缩对话历史。返回 True 表示执行了压缩。"""
        try:
            conv = await self._client.get_conversation(conversation_id, user_id)
            if not conv:
                return False

            cursor = conv.get("summary_msg_cursor", 0) or 0
            unsummarized = await self._get_messages_raw(
                conversation_id, offset=cursor, limit=200
            )

            if not unsummarized:
                return False

            msg_count = len(unsummarized)
            est_tokens = _estimate_tokens(unsummarized)

            if msg_count < COMPRESS_MIN_MSG_COUNT and est_tokens < COMPRESS_TOKEN_THRESHOLD:
                return False

            if msg_count <= RECENT_KEEP:
                return False

            to_compress = unsummarized[:-RECENT_KEEP]
            if not to_compress:
                return False

            existing_summary = conv.get("summary", "") or ""

            if len(existing_summary) > SUMMARY_SELF_COMPRESS_AT:
                existing_summary = await self._self_compress(existing_summary)

            new_text = _format_messages_for_compress(to_compress)
            new_summary = await self._llm_summarize(existing_summary, new_text)

            if not new_summary:
                return False

            await self._client.update_conversation(
                conversation_id,
                {
                    "summary": new_summary,
                    "summary_msg_cursor": cursor + len(to_compress),
                },
            )

            logger.info(
                f"Compressed {len(to_compress)} messages for conv {conversation_id}, "
                f"cursor={cursor + len(to_compress)}, summary_len={len(new_summary)}"
            )
            return True

        except Exception as e:
            logger.warning(f"Compress failed for conv {conversation_id}: {e}")
            return False

    async def _llm_summarize(
        self, existing_summary: str, new_messages_text: str
    ) -> str | None:
        try:
            compress_llm = create_llm(temperature=0.2, use_mock=False)

            system_prompt = (
                f"你是对话历史压缩专家。将对话历史压缩成不超过{SUMMARY_MAX_CHARS}字的摘要。"
                "保留关键信息：学生问了什么问题、AI解答了什么、学生的理解情况、薄弱环节、"
                "学习进度。丢弃闲聊和重复内容。只输出摘要文本，不要加任何前缀解释。"
            )

            if existing_summary:
                user_prompt = (
                    f"## 已有对话摘要\n{existing_summary}\n\n"
                    f"## 新对话记录\n{new_messages_text}\n\n"
                    f"请将上述已有摘要和新对话合并压缩，不超过{SUMMARY_MAX_CHARS}字。"
                )
            else:
                user_prompt = (
                    f"## 对话记录\n{new_messages_text}\n\n"
                    f"请压缩为不超过{SUMMARY_MAX_CHARS}字的摘要。"
                )

            result = await compress_llm.chat(
                [{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
            )
            return result.strip() if result else None
        except Exception as e:
            logger.warning(f"LLM summarization failed: {e}")
            return None

    async def _self_compress(self, summary: str) -> str:
        try:
            compress_llm = create_llm(temperature=0.2, use_mock=False)

            user_prompt = (
                f"以下对话历史摘要过长，请压缩到不超过{SUMMARY_MAX_CHARS}字，保留最重要的信息：\n\n"
                f"{summary}"
            )

            result = await compress_llm.chat(
                [{"role": "user", "content": user_prompt}],
                system_prompt="你是文本压缩专家。只输出压缩后的摘要文本，不要加任何前缀。",
            )
            return result.strip() if result else summary
        except Exception as e:
            logger.warning(f"Self-compress failed: {e}")
            return summary[:SUMMARY_SELF_COMPRESS_AT]

    async def get_summary(self, conversation_id: int, user_id: int = 0) -> str:
        """获取会话摘要"""
        try:
            conv = await self._client.get_conversation(conversation_id, user_id)
            return (conv.get("summary") or "") if conv else ""
        except Exception:
            return ""

    async def save_messages(
        self,
        conversation_id: int,
        user_msg: str,
        assistant_msg: str,
        user_mode: str = "tutor",
        assistant_mode: str = "tutor",
    ) -> None:
        """保存一轮对话到 Java API（不阻塞主流程）"""
        try:
            await self._client.save_messages(
                conversation_id, user_msg, assistant_msg, user_mode, assistant_mode
            )
        except Exception as e:
            logger.warning(f"Failed to save messages for conv {conversation_id}: {e}")

    async def update_title(self, conversation_id: int, title: str) -> None:
        """更新会话标题"""
        try:
            await self._client.update_conversation(
                conversation_id, {"title": title[:200]}
            )
        except Exception as e:
            logger.warning(f"Failed to update title for conv {conversation_id}: {e}")


_service: Optional[ConversationService] = None
_service_lock = threading.Lock()


def get_conversation_service() -> ConversationService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = ConversationService()
    return _service
