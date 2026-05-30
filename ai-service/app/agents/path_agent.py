import json
import logging
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.services.llm_service import create_llm
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)


class PathState(TypedDict, total=False):
    student_id: str
    student_profile: dict
    concept_graph: dict
    steps: list[dict]
    critique: str
    version: int
    response: str


class PathAgent(BaseAgent):
    """学习路径规划 Agent —— 基于画像设计个性化学习路径"""

    def __init__(self, config=None, use_mock_llm: bool = True):
        super().__init__(
            agent_name="path_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
        )
        self.use_mock_llm = use_mock_llm
        self.path_llm = create_llm(temperature=0.3, use_mock=use_mock_llm)

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(PathState)
        graph.add_node("draft", self._draft_node)
        graph.add_node("revise", self._revise_node)
        graph.set_entry_point("draft")
        graph.add_edge("draft", "revise")
        graph.set_finish_point("revise")
        return graph.compile()

    async def _draft_node(self, state: PathState) -> dict:
        """Draft：调用 LLM 设计学习路径"""
        student_profile = state.get("student_profile", {})

        system_prompt = self._load_extra_prompt("path_planner.yaml", key="system")
        user_tpl = self._load_extra_prompt("path_planner.yaml", key="user_template")
        profile_text = json.dumps(student_profile, ensure_ascii=False) if student_profile else "（暂无画像）"
        user_prompt = interpolate_variables(user_tpl, {"student_profile": profile_text})

        result = await self._call_llm_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            expected_key="chapters",
            fallback={},
        )

        chapters = result.get("chapters", [])
        if not chapters:
            chapters = self._fallback_chapters(student_profile)

        steps = [
            {"order": i + 1, "topic": ch["title"], "status": "pending", "resource_id": None}
            for i, ch in enumerate(chapters)
        ]

        concept_graph = self._build_concept_graph(chapters)

        return {
            "concept_graph": concept_graph,
            "steps": steps,
            "version": 1,
        }

    def _fallback_chapters(self, profile: dict) -> list[dict]:
        knowledge_base = profile.get("knowledge_base", 0)
        if knowledge_base < 30:
            return [
                {"title": "Python 基础回顾", "learning_objectives": ["掌握 Python 语法"], "content_type": "theory", "prerequisites": [], "summary": "Python 基础"},
                {"title": "人工智能概述", "learning_objectives": ["了解 AI 发展"], "content_type": "concept", "prerequisites": ["Python 基础回顾"], "summary": "AI 概述"},
                {"title": "机器学习基础", "learning_objectives": ["理解 ML 概念"], "content_type": "theory", "prerequisites": ["人工智能概述"], "summary": "ML 基础"},
            ]
        elif knowledge_base < 60:
            return [
                {"title": "机器学习算法深入", "learning_objectives": ["掌握常见算法"], "content_type": "theory", "prerequisites": [], "summary": "ML 算法"},
                {"title": "神经网络基础", "learning_objectives": ["理解神经网络"], "content_type": "theory", "prerequisites": ["机器学习算法深入"], "summary": "神经网络"},
                {"title": "深度学习实践", "learning_objectives": ["动手实践 DL"], "content_type": "practice", "prerequisites": ["神经网络基础"], "summary": "DL 实践"},
            ]
        return [
            {"title": "Transformer 架构", "learning_objectives": ["理解 Attention"], "content_type": "theory", "prerequisites": [], "summary": "Transformer"},
            {"title": "大模型微调", "learning_objectives": ["掌握微调技术"], "content_type": "practice", "prerequisites": ["Transformer 架构"], "summary": "模型微调"},
            {"title": "多模态应用", "learning_objectives": ["了解多模态"], "content_type": "practice", "prerequisites": ["大模型微调"], "summary": "多模态"},
        ]

    def _build_concept_graph(self, chapters: list[dict]) -> dict:
        nodes = []
        edges = []
        for i, ch in enumerate(chapters):
            node_id = f"ch_{i}"
            nodes.append({
                "id": node_id,
                "label": ch["title"],
                "description": ch.get("summary", ""),
                "weight": round(0.3 + 0.6 * (i / max(len(chapters) - 1, 1)), 2),
            })
            for prereq in ch.get("prerequisites", []):
                for j, prev in enumerate(chapters):
                    if prev["title"] == prereq:
                        edges.append({
                            "src": f"ch_{j}",
                            "dst": node_id,
                            "relation": "depends_on",
                            "rationale": f"{ch['title']} 需要 {prereq} 基础",
                        })
        return {"nodes": nodes, "edges": edges}

    async def _revise_node(self, state: PathState) -> dict:
        """Revise: LLM 自我审查 + 修正 drafted 路径"""
        steps = state.get("steps", [])
        student_profile = state.get("student_profile", {})
        concept_graph = state.get("concept_graph", {})

        # 构建自查 prompt
        steps_text = json.dumps(steps, ensure_ascii=False)
        profile_text = json.dumps(student_profile, ensure_ascii=False) if student_profile else "（暂无画像）"

        revise_system = (
            "你是学习路径审核专家。请审查以下学习路径，检查覆盖度、顺序合理性、与学生画像的匹配度。"
            "如有问题请修正，输出 JSON："
            '{"revised_steps": [{"order": 1, "topic": "...", "status": "pending", "resource_id": null, "rationale": "..."}]}'
        )
        revise_user = f"学生画像：{profile_text}\n\n当前路径：{steps_text}\n\n请审查并输出修正后的路径 JSON。"

        result = await self._call_llm_json(
            system_prompt=revise_system,
            user_prompt=revise_user,
            expected_key="revised_steps",
            fallback={},
        )

        if result and result.get("revised_steps"):
            steps = result["revised_steps"]
        else:
            # fallback: 原有兴趣方向匹配逻辑
            interest = student_profile.get("interest_direction", [])
            if interest:
                steps = [
                    {**step, "status": "recommended" if any(i in step["topic"] for i in interest) else step.get("status", "pending")}
                    for step in steps
                ]

        response = f"已为您规划 {len(steps)} 步学习路径。"
        return {"steps": steps, "response": response, "version": 2}
