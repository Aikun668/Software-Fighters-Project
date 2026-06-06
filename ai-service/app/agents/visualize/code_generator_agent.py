from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.utils.prompt_loader import interpolate_variables


class CodeGenState(TypedDict, total=False):
    render_type: str
    chart_type: str
    description: str
    data_description: str
    visual_elements: list[str]
    question: str
    code_result: dict
    response: str


class CodeGeneratorAgent(BaseAgent):
    def __init__(self, config=None, use_mock_llm: bool = False, model_profile=None):
        super().__init__(
            agent_name="visualize_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
            model_profile=model_profile,
        )

    def build_graph(self):
        graph = StateGraph(CodeGenState)
        graph.add_node("generate", self._generate_node)
        graph.set_entry_point("generate")
        graph.set_finish_point("generate")
        return graph.compile()

    async def _generate_node(self, state: CodeGenState) -> dict:
        render_type = state.get("render_type", "mermaid")
        chart_type = state.get("chart_type", "")
        description = state.get("description", "")
        data_description = state.get("data_description", "")
        visual_elements = state.get("visual_elements", [])
        question = state.get("question", "")

        sys_prompt = self._load_extra_prompt("code_generator.yaml", key="system")
        user_tpl = self._load_extra_prompt("code_generator.yaml", key="user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {
                "render_type": render_type,
                "chart_type": chart_type,
                "description": description,
                "data_description": data_description,
                "visual_elements": ", ".join(visual_elements),
                "question": question,
            },
        )

        result = await self._call_llm_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            expected_key="code",
            fallback={"code": "", "title": "", "notes": ""},
        )

        return {"code_result": result, "response": result.get("notes", "")}