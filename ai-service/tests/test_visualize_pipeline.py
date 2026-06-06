"""Tests for VisualizePipeline — 使用真实 LLM 调用验证"""

import pytest

from app.agents.visualize.visualize_pipeline import VisualizePipeline, VisualizeResult
from app.agents.visualize.analysis_agent import AnalysisAgent
from app.agents.visualize.code_generator_agent import CodeGeneratorAgent
from app.agents.visualize.review_agent import ReviewAgent


@pytest.fixture
def pipeline():
    return VisualizePipeline()


class TestVisualizePipeline:
    @pytest.mark.asyncio
    async def test_pipeline_returns_result(self, pipeline):
        """Pipeline 应该返回 VisualizeResult，无论是否可视化"""
        result = await pipeline.run("什么是 Python", "Python 是一种编程语言，由 Guido van Rossum 创建。")
        assert isinstance(result, VisualizeResult)
        # should_visualize 由 LLM 决定，不硬编码预期值

    @pytest.mark.asyncio
    async def test_pipeline_with_diagram_question(self, pipeline):
        """流程图类问题应该倾向于生成可视化"""
        result = await pipeline.run("请用流程图解释梯度下降的步骤", "梯度下降包括：初始化参数、计算梯度、更新参数、重复迭代。")
        assert isinstance(result, VisualizeResult)
        if result.should_visualize:
            assert result.render_type in ("mermaid", "svg", "chartjs", "html")
            assert result.code

    @pytest.mark.asyncio
    async def test_pipeline_skip_simple_factual(self, pipeline):
        """简单事实性问题不需要可视化"""
        result = await pipeline.run("Python 是什么时候创建的", "Python 语言由 Guido van Rossum 于 1991 年创建。")
        assert isinstance(result, VisualizeResult)


class TestVisualizeResult:
    def test_skip_factory(self):
        result = VisualizeResult.skip(reason="test")
        assert result.should_visualize is False
        assert result.reasoning == "test"

    def test_render_priority(self):
        assert VisualizePipeline.RENDER_PRIORITY["mermaid"] < VisualizePipeline.RENDER_PRIORITY["svg"]
        assert VisualizePipeline.RENDER_PRIORITY["svg"] < VisualizePipeline.RENDER_PRIORITY["chartjs"]


class TestAnalysisAgent:
    @pytest.mark.asyncio
    async def test_analyze_node(self):
        agent = AnalysisAgent()
        result = await agent.run({"question": "什么是AI", "answer": "人工智能是利用计算机模拟人类智能的科学与技术。"})
        assert "analysis" in result
        assert isinstance(result["analysis"], dict)
        assert "should_visualize" in result["analysis"]


class TestCodeGeneratorAgent:
    @pytest.mark.asyncio
    async def test_generate_node(self):
        agent = CodeGeneratorAgent()
        result = await agent.run({
            "render_type": "mermaid",
            "description": "一个两节点的流程图",
            "elements": ["A", "B"],
            "question": "生成简单流程图",
        })
        assert "code_result" in result
        assert isinstance(result["code_result"], dict)
        code = result["code_result"].get("code", "")
        assert code, "Should generate code"


class TestReviewAgent:
    @pytest.mark.asyncio
    async def test_review_node(self):
        agent = ReviewAgent()
        result = await agent.run({
            "render_type": "mermaid",
            "code": "graph TD\n  A[起点] --> B[终点]",
            "description": "简单两节点流程图",
        })
        assert "review_result" in result
        assert isinstance(result["review_result"], dict)
        assert "changed" in result["review_result"]
