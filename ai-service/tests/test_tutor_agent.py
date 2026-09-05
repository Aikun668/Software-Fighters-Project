"""Tests for TutorAgent: message truncation + multi-turn RAG query + conversation persistence."""

import pytest
from unittest.mock import AsyncMock, patch

from app.agents.tutor_agent import (
    TutorAgent,
    MAX_MESSAGES,
    HEAD_KEEP,
    RAG_QUERY_TURNS,
    RAG_QUERY_MAX_CHARS,
)


class TestMessageTruncation:
    """消息截断逻辑"""

    def test_under_limit_unchanged(self):
        msgs = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        result = TutorAgent._truncate_messages(msgs)
        assert len(result) == 10
        assert result == msgs

    def test_at_limit_unchanged(self):
        msgs = [{"role": "user", "content": f"msg{i}"} for i in range(MAX_MESSAGES)]
        result = TutorAgent._truncate_messages(msgs)
        assert len(result) == MAX_MESSAGES

    def test_over_limit_truncated(self):
        msgs = [{"role": "user", "content": f"msg{i}"} for i in range(40)]
        result = TutorAgent._truncate_messages(msgs)

        assert len(result) == MAX_MESSAGES
        # 前 HEAD_KEEP 条保留
        assert result[0]["content"] == "msg0"
        assert result[HEAD_KEEP - 1]["content"] == f"msg{HEAD_KEEP - 1}"
        # 最后一条是原始最后一条
        assert result[-1]["content"] == "msg39"

    def test_empty_list(self):
        result = TutorAgent._truncate_messages([])
        assert result == []

    def test_mixed_roles(self):
        """user/assistant 交替的对话同样截断"""
        msgs = []
        for i in range(50):
            msgs.append({"role": "user", "content": f"q{i}"})
            msgs.append({"role": "assistant", "content": f"a{i}"})

        result = TutorAgent._truncate_messages(msgs)
        assert len(result) == MAX_MESSAGES
        assert result[0]["content"] == "q0"
        assert result[1]["content"] == "a0"
        assert result[-1]["content"] == "a49"


class TestRagQueryConstruction:
    """多轮 RAG query 构建"""

    def test_single_message_returns_directly(self):
        msgs = [{"role": "user", "content": "什么是CNN？"}]
        result = TutorAgent._build_rag_query(msgs)
        assert result == "什么是CNN？"

    def test_combines_last_n_user_messages(self):
        msgs = [
            {"role": "user", "content": "什么是CNN？"},
            {"role": "assistant", "content": "CNN是卷积神经网络..."},
            {"role": "user", "content": "那和RNN的区别？"},
            {"role": "assistant", "content": "CNN处理网格数据，RNN处理序列..."},
            {"role": "user", "content": "第1个问题的卷积能详细讲吗？"},
        ]
        result = TutorAgent._build_rag_query(msgs)
        # 应包含最近 RAG_QUERY_TURNS 条用户消息
        assert "卷积" in result
        assert "RNN" in result or "CNN" in result
        assert " | " in result  # 分隔符

    def test_only_user_messages_considered(self):
        """只取用户消息，跳过 assistant"""
        msgs = [
            {"role": "assistant", "content": "你好"},
            {"role": "assistant", "content": "有什么可以帮你"},
            {"role": "user", "content": "讲一下梯度下降"},
        ]
        result = TutorAgent._build_rag_query(msgs)
        assert result == "讲一下梯度下降"

    def test_truncates_long_query(self):
        """超长拼接时截断"""
        long_msg1 = "A" * 200
        long_msg2 = "B" * 200
        long_msg3 = "C" * 200
        msgs = [
            {"role": "user", "content": long_msg1},
            {"role": "user", "content": long_msg2},
            {"role": "user", "content": long_msg3},
        ]
        result = TutorAgent._build_rag_query(msgs)
        assert len(result) <= RAG_QUERY_MAX_CHARS
        # 最后一条完整消息保留
        assert long_msg3 in result

    def test_non_dict_message_handled(self):
        """非 dict 消息被安全跳过"""
        msgs = [
            "不是字典的字符串",
            {"role": "user", "content": "有效消息"},
        ]
        result = TutorAgent._build_rag_query(msgs)
        assert "有效消息" in result

    def test_empty_messages(self):
        result = TutorAgent._build_rag_query([])
        assert result == ""


