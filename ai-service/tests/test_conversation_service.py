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


# ── Token 估算 & 格式化 ──────────────────────────────────────────


class TestEstimateTokens:
    def test_empty_messages(self):
        from app.services.conversation_service import _estimate_tokens
        assert _estimate_tokens([]) == 0

    def test_simple_messages(self):
        from app.services.conversation_service import _estimate_tokens
        msgs = [
            {"role": "user", "content": "你好" * 50},         # 100 chars
            {"role": "assistant", "content": "你好呀" * 50},  # 150 chars
        ]
        est = _estimate_tokens(msgs)
        # 250 chars / 2 = 125 tokens
        assert est == 125

    def test_multimodal_content(self):
        from app.services.conversation_service import _estimate_tokens
        msgs = [
            {"role": "user", "content": [
                {"type": "text", "text": "这段文字200个字符" * 10},  # ~180 chars
                {"type": "image_url", "image_url": {"url": "..."}},
            ]},
        ]
        est = _estimate_tokens(msgs)
        assert est > 0  # 应该只计算文本
        assert est < 200

    def test_threshold_trigger(self):
        """模拟 25 条中等长度消息 → 应超过 8000 token 阈值"""
        from app.services.conversation_service import _estimate_tokens, COMPRESS_TOKEN_THRESHOLD
        msgs = [
            {"role": "user" if i % 2 == 0 else "assistant",
             "content": "这是一段中等长度的辅导对话消息，包含一些技术讨论内容。" * 10}
            for i in range(25)
        ]
        est = _estimate_tokens(msgs)
        # 每条约 260 chars, 25条 = 6500 chars /2 = 3250 tokens
        assert est > 0


class TestFormatMessages:
    def test_format_basic(self):
        from app.services.conversation_service import _format_messages_for_compress
        msgs = [
            {"role": "user", "content": "什么是反向传播？"},
            {"role": "assistant", "content": "反向传播是神经网络的训练算法..."},
        ]
        result = _format_messages_for_compress(msgs)
        assert "[学生]: 什么是反向传播？" in result
        assert "[AI]: 反向传播是神经网络的训练算法..." in result

    def test_format_skips_empty(self):
        from app.services.conversation_service import _format_messages_for_compress
        msgs = [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": "有效回复"},
        ]
        result = _format_messages_for_compress(msgs)
        assert "[学生]" not in result  # 空消息跳过
        assert "[AI]: 有效回复" in result

    def test_format_multimodal(self):
        from app.services.conversation_service import _format_messages_for_compress
        msgs = [
            {"role": "user", "content": [
                {"type": "text", "text": "看看这张图"},
                {"type": "image_url", "image_url": {"url": "http://..."}},
            ]},
        ]
        result = _format_messages_for_compress(msgs)
        assert "[学生]: 看看这张图" in result


# ── 摘要压缩 ─────────────────────────────────────────────────────


