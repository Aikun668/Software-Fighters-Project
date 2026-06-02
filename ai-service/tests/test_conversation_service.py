"""Tests for ConversationService: 会话持久化"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.conversation_service import ConversationService, get_conversation_service


class TestConversationService:
    @pytest.fixture
    def service(self):
        return ConversationService()

    @pytest.fixture
    def mock_db(self):
        s = AsyncMock()
        s.execute = AsyncMock()
        s.commit = AsyncMock()
        s.add = MagicMock()
        return s

    @pytest.mark.asyncio
    async def test_get_or_create_existing(self, service, mock_db):
        """已有会话 → 返回已有"""
        mock_conv = MagicMock()
        mock_conv.id = 42
        mock_conv.user_id = 1
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_conv
        mock_db.execute.return_value = mock_result

        with patch("app.services.conversation_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            conv = await service.get_or_create_conversation(1, 42)

        assert conv.id == 42
        assert conv.user_id == 1

    @pytest.mark.asyncio
    async def test_get_or_create_new(self, service, mock_db):
        """无 conversation_id → 创建新会话"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        def refresh_side_effect(obj):
            obj.id = 99

        mock_db.refresh = AsyncMock(side_effect=refresh_side_effect)

        with patch("app.services.conversation_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            conv = await service.get_or_create_conversation(1)

        assert conv.user_id == 1
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_or_create_not_found_fallback(self, service, mock_db):
        """conversation_id 存在但找不到 → 创建新的"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        def refresh_side_effect(obj):
            obj.id = 100

        mock_db.refresh = AsyncMock(side_effect=refresh_side_effect)

        with patch("app.services.conversation_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            conv = await service.get_or_create_conversation(1, 999)

        assert conv.user_id == 1

    @pytest.mark.asyncio
    async def test_load_history(self, service, mock_db):
        """加载会话历史"""
        msgs = [
            _make_msg(role="user", content="你好"),
            _make_msg(role="assistant", content="你好！有什么可以帮你？"),
            _make_msg(role="user", content="什么是CNN？"),
        ]
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = msgs
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        with patch("app.services.conversation_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            history = await service.load_history(1)

        assert len(history) == 3
        assert history[0] == {"role": "user", "content": "你好"}
        assert history[2] == {"role": "user", "content": "什么是CNN？"}

    @pytest.mark.asyncio
    async def test_load_history_empty(self, service, mock_db):
        """空会话 → 返回空列表"""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        with patch("app.services.conversation_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            history = await service.load_history(1)

        assert history == []

    @pytest.mark.asyncio
    async def test_load_history_db_error(self, service, mock_db):
        """DB 异常 → 返回空列表（不抛异常）"""
        mock_db.execute.side_effect = Exception("DB connection lost")

        with patch("app.services.conversation_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            history = await service.load_history(1)

        assert history == []

    @pytest.mark.asyncio
    async def test_save_messages(self, service, mock_db):
        """保存一轮对话"""
        mock_db.execute = AsyncMock()

        with patch("app.services.conversation_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            await service.save_messages(1, "用户消息", "AI回复")

        assert mock_db.add.call_count == 2
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_messages_db_error(self, service, mock_db):
        """保存失败 → 不抛异常"""
        mock_db.add.side_effect = Exception("DB write failed")

        with patch("app.services.conversation_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            # 不应 raise
            await service.save_messages(1, "msg", "reply")

    def test_singleton(self):
        s1 = get_conversation_service()
        s2 = get_conversation_service()
        assert s1 is s2


def _make_msg(role, content):
    m = MagicMock()
    m.role = role
    m.content = content
    return m
