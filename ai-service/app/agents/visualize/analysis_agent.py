from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.utils.prompt_loader import interpolate_variables


class AnalysisState(TypedDict, total=False):
    question: str
    answer: str
    analysis: dict
    response: str


class AnalysisAgent(BaseAgent):
    def __init__(self, config=None, use_mock_llm: bool = True, model_profile=None):
        super().__init__(
            agent_name="visualize_analysis_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
            model_profile=model_profile,
        )

    def build_graph(self):
        graph = StateGraph(AnalysisState)
        graph.add_node("analyze", self._analyze_node)
        graph.set_entry_point("analyze")
        graph.set_finish_point("analyze")
        return graph.compile()

    async def _analyze_node(self, state: AnalysisState) -> dict:
        question = state.get("question", "")
        answer = state.get("answer", "")

        sys_prompt = self._load_extra_prompt("analysis.yaml", key="system")
        user_tpl = self._load_extra_prompt("analysis.yaml", key="user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {"question": question, "answer": answer},
        )

        result = await self._call_llm_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            expected_key="should_visualize",
            fallback={"should_visualize": False},
        )

        return {"analysis": result, "response": str(result.get("reasoning", ""))}