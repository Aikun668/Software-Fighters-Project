"""会话持久化服务 — 从 DB 加载/保存对话历史"""

import logging
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.dialects.mysql import insert

from app.db.database import get_db
from app.models.conversation import Conversation, Message

logger = logging.getLogger(__name__)

MAX_LOAD_MESSAGES = 50  # 最多从 DB 加载 50 条历史消息


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


def get_conversation_service() -> ConversationService:
    global _service
    if _service is None:
        _service = ConversationService()
    return _service
