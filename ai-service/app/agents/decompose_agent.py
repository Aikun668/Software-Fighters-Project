import json
import logging
import os
from typing import Any, TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)


class DecomposeState(TypedDict, total=False):
    topic: str
    context: str
    student_profile: dict
    macro_topics: list[dict]
    micro_skills: list[dict]
    prerequisites: list[dict]
    summary: str
    response: str


class DecomposeAgent(BaseAgent):
    """知识分解 Agent — 将学习主题拆分为宏观主题、微观技能与前置知识。"""

    def __init__(self, config=None, use_mock_llm: bool = False, model_profile=None):
        super().__init__(
            agent_name="decompose_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
            model_profile=model_profile,
        )
        self._skeleton = self._load_skeleton()

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(DecomposeState)
        graph.add_node("decompose", self._decompose_node)
        graph.set_entry_point("decompose")
        graph.set_finish_point("decompose")
        return graph.compile()

    async def _decompose_node(self, state: DecomposeState) -> dict:
        topic = state.get("topic", "")
        context = state.get("context", "")
        student_profile = state.get("student_profile", {})

        sys_prompt = self._load_prompt()
        user_tpl = self._load_extra_prompt("system.yaml", key="user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {
                "topic": topic,
                "context": context or "（无额外上下文）",
                "student_profile": self._format_profile(student_profile),
            },
        )

        result = await self._call_llm_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            expected_key="macro_topics",
            fallback={},
            validator=self._validate_decomposition,
            max_retries=1,
        )

        if not result or "macro_topics" not in result:
            result = self._skeleton_fallback(topic)

        macro_topics = result.get("macro_topics", [])
        micro_skills = result.get("micro_skills", [])
        prerequisites = result.get("prerequisites", [])
        summary = result.get("summary", f"已将「{topic}」拆解为 {len(macro_topics)} 个宏观主题与 {len(micro_skills)} 个微观技能。")

        logger.info(f"DecomposeAgent: topic='{topic}' macros={len(macro_topics)} micros={len(micro_skills)} preqs={len(prerequisites)}")

        return {
            "macro_topics": macro_topics,
            "micro_skills": micro_skills,
            "prerequisites": prerequisites,
            "summary": summary,
            "response": summary,
        }

    @staticmethod
    def _validate_decomposition(result: dict) -> list[str]:
        issues = []
        macro_topics = result.get("macro_topics")
        if not isinstance(macro_topics, list) or len(macro_topics) == 0:
            issues.append("macro_topics 必须是非空数组")
        else:
            for i, t in enumerate(macro_topics):
                if not isinstance(t.get("name"), str) or not t["name"]:
                    issues.append(f"macro_topics[{i}] 缺少 name")
        micro_skills = result.get("micro_skills", [])
        if not isinstance(micro_skills, list):
            issues.append("micro_skills 必须是数组")
        return issues

    def _load_skeleton(self) -> dict:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base_dir, "..", "..", "data", "knowledge_graph_skeleton.json")
        path = os.path.normpath(path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception as e:
            logger.warning(f"Failed to load knowledge graph skeleton: {e}")
            return {"nodes": [], "edges": []}

    def _skeleton_fallback(self, topic: str) -> dict:
        nodes = self._skeleton.get("nodes", [])
        edges = self._skeleton.get("edges", [])

        topic_lower = topic.lower()
        matched = [n for n in nodes if topic_lower in n.get("name", "").lower() or topic_lower in n.get("description", "").lower()]

        if not matched and nodes:
            matched = [nodes[0]]

        macro_topics = [
            {
                "name": n.get("name", topic),
                "bloom_level": "understand",
                "description": n.get("description", ""),
            }
            for n in matched[:5]
        ]

        micro_skills = []
        for n in matched[:3]:
            micro_skills.append({
                "name": f"{n.get('name')} 基础概念",
                "bloom_level": "remember",
                "parent": n.get("name"),
                "description": f"掌握 {n.get('name')} 的核心术语与定义",
            })
            micro_skills.append({
                "name": f"{n.get('name')} 应用方法",
                "bloom_level": "apply",
                "parent": n.get("name"),
                "description": f"能够使用 {n.get('name')} 解决简单问题",
            })

        prerequisites = []
        node_ids = {n.get("id") for n in matched}
        for edge in edges:
            if edge.get("target") in node_ids and edge.get("relation") == "depends_on":
                source = next((n for n in nodes if n.get("id") == edge.get("source")), None)
                if source:
                    prerequisites.append({
                        "name": source.get("name"),
                        "bloom_level": "remember",
                        "relation": "required",
                        "description": source.get("description", ""),
                    })

        return {
            "macro_topics": macro_topics,
            "micro_skills": micro_skills[:8],
            "prerequisites": prerequisites[:4],
            "summary": f"基于课程知识骨架，将「{topic}」拆解为 {len(macro_topics)} 个宏观主题。",
        }
