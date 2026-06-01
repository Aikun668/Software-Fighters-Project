"""Tests for FlashCardAgent.

覆盖:
- 从 content_blocks 提取关键概念
- LLM 生成闪卡（mock）
- 非 JSON 回退
- 输出格式验证
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.agents.flashcard_agent import FlashCardAgent, FlashCardState


@pytest.fixture
def mock_llm():
    m = AsyncMock()
    m.chat = AsyncMock(return_value='{"cards": [{"front": "Q1", "back": "A1"}]}')
    return m


@pytest.fixture
def agent(mock_llm):
    with patch("app.agents.base_agent.create_llm", return_value=mock_llm):
        a = FlashCardAgent(use_mock_llm=True)
        a.llm = mock_llm
        return a


class TestFlashCardAgentExtract:
    @pytest.mark.asyncio
    async def test_extract_from_content_blocks(self, agent):
        state: FlashCardState = {
            "topic": "梯度下降",
            "content_blocks": [
                {"type": "section", "heading": "梯度下降原理", "content": "梯度下降是一种优化算法..."},
                {"type": "callout", "heading": "学习率", "content": "学习率控制参数更新步长..."},
            ],
        }
        result = await agent._extract_node(state)

        assert "key_concepts" in result
        assert "梯度下降原理" in result["key_concepts"]
        assert "学习率" in result["key_concepts"]
        assert "content_summary" in result

    @pytest.mark.asyncio
    async def test_extract_empty_blocks(self, agent):
        state: FlashCardState = {"topic": "x", "content_blocks": []}
        result = await agent._extract_node(state)

        assert result["key_concepts"] == []
        assert "content_summary" in result


class TestFlashCardAgentGenerate:
    @pytest.mark.asyncio
    async def test_generate_cards_mock_llm(self, agent, mock_llm):
        mock_llm.chat.return_value = (
            '{"cards": ['
            '{"front": "什么是梯度下降？", "back": "一种优化算法"},'
            '{"front": "学习率的作用？", "back": "控制更新步长"}'
            ']}'
        )
        state: FlashCardState = {
            "topic": "梯度下降",
            "key_concepts": ["梯度下降原理", "学习率"],
            "content_summary": "梯度下降是一种优化算法...",
        }
        result = await agent._generate_node(state)

        assert result["blocks"][0]["type"] == "flash_cards"
        cards = result["blocks"][0]["content"]["cards"]
        assert len(cards) == 2
        assert cards[0]["front"] == "什么是梯度下降？"
        assert cards[0]["back"] == "一种优化算法"

    @pytest.mark.asyncio
    async def test_generate_non_json_fallback(self, agent, mock_llm):
        mock_llm.chat.return_value = "这是普通文本，不是 JSON"
        state: FlashCardState = {
            "topic": "梯度下降",
            "key_concepts": ["梯度下降"],
            "content_summary": "摘要",
        }
        result = await agent._generate_node(state)

        assert result["blocks"][0]["type"] == "flash_cards"
        cards = result["blocks"][0]["content"]["cards"]
        assert len(cards) >= 1

    @pytest.mark.asyncio
    async def test_generate_llm_failure(self, agent, mock_llm):
        mock_llm.chat.side_effect = RuntimeError("LLM 调用失败")
        state: FlashCardState = {
            "topic": "梯度下降",
            "key_concepts": ["梯度下降"],
            "content_summary": "摘要",
        }
        result = await agent._generate_node(state)

        assert result["blocks"][0]["type"] == "flash_cards"
        cards = result["blocks"][0]["content"]["cards"]
        assert len(cards) >= 1


class TestFlashCardAgentIntegration:
    @pytest.mark.asyncio
    async def test_full_run(self, agent, mock_llm):
        mock_llm.chat.return_value = (
            '{"cards": ['
            '{"front": "Q1", "back": "A1"},'
            '{"front": "Q2", "back": "A2"},'
            '{"front": "Q3", "back": "A3"}'
            ']}'
        )
        state: FlashCardState = {
            "topic": "梯度下降",
            "key_concepts": ["原理"],
            "content_summary": "内容...",
        }
        result = await agent._generate_node(state)

        blocks = result.get("blocks", [])
        assert len(blocks) > 0
        assert blocks[0]["type"] == "flash_cards"
        cards = blocks[0]["content"]["cards"]
        assert len(cards) == 3
        assert all("front" in c and "back" in c for c in cards)

    @pytest.mark.asyncio
    async def test_full_graph_run(self, agent, mock_llm):
        """Verify agent.run() traverses extract→generate via the compiled graph."""
        mock_llm.chat.return_value = (
            '{"cards": ['
            '{"front": "什么是梯度下降？", "back": "一种优化算法"},'
            '{"front": "什么是学习率？", "back": "控制参数更新步长"}'
            ']}'
        )
        state = {
            "topic": "梯度下降",
            "content_blocks": [
                {"type": "section", "heading": "梯度下降原理",
                 "content": "梯度下降是一种优化算法..."},
                {"type": "callout", "heading": "学习率",
                 "content": "学习率控制参数更新步长..."},
            ],
        }
        result = await agent.run(state)

        blocks = result.get("blocks", [])
        assert len(blocks) == 1
        assert blocks[0]["type"] == "flash_cards"
        cards = blocks[0]["content"]["cards"]
        assert len(cards) == 2
        assert cards[0]["front"] == "什么是梯度下降？"
        assert result["response"] == "已生成 2 张记忆闪卡"

    @pytest.mark.asyncio
    async def test_full_graph_run_empty_blocks(self, agent):
        """Verify agent.run() handles empty content_blocks gracefully."""
        state = {"topic": "空主题", "content_blocks": []}
        result = await agent.run(state)

        blocks = result.get("blocks", [])
        assert len(blocks) == 1
        assert blocks[0]["type"] == "flash_cards"
        cards = blocks[0]["content"]["cards"]
        assert len(cards) == 0

    def test_turn_summary(self, agent, mock_llm):
        mock_llm.chat.return_value = '{"cards": [{"front": "Q1", "back": "A1"}]}'
        state = {"topic": "测试"}
        output = {
            "blocks": [{
                "type": "flash_cards",
                "content": {"cards": [{"front": "问题", "back": "答案"}]},
            }],
        }
        summary = agent.create_turn_summary(state, output)

        assert summary.agent_name == "FlashCardAgent"
        assert summary.output_metrics["card_count"] == 1
        assert "问题" in summary.covered_concepts