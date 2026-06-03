from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.utils.prompt_loader import interpolate_variables


class ReviewState(TypedDict, total=False):
    render_type: str
    chart_type: str
    code: str
    description: str
    data_description: str
    review_result: dict
    response: str


class ReviewAgent(BaseAgent):
    def __init__(self, config=None, use_mock_llm: bool = True, model_profile=None):
        super().__init__(
            agent_name="visualize_review_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
            model_profile=model_profile,
        )

    def build_graph(self):
        graph = StateGraph(ReviewState)
        graph.add_node("review", self._review_node)
        graph.set_entry_point("review")
        graph.set_finish_point("review")
        return graph.compile()

    async def _review_node(self, state: ReviewState) -> dict:
        render_type = state.get("render_type", "")
        chart_type = state.get("chart_type", "")
        code = state.get("code", "")
        description = state.get("description", "")
        data_description = state.get("data_description", "")

        sys_prompt = self._load_extra_prompt("review.yaml", key="system")
        user_tpl = self._load_extra_prompt("review.yaml", key="user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {
                "render_type": render_type,
                "chart_type": chart_type,
                "code": code,
                "description": description,
                "data_description": data_description,
            },
        )

        result = await self._call_llm_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            expected_key="changed",
            fallback={"changed": False, "issues": [], "optimized_code": code, "suggestions": ""},
        )

        return {"review_result": result, "response": str(result.get("suggestions", ""))}