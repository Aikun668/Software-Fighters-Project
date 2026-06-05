"""Tests for ReadingAgent — 拓展阅读推荐智能体"""

import pytest

from app.agents.reading_agent import ReadingAgent


class TestReadingAgent:
    @pytest.fixture
    def agent(self):
        return ReadingAgent()

    def test_agent_instantiation(self):
        agent = ReadingAgent()
        assert agent.agent_name == "reading_agent"
        assert agent._compiled_graph is not None

    @pytest.mark.asyncio
    async def test_generate_node_with_profile(self, agent):
        state = {
            "topic": "机器学习",
            "student_profile": {
                "knowledge_base": 50,
                "interest_direction": ["计算机视觉", "自然语言处理"],
            },
        }
        result = await agent._generate_node(state)
        blocks = result.get("blocks", [])
        assert len(blocks) >= 1
        assert blocks[0]["type"] == "reading"

    @pytest.mark.asyncio
    async def test_generate_node_empty_profile(self, agent):
        state = {
            "topic": "Python基础",
            "student_profile": {},
        }
        result = await agent._generate_node(state)
        blocks = result.get("blocks", [])
        assert len(blocks) >= 1
        assert blocks[0]["type"] == "reading"

    def test_render_content_with_suggestions(self, agent):
        suggestions = [
            {
                "topic": "Transformer架构详解",
                "rationale": "深入理解注意力机制，对学习NLP至关重要",
                "source": "Attention Is All You Need (2017)",
            },
            {
                "topic": "BERT预训练模型",
                "rationale": "了解预训练+微调范式",
                "source": "BERT论文 + HuggingFace教程",
            },
        ]
        content = agent._render_content("深度学习", suggestions)
        assert "Transformer架构详解" in content
        assert "📚" in content
        assert "Attention Is All You Need" in content

    def test_render_content_empty_suggestions(self, agent):
        content = agent._render_content("测试主题", [])
        assert "测试主题 拓展阅读" in content
        assert "入门指南" in content or "进阶" in content or "实践项目" in content

    def test_render_content_with_missing_source(self, agent):
        suggestions = [
            {"topic": "梯度下降优化", "rationale": "理解优化算法的核心"},
        ]
        content = agent._render_content("机器学习", suggestions)
        assert "梯度下降优化" in content
        assert "理解优化算法" in content

    @pytest.mark.asyncio
    async def test_run_integration(self, agent):
        state = {
            "topic": "强化学习",
            "student_profile": {
                "knowledge_base": 70,
                "learning_goal": "掌握DQN算法",
                "interest_direction": ["游戏AI"],
            },
        }
        result = await agent.run(state)
        blocks = result.get("blocks", [])
        assert len(blocks) >= 1
        assert blocks[0]["type"] == "reading"
