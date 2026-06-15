import logging
from typing import Any, TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)


class ImageState(TypedDict, total=False):
    topic: str
    summary: str
    student_profile: dict
    prompt: str
    caption: str
    style: str
    alt_text: str
    response: str


class ImageAgent(BaseAgent):
    def __init__(self, config=None, use_mock_llm: bool = False, model_profile=None):
        super().__init__(
            agent_name="image_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
            model_profile=model_profile,
        )

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(ImageState)
        graph.add_node("generate", self._generate_node)
        graph.set_entry_point("generate")
        graph.set_finish_point("generate")
        return graph.compile()

    async def _generate_node(self, state: ImageState) -> dict:
        topic = state.get("topic", "")
        summary = state.get("summary", "")
        student_profile = state.get("student_profile", {})

        sys_prompt = self._load_prompt()
        user_tpl = self._load_extra_prompt("system.yaml", key="user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {
                "topic": topic,
                "summary": summary or "（暂无摘要）",
                "student_profile": self._format_profile(student_profile),
            },
        )

        result = await self._call_llm_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            expected_key="prompt",
            fallback={},
            validator=self._validate_image,
            max_retries=1,
        )

        if not result or "prompt" not in result:
            result = self._fallback_image(topic)

        return {
            "prompt": result.get("prompt", ""),
            "caption": result.get("caption", f"{topic}配图"),
            "style": result.get("style", "diagram"),
            "alt_text": result.get("alt_text", f"{topic}示意图"),
            "response": result.get("response", f"已为「{topic}」生成配图提示词。"),
        }

    @staticmethod
    def _validate_image(result: dict) -> list[str]:
        issues = []
        if not isinstance(result.get("prompt"), str) or not result["prompt"]:
            issues.append("缺少有效的 prompt 字段")
        if result.get("style") not in ("diagram", "illustration", "mindmap", "comparison"):
            issues.append("style 必须是 diagram/illustration/mindmap/comparison 之一")
        return issues

    @staticmethod
    def _fallback_image(topic: str) -> dict:
        return {
            "prompt": f"Educational diagram explaining {topic}, clean minimalist style, soft blue background, labeled components, no text-heavy, flat illustration",
            "caption": f"{topic}核心概念示意图",
            "style": "diagram",
            "alt_text": f"展示{topic}关键要素的教育示意图",
            "response": f"已为「{topic}」生成配图提示词。",
        }