class TestTutorAgentGraph:
    """TutorAgent graph 端到端（mock LLM）"""

    @pytest.fixture
    def mock_llm(self):
        m = AsyncMock()
        m.chat_stream = AsyncMock()
        m.chat_stream.__aiter__ = lambda self: iter(["好的，我来回答你的问题。"])
        return m

    @pytest.fixture
    def agent(self, mock_llm):
        with patch("app.agents.base_agent.create_llm", return_value=mock_llm):
            a = TutorAgent(use_mock_llm=True)
            a.llm = mock_llm
            return a

    @pytest.mark.asyncio
    async def test_truncation_applied_in_respond(self, agent, mock_llm):
        """_respond_node 传给 LLM 的消息是截断后的"""
        long_history = []
        for i in range(40):
            long_history.append({"role": "user", "content": f"q{i}"})
            long_history.append({"role": "assistant", "content": f"a{i}"})

        captured_messages = []

        async def capture(*args, **kwargs):
            captured_messages.extend(args[0] if args else [])
            for char in ["好", "的"]:
                yield char

        mock_llm.chat_stream = capture

        state = {
            "messages": long_history,
            "student_profile": {},
            "knowledge_context": "test context",
        }
        await agent._respond_node(state)

        assert len(captured_messages) <= MAX_MESSAGES

    @pytest.mark.asyncio
    async def test_rag_query_uses_multi_turn(self, agent):
        """_retrieve_node 使用多轮用户消息构建 query"""
        msgs = [
            {"role": "user", "content": "CNN是什么"},
            {"role": "assistant", "content": "..."},
            {"role": "user", "content": "第1个问题里的卷积"},
        ]
        state = {"messages": msgs}

        with patch.object(
            agent, "_build_rag_query", wraps=agent._build_rag_query
        ) as spy:
            await agent._retrieve_node(state)
            spy.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_failure_returns_fallback(self, agent, mock_llm):
        """LLM 调用失败 → 返回兜底文案"""

        async def failing_stream(*args, **kwargs):
            raise RuntimeError("LLM down")
            yield  # unreachable, makes it an async generator

        mock_llm.chat_stream = failing_stream

        state = {
            "messages": [{"role": "user", "content": "测试"}],
            "student_profile": {},
            "knowledge_context": "",
        }
        result = await agent._respond_node(state)
        assert "抱歉" in result["response"]


class TestConversationFoundationWiring:
    """真实 Tutor 出口必须消费精简上下文，并对空回答只重试一次。"""

    @pytest.mark.asyncio
    async def test_retries_empty_reply_with_filtered_context(self, monkeypatch):
        class ScriptedLLM:
            def __init__(self):
                self.calls = []

            async def chat_stream(self, messages, system_prompt=""):
                self.calls.append((messages, system_prompt))
                reply = "" if len(self.calls) == 1 else "TCP 三次握手用于确认双方收发能力。"
                if reply:
                    yield reply

        with patch("app.agents.base_agent.create_llm", return_value=AsyncMock()):
            agent = TutorAgent(use_mock_llm=True)
        llm = ScriptedLLM()
        agent.llm = llm

        class GeneralRouter:
            def classify(self, *args, **kwargs):
                return "general"

            def should_inject_kb(self, *args, **kwargs):
                return False

            def should_inject_analogy(self, *args, **kwargs):
                return False

        async def clear_clarity(_message):
            return {"has_clear_goal": True, "has_blocker": False, "needs_clarification": False}

        monkeypatch.setattr("app.agents.tutor_agent.get_domain_router", lambda: GeneralRouter())
        monkeypatch.setattr(agent, "_classify_clarity", clear_clarity)

        result = await agent._respond_node({
            "messages": [
                {"role": "user", "content": "我们在学 TCP/IP。"},
                {"role": "assistant", "content": "可以从握手开始理解。"},
                {"role": "user", "content": "TCP 为什么需要三次握手？"},
            ],
            "student_profile": {
                "cognitive_style": "偏好先直观后公式",
                "interest_direction": "摄影",
            },
            "knowledge_context": "",
        })

        assert result["response"] == "TCP 三次握手用于确认双方收发能力。"
        assert len(llm.calls) == 2
        first_messages, first_system = llm.calls[0]
        assert first_messages[-1] == {"role": "user", "content": "TCP 为什么需要三次握手？"}
        assert "偏好先直观后公式" in first_system
        assert "摄影" not in first_system


