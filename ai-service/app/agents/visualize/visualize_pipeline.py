from dataclasses import dataclass
from typing import Optional

from app.agents.visualize.analysis_agent import AnalysisAgent
from app.agents.visualize.code_generator_agent import CodeGeneratorAgent
from app.agents.visualize.review_agent import ReviewAgent
from app.services.llm_service import PROFILE_ANALYSIS, PROFILE_CODE, PROFILE_REVIEW


@dataclass
class VisualizeResult:
    should_visualize: bool = False
    render_type: str = ""
    code: str = ""
    title: str = ""
    reasoning: str = ""

    @staticmethod
    def skip(reason: str = "") -> "VisualizeResult":
        return VisualizeResult(should_visualize=False, reasoning=reason)


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
        if confidence < 0.6:
            return VisualizeResult.skip(
                reason=f"置信度过低 ({confidence:.2f})，跳过可视化"
            )

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
        )