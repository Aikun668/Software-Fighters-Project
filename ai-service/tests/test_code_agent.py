"""Tests for CodeAgent — 代码实操案例生成智能体"""

import pytest

from app.agents.code_agent import CodeAgent


class TestCodeAgent:
    @pytest.fixture
    def agent(self):
        return CodeAgent()

    def test_agent_instantiation(self):
        agent = CodeAgent()
        assert agent.agent_name == "code_agent"
        assert agent._compiled_graph is not None

    @pytest.mark.asyncio
    async def test_generate_node_with_profile(self, agent):
        state = {
            "topic": "线性回归",
            "student_profile": {"knowledge_base": 40},
            "outline": {
                "subsections": [
                    {"heading": "梯度下降", "role": "example", "focus": "实现梯度下降"},
                ],
            },
        }
        result = await agent._generate_node(state)
        blocks = result.get("blocks", [])
        assert len(blocks) >= 1
        assert blocks[0]["type"] == "code"

    @pytest.mark.asyncio
    async def test_generate_node_no_code_subsections(self, agent):
        state = {
            "topic": "Python列表操作",
            "student_profile": {},
            "outline": {"subsections": []},
        }
        result = await agent._generate_node(state)
        blocks = result.get("blocks", [])
        assert len(blocks) >= 1
        assert blocks[0]["type"] == "code"

    def test_render_content_with_code(self, agent):
        content = agent._render_content(
            topic="线性回归",
            language="python",
            code="import numpy as np\n# 实现梯度下降\ndef gradient_descent(X, y, lr=0.01):\n    pass",
            explanation="第一步：导入numpy。第二步：定义梯度下降函数。第三步：迭代更新参数。",
        )
        assert "```python" in content
        assert "gradient_descent" in content
        assert "第一步" in content

    def test_render_content_fallback(self, agent):
        content = agent._render_content(
            topic="决策树",
            language="python",
            code="",
            explanation="",
        )
        assert "```python" in content
        assert "决策树" in content
        assert "example" in content

    @pytest.mark.asyncio
    async def test_run_integration(self, agent):
        state = {
            "topic": "K-means聚类",
            "student_profile": {
                "knowledge_base": 55,
                "cognitive_style": "kinesthetic",
            },
            "outline": {
                "subsections": [
                    {"heading": "K-means算法", "role": "core"},
                    {"heading": "实现K-means", "role": "example", "focus": "手写K-means"},
                ],
            },
        }
        result = await agent.run(state)
        blocks = result.get("blocks", [])
        assert len(blocks) >= 1
        assert blocks[0]["type"] == "code"
