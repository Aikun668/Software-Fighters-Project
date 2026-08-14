import logging

from dataclasses import dataclass
from typing import Optional

from app.agents.visualize.analysis_agent import AnalysisAgent
from app.agents.visualize.code_generator_agent import CodeGeneratorAgent
from app.agents.visualize.review_agent import ReviewAgent
from app.agents.visualize.utils import validate_visualization
from app.services.llm_service import PROFILE_ANALYSIS, PROFILE_CODE, PROFILE_REVIEW

logger = logging.getLogger(__name__)


@dataclass
class VisualizeResult:
    should_visualize: bool = False
    render_type: str = ""
    code: str = ""
    title: str = ""
    reasoning: str = ""
    warning: str = ""  # 非空时前端可展示免责声明（低置信度等）

    @staticmethod
    def skip(reason: str = "", warning: str = "") -> "VisualizeResult":
        return VisualizeResult(should_visualize=False, reasoning=reason, warning=warning)


class VisualizePipeline:
    RENDER_PRIORITY = {
        "mermaid": 1,
        "svg": 2,
        "chartjs": 3,
        "html": 4,
    }

    def __init__(self, use_mock_llm: bool = False):
        self.analysis_agent = AnalysisAgent(use_mock_llm=use_mock_llm, model_profile=PROFILE_ANALYSIS)
        self.code_generator = CodeGeneratorAgent(use_mock_llm=use_mock_llm, model_profile=PROFILE_CODE)
        self.review_agent = ReviewAgent(use_mock_llm=use_mock_llm, model_profile=PROFILE_REVIEW)

    async def run(self, question: str, answer: str) -> VisualizeResult:
        analysis_state = {"question": question, "answer": answer}
        analysis_output = await self.analysis_agent.run(analysis_state)
        analysis = analysis_output.get("analysis", {})

        if not analysis.get("should_visualize", False):
            return VisualizeResult.skip(reason=analysis.get("reasoning", "无需可视化"))

        confidence = analysis.get("confidence", 0.5)
        warning = ""
        if confidence < 0.6:
            warning = f"该图表由系统根据简短提示自动生成（置信度 {confidence:.2f}），可能存在细节缺失"

        render_type = analysis.get("render_type", "mermaid")
        description = analysis.get("description", "")
        data_description = analysis.get("data_description", "")
        chart_type = analysis.get("chart_type", "")
        visual_elements = analysis.get("visual_elements", [])

        codegen_state = {
            "render_type": render_type,
            "chart_type": chart_type,
            "description": description,
            "data_description": data_description,
            "visual_elements": visual_elements,
            "question": question,
        }
        codegen_output = await self.code_generator.run(codegen_state)
        code_result = codegen_output.get("code_result", {})
        code = code_result.get("code", "")

        if not code:
            return VisualizeResult.skip(reason="代码生成失败")

        review_state = {
            "render_type": render_type,
            "chart_type": chart_type,
            "code": code,
            "description": description,
            "data_description": data_description,
        }

        # ── 确定性验证：通过则跳过 ReviewAgent，省一次 LLM 调用 ──
        valid, error = validate_visualization(code, render_type)
        if valid:
            final_code = code
        else:
            logger.info(
                "可视化代码校验失败 type=%s: %s，调用 ReviewAgent 修复",
                render_type, error,
            )
            review_output = await self.review_agent.run(review_state)
            review = review_output.get("review_result", {})
            if review.get("changed", False):
                final_code = review.get("optimized_code", code)
            else:
                final_code = code

        return VisualizeResult(
            should_visualize=True,
            render_type=render_type,
            code=final_code,
            title=code_result.get("title", "图表"),
            reasoning=analysis.get("reasoning", ""),
            warning=warning,
        )