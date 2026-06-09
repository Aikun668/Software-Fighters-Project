"""Tests for ConversationService: 会话持久化"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.conversation_service import ConversationService, get_conversation_service


class TestConversationService:
    @pytest.fixture
    def service(self):
        svc = ConversationService()
        svc._client = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_get_or_create_existing(self, service):
        """已有会话 -> 返回已有"""
        service._client.get_conversation = AsyncMock(return_value={
            "id": 42, "user_id": 1, "title": "测试",
        })

        conv = await service.get_or_create_conversation(1, 42)

        assert conv["id"] == 42
        assert conv["user_id"] == 1

    @pytest.mark.asyncio
    async def test_get_or_create_new(self, service):
        """无 conversation_id -> 创建新会话"""
        service._client.create_conversation = AsyncMock(return_value={
            "id": 99, "user_id": 1,
        })

        conv = await service.get_or_create_conversation(1)

        assert conv["user_id"] == 1
        assert conv["id"] == 99

    @pytest.mark.asyncio
    async def test_get_or_create_not_found_fallback(self, service):
        """conversation_id 存在但找不到 -> 创建新的"""
        service._client.get_conversation = AsyncMock(return_value=None)
        service._client.create_conversation = AsyncMock(return_value={
            "id": 100, "user_id": 1,
        })

        conv = await service.get_or_create_conversation(1, 999)

        assert conv["user_id"] == 1
        assert conv["id"] == 100

    @pytest.mark.asyncio
    async def test_get_or_create_api_failure(self, service):
        """Java API 创建失败 -> 抛出 RuntimeError"""
        service._client.create_conversation = AsyncMock(return_value=None)

        with pytest.raises(RuntimeError, match="无法为用户"):
            await service.get_or_create_conversation(1)

    @pytest.mark.asyncio
    async def test_load_history(self, service):
        """加载会话历史"""
        service._client.load_messages = AsyncMock(return_value=[
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮你？"},
            {"role": "user", "content": "什么是CNN？"},
        ])

        history = await service.load_history(1)

        assert len(history) == 3
        assert history[0] == {"role": "user", "content": "你好"}
        assert history[2] == {"role": "user", "content": "什么是CNN？"}

    @pytest.mark.asyncio
    async def test_load_history_empty(self, service):
        """空会话 -> 返回空列表"""
        service._client.load_messages = AsyncMock(return_value=[])

        history = await service.load_history(1)

        assert history == []

    @pytest.mark.asyncio
    async def test_load_history_api_error(self, service):
        """API 异常 -> 返回空列表（不抛异常）"""
        service._client.load_messages = AsyncMock(side_effect=Exception("API error"))

        history = await service.load_history(1)

        assert history == []

    @pytest.mark.asyncio
    async def test_save_messages(self, service):
        """保存一轮对话"""
        service._client.save_messages = AsyncMock(return_value=None)

        await service.save_messages(1, "用户消息", "AI回复")

        service._client.save_messages.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_messages_api_error(self, service):
        """保存失败 -> 不抛异常"""
        service._client.save_messages = AsyncMock(side_effect=Exception("API error"))

        # 不应 raise
        await service.save_messages(1, "msg", "reply")

    def test_singleton(self):
        s1 = get_conversation_service()
        s2 = get_conversation_service()
        assert s1 is s2


# ── Token 估算 & 格式化 ──────────────────────────────────────────


class TestEstimateTokens:
    def test_empty_messages(self):
        from app.services.conversation_service import _estimate_tokens
        assert _estimate_tokens([]) == 0

    def test_simple_messages(self):
        from app.services.conversation_service import _estimate_tokens
        msgs = [
            {"role": "user", "content": "你好" * 50},
            {"role": "assistant", "content": "你好呀" * 50},
        ]
        est = _estimate_tokens(msgs)
        assert est == 125

    def test_multimodal_content(self):
        from app.services.conversation_service import _estimate_tokens
        msgs = [
            {"role": "user", "content": [
                {"type": "text", "text": "这段文字200个字符" * 10},
                {"type": "image_url", "image_url": {"url": "..."}},
            ]},
        ]
        est = _estimate_tokens(msgs)
        assert est > 0
        assert est < 200

    def test_threshold_trigger(self):
        from app.services.conversation_service import _estimate_tokens, COMPRESS_TOKEN_THRESHOLD
        msgs = [
            {"role": "user" if i % 2 == 0 else "assistant",
             "content": "这是一段中等长度的辅导对话消息，包含一些技术讨论内容。" * 10}
            for i in range(25)
        ]
        est = _estimate_tokens(msgs)
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
        assert "[学生]" not in result
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
        svc = ConversationService()
        svc._client = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_no_compress_when_few_messages(self, service):
        """消息太少 -> 不触发压缩"""
        service._client.get_conversation = AsyncMock(return_value={
            "id": 1, "summary_msg_cursor": 0, "summary": "",
        })
        msgs = [{"role": "user", "content": f"消息{i}"} for i in range(10)]
        service._client.load_messages_raw = AsyncMock(return_value=msgs)

        result = await service.compress_history(1, user_id=1)

        assert result is False

    @pytest.mark.asyncio
    async def test_no_compress_all_recent(self, service):
        """消息数量超过阈值但 <= RECENT_KEEP -> 不压缩"""
        from app.services.conversation_service import RECENT_KEEP

        service._client.get_conversation = AsyncMock(return_value={
            "id": 1, "summary_msg_cursor": 0, "summary": "",
        })
        msgs = [{"role": "user", "content": "这是一段足够长的消息内容，包含一些学习讨论。" * 3}
                for _ in range(RECENT_KEEP)]
        service._client.load_messages_raw = AsyncMock(return_value=msgs)

        result = await service.compress_history(1, user_id=1)

        assert result is False

    @pytest.mark.asyncio
    async def test_compress_triggers(self, service):
        """消息数 >=20 且 > RECENT_KEEP -> 触发 LLM 压缩"""
        from app.services.conversation_service import RECENT_KEEP

        service._client.get_conversation = AsyncMock(return_value={
            "id": 1, "summary_msg_cursor": 0, "summary": "",
        })
        long_content = "这是一段足够长的消息来触发 token 阈值估算压缩机制检查" * 8
        msgs = [{"role": "user" if i % 2 == 0 else "assistant",
                 "content": f"{long_content} #{i}"} for i in range(30)]
        service._client.load_messages_raw = AsyncMock(return_value=msgs)
        service._client.update_conversation = AsyncMock(return_value={"id": 1})

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="这是一段压缩后的对话摘要包含了关键信息")
        mock_create_llm = MagicMock(return_value=mock_llm)

        with patch("app.services.conversation_service.create_llm", mock_create_llm):
            result = await service.compress_history(1, user_id=1)

        assert result is True
        assert mock_create_llm.called
        assert mock_llm.chat.called

    @pytest.mark.asyncio
    async def test_incremental_summary(self, service):
        """已有摘要 + 新消息 -> 增量压缩"""
        service._client.get_conversation = AsyncMock(return_value={
            "id": 1, "summary_msg_cursor": 25,
            "summary": "之前的对话摘要：学生学习了线性代数和微积分基础...",
        })
        long_content = "这是一段消息内容用来填充到足够的长度触发压缩" * 5
        msgs = [{"role": "user" if i % 2 == 0 else "assistant",
                 "content": f"{long_content} #{i}"} for i in range(20)]
        service._client.load_messages_raw = AsyncMock(return_value=msgs)
        service._client.update_conversation = AsyncMock(return_value={"id": 1})

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="更新后的摘要：学生继续学习了深度学习基础，包括CNN和RNN...")
        mock_create_llm = MagicMock(return_value=mock_llm)

        with patch("app.services.conversation_service.create_llm", mock_create_llm):
            result = await service.compress_history(1, user_id=1)

        assert result is True
        call_args = mock_llm.chat.call_args[0][0]
        if isinstance(call_args, list):
            user_text = call_args[0].get("content", "")
            assert "之前的对话摘要" in user_text

    @pytest.mark.asyncio
    async def test_compress_api_error_graceful(self, service):
        """API 异常 -> 返回 False 不抛异常"""
        service._client.get_conversation = AsyncMock(side_effect=Exception("API error"))

        result = await service.compress_history(1, user_id=1)

        assert result is False

    @pytest.mark.asyncio
    async def test_llm_failure_graceful(self, service):
        """LLM 调用失败 -> 返回 False"""
        service._client.get_conversation = AsyncMock(return_value={
            "id": 1, "summary_msg_cursor": 0, "summary": "",
        })
        long_content = "一段足够长的消息用来满足压缩触发条件" * 10
        msgs = [{"role": "user", "content": long_content} for _ in range(25)]
        service._client.load_messages_raw = AsyncMock(return_value=msgs)

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=Exception("API timeout"))
        mock_create_llm = MagicMock(return_value=mock_llm)

        with patch("app.services.conversation_service.create_llm", mock_create_llm):
            result = await service.compress_history(1, user_id=1)

        assert result is False

    @pytest.mark.asyncio
    async def test_get_summary(self, service):
        """获取已有摘要"""
        service._client.get_conversation = AsyncMock(return_value={
            "id": 1, "summary": "学生学习了线性代数基础...",
        })

        summary = await service.get_summary(1, user_id=1)

        assert summary == "学生学习了线性代数基础..."

    @pytest.mark.asyncio
    async def test_get_summary_empty(self, service):
        """无摘要 -> 返回空字符串"""
        service._client.get_conversation = AsyncMock(return_value={})

        summary = await service.get_summary(1, user_id=1)

        assert summary == ""


# ── 摘要自我压缩 ──────────────────────────────────────────────────


class TestSelfCompress:
    @pytest.fixture
    def service(self):
        return ConversationService()

    @pytest.mark.asyncio
    async def test_self_compress_triggers(self, service):
        """摘要超长 -> 触发 LLM 自我压缩"""
        long_summary = "长摘要内容。" * 400

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="压缩后的短摘要")
        mock_create_llm = MagicMock(return_value=mock_llm)

        with patch("app.services.conversation_service.create_llm", mock_create_llm):
            result = await service._self_compress(long_summary)

        assert mock_create_llm.called
        assert result == "压缩后的短摘要"

    @pytest.mark.asyncio
    async def test_self_compress_llm_failed(self, service):
        """LLM 自我压缩失败 -> 降级截断"""
        long_summary = "长摘要。" * 500

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=Exception("timeout"))

        with patch("app.services.conversation_service.create_llm", MagicMock(return_value=mock_llm)):
            result = await service._self_compress(long_summary)

        from app.services.conversation_service import SUMMARY_SELF_COMPRESS_AT
        assert len(result) <= SUMMARY_SELF_COMPRESS_AT
