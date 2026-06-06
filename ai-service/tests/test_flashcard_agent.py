"""Tests for FlashCardAgent — 使用真实 LLM 调用验证"""

import pytest

from app.agents.flashcard_agent import FlashCardAgent, FlashCardState


@pytest.fixture
def agent():
    return FlashCardAgent()


class TestFlashCardAgentExtract:
    """提取节点测试 — 不依赖 LLM"""

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
        assert len(result["key_concepts"]) >= 1
        assert "content_summary" in result

    @pytest.mark.asyncio
    async def test_extract_empty_blocks(self, agent):
        state: FlashCardState = {"topic": "x", "content_blocks": []}
        result = await agent._extract_node(state)
        assert result["key_concepts"] == []
        assert "content_summary" in result


class TestFlashCardAgentGenerate:
    """生成节点测试 — 使用真实 LLM"""

    @pytest.mark.asyncio
    async def test_generate_cards_from_concepts(self, agent):
        state: FlashCardState = {
            "topic": "梯度下降",
            "key_concepts": ["梯度下降原理", "学习率"],
            "content_summary": "梯度下降是一种优化算法...",
        }
        result = await agent._generate_node(state)
        assert result["blocks"][0]["type"] == "flash_cards"
        cards = result["blocks"][0]["content"]["cards"]
        assert len(cards) >= 1
        assert all("front" in c and "back" in c for c in cards)

    @pytest.mark.asyncio
    async def test_generate_with_single_concept(self, agent):
        state: FlashCardState = {
            "topic": "过拟合",
            "key_concepts": ["过拟合"],
            "content_summary": "过拟合是机器学习中的常见问题",
        }
        result = await agent._generate_node(state)
        assert result["blocks"][0]["type"] == "flash_cards"
        cards = result["blocks"][0]["content"]["cards"]
        assert len(cards) >= 1


class TestFlashCardAgentIntegration:
    """全集成的测试"""

    @pytest.mark.asyncio
    async def test_full_graph_run(self, agent):
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
        assert len(blocks) >= 1
        assert blocks[0]["type"] == "flash_cards"
        cards = blocks[0]["content"]["cards"]
        assert len(cards) >= 1
        assert all("front" in c and "back" in c for c in cards)

    @pytest.mark.asyncio
    async def test_full_graph_run_empty_blocks(self, agent):
        state = {"topic": "空主题", "content_blocks": []}
        result = await agent.run(state)
        blocks = result.get("blocks", [])
        assert len(blocks) >= 1
        assert blocks[0]["type"] == "flash_cards"
        cards = blocks[0]["content"]["cards"]
        assert len(cards) == 0

    def test_turn_summary(self, agent):
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
