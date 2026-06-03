import pytest
from unittest.mock import AsyncMock, patch

from app.agents.visualize.visualize_pipeline import VisualizePipeline, VisualizeResult
from app.agents.visualize.analysis_agent import AnalysisAgent
from app.agents.visualize.code_generator_agent import CodeGeneratorAgent
from app.agents.visualize.review_agent import ReviewAgent


@pytest.fixture
def mock_llm():
    m = AsyncMock()
    return m


@pytest.fixture
def pipeline(mock_llm):
    with patch("app.agents.base_agent.create_llm", return_value=mock_llm):
        return VisualizePipeline(use_mock_llm=True)


class TestVisualizePipeline:
    @pytest.mark.asyncio
    async def test_skip_when_no_visualization_needed(self, pipeline, mock_llm):
        mock_llm.chat.return_value = '{"should_visualize": false, "reasoning": "纯文字问题不需要图表"}'
        result = await pipeline.run("什么是 Python", "Python 是一种编程语言。")
        assert result.should_visualize is False
        assert "纯文字问题" in result.reasoning

    @pytest.mark.asyncio
    async def test_full_pipeline_mermaid(self, pipeline, mock_llm):
        mock_llm.chat.side_effect = [
            '{"should_visualize": true, "render_type": "mermaid", "description": "梯度下降流程", "elements": ["输入", "梯度", "更新"], "reasoning": "流程图适合"}',
            '{"code": "graph TD\\n  A[输入] --> B[梯度]", "title": "梯度下降", "notes": "ok"}',
            '{"changed": false, "issues": [], "optimized_code": "", "suggestions": ""}',
        ]
        with patch("app.agents.base_agent.BaseAgent._call_llm_json", side_effect=[
            {"should_visualize": True, "render_type": "mermaid", "description": "梯度下降流程", "elements": ["输入", "梯度", "更新"], "reasoning": "流程图适合"},
            {"code": "graph TD\n  A[输入] --> B[梯度]", "title": "梯度下降", "notes": "ok"},
            {"changed": False, "issues": [], "optimized_code": "", "suggestions": ""},
        ]):
            result = await pipeline.run("解释梯度下降", "梯度下降是一种优化算法。")
            assert result.should_visualize is True
            assert result.render_type == "mermaid"
            assert "graph TD" in result.code
            assert result.title == "梯度下降"

    @pytest.mark.asyncio
    async def test_review_fixes_code(self, pipeline, mock_llm):
        mock_llm.chat.side_effect = [
            '{"should_visualize": true, "render_type": "svg", "description": "神经网络结构", "elements": ["输入层", "隐藏层"], "reasoning": "结构图"}',
            '{"code": "<svg> broken", "title": "神经网络", "notes": ""}',
            '{"changed": true, "issues": ["标签未闭合"], "optimized_code": "<svg></svg>", "suggestions": "已修复"}',
        ]
        result = await pipeline.run("神经网络结构", "神经网络由多层组成。")
        assert result.should_visualize is True
        assert result.code == "<svg></svg>"

    @pytest.mark.asyncio
    async def test_codegen_failure_fallback(self, pipeline, mock_llm):
        with patch("app.agents.base_agent.BaseAgent._call_llm_json", side_effect=[
            {"should_visualize": True, "render_type": "mermaid", "description": "测试", "elements": [], "reasoning": ""},
            {"code": "", "title": "", "notes": ""},
        ]):
            result = await pipeline.run("测试", "回答")
            assert result.should_visualize is False
            assert "代码生成失败" in result.reasoning


class TestVisualizeResult:
    def test_skip_factory(self):
        result = VisualizeResult.skip(reason="test")
        assert result.should_visualize is False
        assert result.reasoning == "test"

    def test_render_priority(self):
        from app.agents.visualize.visualize_pipeline import VisualizePipeline
        assert VisualizePipeline.RENDER_PRIORITY["mermaid"] < VisualizePipeline.RENDER_PRIORITY["svg"]
        assert VisualizePipeline.RENDER_PRIORITY["svg"] < VisualizePipeline.RENDER_PRIORITY["chartjs"]


class TestAnalysisAgent:
    @pytest.mark.asyncio
    async def test_analyze_node(self, mock_llm):
        mock_llm.chat.return_value = '{"should_visualize": true, "render_type": "mermaid", "description": "流程图", "elements": ["A", "B"], "reasoning": "适合图解"}'
        with patch("app.agents.base_agent.create_llm", return_value=mock_llm):
            agent = AnalysisAgent(use_mock_llm=True)
            result = await agent.run({"question": "什么是AI", "answer": "人工智能是..."})
            assert "analysis" in result
            assert result["analysis"]["should_visualize"] is True


class TestCodeGeneratorAgent:
    @pytest.mark.asyncio
    async def test_generate_node(self, mock_llm):
        mock_llm.chat.return_value = '{"code": "graph TD\\n  A --> B", "title": "测试图", "notes": "ok"}'
        with patch("app.agents.base_agent.create_llm", return_value=mock_llm):
            agent = CodeGeneratorAgent(use_mock_llm=True)
            result = await agent.run({
                "render_type": "mermaid",
                "description": "流程图",
                "elements": ["A", "B"],
                "question": "测试",
            })
            assert "code_result" in result
            assert "graph TD" in result["code_result"]["code"]


class TestReviewAgent:
    @pytest.mark.asyncio
    async def test_review_node(self, mock_llm):
        mock_llm.chat.return_value = '{"changed": false, "issues": [], "optimized_code": "", "suggestions": ""}'
        with patch("app.agents.base_agent.create_llm", return_value=mock_llm):
            agent = ReviewAgent(use_mock_llm=True)
            result = await agent.run({
                "render_type": "mermaid",
                "code": "graph TD\\n  A --> B",
                "description": "流程图",
            })
            assert "review_result" in result
            assert result["review_result"]["changed"] is False