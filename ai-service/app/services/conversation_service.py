"""会话持久化服务 — 从 DB 加载/保存对话历史 + LLM 摘要压缩"""

import logging
import threading
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.dialects.mysql import insert

from app.db.database import get_db
from app.models.conversation import Conversation, Message
from app.services.llm_service import create_llm

logger = logging.getLogger(__name__)

MAX_LOAD_MESSAGES = 50  # 最多从 DB 加载 50 条历史消息

# ── 摘要压缩参数 ──
COMPRESS_MIN_MSG_COUNT = 20     # 未摘要消息 ≥20 条才考虑压缩
COMPRESS_TOKEN_THRESHOLD = 8000  # 未摘要消息估算 token ≥8000 触发
RECENT_KEEP = 15                # 保留最近 15 条原始消息不压缩
SUMMARY_MAX_CHARS = 800         # 摘要目标长度（字符）
SUMMARY_SELF_COMPRESS_AT = 2000  # 摘要超过此长度时自我压缩


def _estimate_tokens(messages: list[dict]) -> int:
    """粗略估算消息 token 数：中英文混合保守估计 chars/2 ≈ tokens"""
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
    """格式化消息为压缩用的纯文本"""
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
    """会话持久化服务"""

    async def get_or_create_conversation(
        self, user_id: int, conversation_id: Optional[int] = None
    ) -> Conversation:
        """获取已有会话或创建新会话"""
        if conversation_id:
            async with get_db() as session:
                result = await session.execute(
                    select(Conversation).where(
                        Conversation.id == conversation_id,
                        Conversation.user_id == user_id,
                    )
                )
                conv = result.scalar_one_or_none()
                if conv:
                    return conv
                logger.info(
                    f"Conversation {conversation_id} not found for user {user_id}, creating new"
                )

        async with get_db() as session:
            conv = Conversation(user_id=user_id)
            session.add(conv)
            await session.commit()
            await session.refresh(conv)
            return conv

    async def load_history(self, conversation_id: int) -> list[dict]:
        """从 DB 加载会话历史，返回 [{"role": "user", "content": "..."}, ...]"""
        try:
            async with get_db() as session:
                result = await session.execute(
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.created_at.asc())
                    .limit(MAX_LOAD_MESSAGES)
                )
                rows = result.scalars().all()
                return [{"role": m.role, "content": m.content} for m in rows]
        except Exception as e:
            logger.warning(f"Failed to load history for conv {conversation_id}: {e}")
            return []

    async def _get_messages_raw(
        self, conversation_id: int, offset: int = 0, limit: int = 200
    ) -> list[Message]:
        """加载消息 ORM 对象（内部使用，支持偏移）"""
        async with get_db() as session:
            result = await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc())
                .offset(offset)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def compress_history(self, conversation_id: int) -> bool:
        """增量压缩对话历史（借鉴 DeepTutor ContextBuilder）。

        只在满足条件时触发：未摘要消息数 ≥20 且估算 token ≥8000。

        返回 True 表示执行了压缩。
        """
        try:
            async with get_db() as session:
                conv_result = await session.execute(
                    select(Conversation).where(Conversation.id == conversation_id)
                )
                conv = conv_result.scalar_one_or_none()
                if not conv:
                    return False

                cursor = conv.summary_msg_cursor or 0

                # 加载 cursor 之后的消息
                msg_result = await session.execute(
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.created_at.asc())
                    .offset(cursor)
                    .limit(200)
                )
                unsummarized = list(msg_result.scalars().all())

                if not unsummarized:
                    return False

                # 转换为 dict
                unsummarized_dicts = [
                    {"role": m.role, "content": m.content} for m in unsummarized
                ]

                # ── 判断是否需要压缩 ──
                msg_count = len(unsummarized_dicts)
                est_tokens = _estimate_tokens(unsummarized_dicts)

                if msg_count < COMPRESS_MIN_MSG_COUNT and est_tokens < COMPRESS_TOKEN_THRESHOLD:
                    return False

                # ── 保留最近 RECENT_KEEP 条 ──
                if msg_count <= RECENT_KEEP:
                    return False

                to_compress = unsummarized_dicts[:-RECENT_KEEP]
                if not to_compress:
                    return False

                # ── 增量 LLM 压缩 ──
                existing_summary = conv.summary or ""

                # 如果已有摘要过长，先自我压缩
                if len(existing_summary) > SUMMARY_SELF_COMPRESS_AT:
                    existing_summary = await self._self_compress(existing_summary)

                new_text = _format_messages_for_compress(to_compress)
                new_summary = await self._llm_summarize(existing_summary, new_text)

                if not new_summary:
                    return False

                # ── 写回 DB ──
                conv.summary = new_summary
                conv.summary_msg_cursor = cursor + len(to_compress)

                await session.execute(
                    update(Conversation)
                    .where(Conversation.id == conversation_id)
                    .values(
                        summary=new_summary,
                        summary_msg_cursor=conv.summary_msg_cursor,
                        updated_at=func.now(),
                    )
                )
                await session.commit()

                logger.info(
                    f"Compressed {len(to_compress)} messages for conv {conversation_id}, "
                    f"cursor={conv.summary_msg_cursor}, summary_len={len(new_summary)}"
                )
                return True

        except Exception as e:
            logger.warning(f"Compress failed for conv {conversation_id}: {e}")
            return False

    async def _llm_summarize(
        self, existing_summary: str, new_messages_text: str
    ) -> str | None:
        """调用 LLM 增量压缩对话历史"""
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
        """对过长的摘要进行自我压缩"""
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
            # 降级：直接截断
            return summary[:SUMMARY_SELF_COMPRESS_AT]

    async def get_summary(self, conversation_id: int) -> str:
        """获取会话摘要"""
        try:
            async with get_db() as session:
                result = await session.execute(
                    select(Conversation.summary).where(
                        Conversation.id == conversation_id
                    )
                )
                return result.scalar() or ""
        except Exception:
            return ""

    async def save_messages(
        self,
        conversation_id: int,
        user_msg: str,
        assistant_msg: str,
    ) -> None:
        """保存一轮对话到 DB（不阻塞主流程）"""
        try:
            async with get_db() as session:
                session.add(Message(
                    conversation_id=conversation_id,
                    role="user",
                    content=user_msg,
                ))
                session.add(Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=assistant_msg,
                ))
                await session.execute(
                    update(Conversation)
                    .where(Conversation.id == conversation_id)
                    .values(updated_at=func.now())
                )
                await session.commit()
        except Exception as e:
            logger.warning(f"Failed to save messages for conv {conversation_id}: {e}")

    async def update_title(self, conversation_id: int, title: str) -> None:
        """更新会话标题（首次对话后自动生成）"""
        try:
            async with get_db() as session:
                await session.execute(
                    update(Conversation)
                    .where(Conversation.id == conversation_id)
                    .values(title=title[:200])
                )
                await session.commit()
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