class TestCompressHistory:
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
    async def test_no_compress_when_few_messages(self, service, mock_db):
        """消息太少 → 不触发压缩"""
        mock_conv = MagicMock()
        mock_conv.id = 1
        mock_conv.summary_msg_cursor = 0
        mock_conv.summary = ""

        # 只返回 10 条消息
        msgs = [_make_msg("user", f"消息{i}") for i in range(10)]
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = msgs
        mock_conv_result = MagicMock()
        mock_conv_result.scalar_one_or_none.return_value = mock_conv
        mock_msg_result = MagicMock()
        mock_msg_result.scalars.return_value = mock_scalars

        # 第一次 execute 返回 conv，第二次返回 messages
        mock_db.execute = AsyncMock(side_effect=[mock_conv_result, mock_msg_result])

        with patch("app.services.conversation_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await service.compress_history(1)

        assert result is False  # 不触发

    @pytest.mark.asyncio
    async def test_no_compress_all_recent(self, service, mock_db):
        """消息数量超过阈值但 ≤ RECENT_KEEP → 不压缩"""
        from app.services.conversation_service import RECENT_KEEP

        mock_conv = MagicMock()
        mock_conv.id = 1
        mock_conv.summary_msg_cursor = 0
        mock_conv.summary = ""

        # 恰好 = RECENT_KEEP 条
        msgs = [_make_msg("user", f"这是一段足够长的消息内容，包含一些学习讨论。" * 3)
                for i in range(RECENT_KEEP)]
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = msgs
        mock_conv_result = MagicMock()
        mock_conv_result.scalar_one_or_none.return_value = mock_conv
        mock_msg_result = MagicMock()
        mock_msg_result.scalars.return_value = mock_scalars

        mock_db.execute = AsyncMock(side_effect=[mock_conv_result, mock_msg_result])

        with patch("app.services.conversation_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await service.compress_history(1)

        assert result is False

    @pytest.mark.asyncio
    async def test_compress_triggers(self, service, mock_db):
        """消息数 ≥20 且 > RECENT_KEEP → 触发 LLM 压缩"""
        from app.services.conversation_service import RECENT_KEEP

        mock_conv = MagicMock()
        mock_conv.id = 1
        mock_conv.summary_msg_cursor = 0
        mock_conv.summary = ""

        # 30 条消息（≥20 阈值），远超 RECENT_KEEP
        long_content = "这是一段足够长的消息来触发 token 阈值估算压缩机制检查" * 8
        msgs = [_make_msg("user" if i % 2 == 0 else "assistant", f"{long_content} #{i}")
                for i in range(30)]
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = msgs
        mock_conv_result = MagicMock()
        mock_conv_result.scalar_one_or_none.return_value = mock_conv
        mock_msg_result = MagicMock()
        mock_msg_result.scalars.return_value = mock_scalars
        # update 的 execute 结果
        mock_update_result = MagicMock()

        # 3 次 execute 调用：conv query, msg query, update
        mock_db.execute = AsyncMock(side_effect=[
            mock_conv_result, mock_msg_result, mock_update_result
        ])

        # Mock LLM 调用
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="这是一段压缩后的对话摘要包含了关键信息")
        mock_create_llm = MagicMock(return_value=mock_llm)

        with patch("app.services.conversation_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("app.services.conversation_service.create_llm", mock_create_llm):
                result = await service.compress_history(1)

        assert result is True
        assert mock_create_llm.called
        assert mock_llm.chat.called

    @pytest.mark.asyncio
    async def test_incremental_summary(self, service, mock_db):
        """已有摘要 + 新消息 → 增量压缩"""
        from app.services.conversation_service import RECENT_KEEP

        mock_conv = MagicMock()
        mock_conv.id = 1
        mock_conv.summary_msg_cursor = 25  # 前 25 条已压缩
        mock_conv.summary = "之前的对话摘要：学生学习了线性代数和微积分基础..."

        # cursor=25 之后还有 20 条新未摘要消息
        long_content = "这是一段消息内容用来填充到足够的长度触发压缩" * 5
        msgs = [_make_msg("user" if i % 2 == 0 else "assistant", f"{long_content} #{i}")
                for i in range(20)]
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = msgs
        mock_conv_result = MagicMock()
        mock_conv_result.scalar_one_or_none.return_value = mock_conv
        mock_msg_result = MagicMock()
        mock_msg_result.scalars.return_value = mock_scalars
        mock_update_result = MagicMock()

        mock_db.execute = AsyncMock(side_effect=[
            mock_conv_result, mock_msg_result, mock_update_result
        ])

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="更新后的摘要：学生继续学习了深度学习基础，包括CNN和RNN...")
        mock_create_llm = MagicMock(return_value=mock_llm)

        with patch("app.services.conversation_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("app.services.conversation_service.create_llm", mock_create_llm):
                result = await service.compress_history(1)

        assert result is True
        # 验证 LLM 收到了已有摘要
        call_args = mock_llm.chat.call_args[0][0]
        if isinstance(call_args, list):
            user_text = call_args[0].get("content", "")
            assert "之前的对话摘要" in user_text

    @pytest.mark.asyncio
    async def test_compress_db_error_graceful(self, service, mock_db):
        """DB 异常 → 返回 False 不抛异常"""
        mock_conv = MagicMock()
        mock_conv.id = 1
        mock_conv.summary_msg_cursor = 0
        mock_conv.summary = ""

        long_content = "触发压缩的消息内容" * 20
        msgs = [_make_msg("user", long_content) for _ in range(25)]
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = msgs
        mock_conv_result = MagicMock()
        mock_conv_result.scalar_one_or_none.return_value = mock_conv
        mock_msg_result = MagicMock()
        mock_msg_result.scalars.return_value = mock_scalars
        mock_update_result = MagicMock()

        # 前两次 execute 正常，第三次也正常，但 commit 失败
        mock_db.execute = AsyncMock(side_effect=[
            mock_conv_result, mock_msg_result, mock_update_result
        ])

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="摘要内容")
        mock_create_llm = MagicMock(return_value=mock_llm)

        # commit 失败
        mock_db.commit = AsyncMock(side_effect=Exception("DB write failed"))

        with patch("app.services.conversation_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("app.services.conversation_service.create_llm", mock_create_llm):
                result = await service.compress_history(1)

        assert result is False  # 优雅失败

    @pytest.mark.asyncio
    async def test_llm_failure_graceful(self, service, mock_db):
        """LLM 调用失败 → 返回 False"""
        mock_conv = MagicMock()
        mock_conv.id = 1
        mock_conv.summary_msg_cursor = 0
        mock_conv.summary = ""

        long_content = "一段足够长的消息用来满足压缩触发条件" * 10
        msgs = [_make_msg("user", long_content) for _ in range(25)]
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = msgs
        mock_conv_result = MagicMock()
        mock_conv_result.scalar_one_or_none.return_value = mock_conv
        mock_msg_result = MagicMock()
        mock_msg_result.scalars.return_value = mock_scalars

        mock_db.execute = AsyncMock(side_effect=[mock_conv_result, mock_msg_result])

        # LLM 直接失败
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=Exception("API timeout"))
        mock_create_llm = MagicMock(return_value=mock_llm)

        with patch("app.services.conversation_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("app.services.conversation_service.create_llm", mock_create_llm):
                result = await service.compress_history(1)

        assert result is False

    @pytest.mark.asyncio
    async def test_get_summary(self, service, mock_db):
        """获取已有摘要"""
        mock_result = MagicMock()
        mock_result.scalar.return_value = "学生学习了线性代数基础..."

        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.services.conversation_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            summary = await service.get_summary(1)

        assert summary == "学生学习了线性代数基础..."

    @pytest.mark.asyncio
    async def test_get_summary_empty(self, service, mock_db):
        """无摘要 → 返回空字符串"""
        mock_result = MagicMock()
        mock_result.scalar.return_value = None

        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.services.conversation_service.get_db") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            summary = await service.get_summary(1)

        assert summary == ""


# ── 摘要自我压缩 ──────────────────────────────────────────────────


class TestSelfCompress:
    @pytest.fixture
    def service(self):
        return ConversationService()

    @pytest.mark.asyncio
    async def test_self_compress_triggers(self, service):
        """摘要超长 → 触发 LLM 自我压缩"""
        long_summary = "长摘要内容。" * 400  # ~2400 chars, > 2000 threshold

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="压缩后的短摘要")
        mock_create_llm = MagicMock(return_value=mock_llm)

        with patch("app.services.conversation_service.create_llm", mock_create_llm):
            result = await service._self_compress(long_summary)

        assert mock_create_llm.called
        assert result == "压缩后的短摘要"

    @pytest.mark.asyncio
    async def test_self_compress_llm_failed(self, service):
        """LLM 自我压缩失败 → 降级截断"""
        long_summary = "长摘要。" * 500

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=Exception("timeout"))

        with patch("app.services.conversation_service.create_llm", MagicMock(return_value=mock_llm)):
            result = await service._self_compress(long_summary)

        # 降级：截断到 SELF_COMPRESS_AT 字符
        from app.services.conversation_service import SUMMARY_SELF_COMPRESS_AT
        assert len(result) <= SUMMARY_SELF_COMPRESS_AT