class TestMultimodalContentExtraction:
    """多模态 content 的文本提取"""

    def test_string_content_returns_as_is(self):
        result = TutorAgent._extract_text("你好")
        assert result == "你好"

    def test_multimodal_array_extracts_text(self):
        content = [
            {"type": "text", "text": "这张图里的公式对吗？"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/..."}},
        ]
        result = TutorAgent._extract_text(content)
        assert result == "这张图里的公式对吗？"

    def test_multimodal_multiple_text_parts(self):
        content = [
            {"type": "text", "text": "第一部分"},
            {"type": "text", "text": "第二部分"},
        ]
        result = TutorAgent._extract_text(content)
        assert result == "第一部分 第二部分"

    def test_empty_multimodal_returns_empty(self):
        assert TutorAgent._extract_text([]) == ""
        assert TutorAgent._extract_text([{"type": "image_url", "image_url": {}}]) == ""

    def test_non_dict_items_skipped(self):
        content = ["not a dict", {"type": "text", "text": "有效文本"}]
        result = TutorAgent._extract_text(content)
        assert result == "有效文本"


class TestMultimodalRagQuery:
    """多模态消息的 RAG query 构建"""

    def test_multimodal_current_turn_included(self):
        msgs = [
            {"role": "user", "content": "什么是梯度下降？"},
            {"role": "assistant", "content": "梯度下降是..."},
            {"role": "user", "content": [
                {"type": "text", "text": "结合这张图解释"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}},
            ]},
        ]
        result = TutorAgent._build_rag_query(msgs)
        assert "梯度下降" in result
        assert "结合这张图解释" in result

    def test_image_only_message_handled(self):
        """纯图片消息（无文本）不会被遗漏"""
        msgs = [
            {"role": "user", "content": "前一轮问题"},
            {"role": "assistant", "content": "..."},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
            ]},
        ]
        result = TutorAgent._build_rag_query(msgs)
        assert "前一轮问题" in result

    def test_mixed_text_and_multimodal_history(self):
        """历史中有纯文本，当前轮是多模态"""
        msgs = [
            {"role": "user", "content": "历史问题1"},
            {"role": "assistant", "content": "历史回答1"},
            {"role": "user", "content": "历史问题2"},
            {"role": "assistant", "content": "历史回答2"},
            {"role": "user", "content": [
                {"type": "text", "text": "当前问题"},
                {"type": "image_url", "image_url": {"url": "data:image/webp;base64,..."}},
            ]},
        ]
        result = TutorAgent._build_rag_query(msgs)
        assert "历史问题2" in result
        assert "当前问题" in result
        assert "data:image" not in result  # 图片 URL 不应出现在 query 中


class TestTruncationWithMultimodal:
    """多模态消息的截断"""

    def test_multimodal_messages_counted_as_one(self):
        """多模态内容数组仍算作一条消息"""
        msgs = []
        for i in range(30):
            msgs.append({"role": "user", "content": f"msg{i}"})
            msgs.append({"role": "assistant", "content": f"ans{i}"})
        msgs[-2] = {"role": "user", "content": [
            {"type": "text", "text": "last question"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}},
        ]}

        result = TutorAgent._truncate_messages(msgs)
        assert len(result) == MAX_MESSAGES
        last_user = [m for m in result if m["role"] == "user"][-1]
        assert isinstance(last_user["content"], list)  # content 仍是数组
