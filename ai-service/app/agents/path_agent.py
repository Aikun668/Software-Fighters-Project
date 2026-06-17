import json
import logging
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.services.hallucination_guard import kb_verify
from app.services.llm_service import create_llm
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)


def _loose_topic_match(title: str, topic_keywords: set[str]) -> bool:
    """检查章节标题是否与 topic 有至少一个字的交集。
    用途：过滤 LLM 输出的明显无关章节（如用户要学数学，LLM 混入英语语法章）。"""
    return bool(topic_keywords & set(title))


class PathState(TypedDict, total=False):
    student_id: str
    student_profile: dict
    topic: str
    concept_graph: dict
    steps: list[dict]
    critique: str
    version: int
    response: str


@kb_verify(fields=["response"])
class PathAgent(BaseAgent):
    """学习路径规划 Agent —— 基于画像设计个性化学习路径"""

    def __init__(self, config=None, use_mock_llm: bool = False):
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
        topic = state.get("topic", "")

        system_prompt = self._load_extra_prompt("path_planner.yaml", key="system")
        user_tpl = self._load_extra_prompt("path_planner.yaml", key="user_template")
        profile_text = json.dumps(student_profile, ensure_ascii=False) if student_profile else "（暂无画像）"
        system_prompt = interpolate_variables(
            system_prompt, {"topic": topic or "未指定"}
        )
        user_prompt = interpolate_variables(
            user_tpl,
            {"student_profile": profile_text, "topic": topic or "（用户未指定主题，请基于画像推断）"},
        )

        result = await self._call_llm_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            expected_key="chapters",
            fallback={},
        )

        chapters = result.get("chapters", [])
        if not chapters:
            chapters = self._fallback_chapters(student_profile, topic)

        # 后处理：过滤与 topic 明显无关的章节（如用户要学数学，profile 有英语弱点时 LLM 可能混入英语章）
        if topic and chapters:
            topic_keywords = set(topic)
            filtered = [ch for ch in chapters if _loose_topic_match(ch.get("title", ""), topic_keywords)]
            if len(filtered) >= 2:
                chapters = filtered

        steps = [
            {"order": i + 1, "topic": ch["title"], "status": "pending", "resource_id": None}
            for i, ch in enumerate(chapters)
        ]

        concept_graph = self._build_concept_graph(chapters, topic=state.get("topic", ""))

        return {
            "concept_graph": concept_graph,
            "steps": steps,
            "version": 1,
        }

    def _fallback_chapters(self, profile: dict, topic: str = "") -> list[dict]:
        knowledge_base = profile.get("knowledge_base", 0)
        subject = topic or "基础知识"
        if knowledge_base < 30:
            return [
                {"title": f"{subject}基础概念", "learning_objectives": [f"掌握{subject}的基本概念"], "content_type": "concept", "prerequisites": [], "summary": f"{subject}入门基础"},
                {"title": f"{subject}核心原理", "learning_objectives": [f"理解{subject}的核心原理"], "content_type": "theory", "prerequisites": [f"{subject}基础概念"], "summary": f"{subject}核心理论"},
                {"title": f"{subject}实践应用", "learning_objectives": [f"能独立完成{subject}相关练习"], "content_type": "practice", "prerequisites": [f"{subject}核心原理"], "summary": f"{subject}动手实践"},
            ]
        elif knowledge_base < 60:
            return [
                {"title": f"{subject}进阶理论", "learning_objectives": [f"深入理解{subject}进阶概念"], "content_type": "theory", "prerequisites": [], "summary": f"{subject}进阶"},
                {"title": f"{subject}综合应用", "learning_objectives": [f"综合运用{subject}知识"], "content_type": "practice", "prerequisites": [f"{subject}进阶理论"], "summary": f"{subject}综合"},
                {"title": f"{subject}前沿探索", "learning_objectives": [f"了解{subject}最新发展"], "content_type": "concept", "prerequisites": [f"{subject}综合应用"], "summary": f"{subject}前沿"},
            ]
        return [
            {"title": f"{subject}专项突破", "learning_objectives": [f"攻克{subject}难点"], "content_type": "theory", "prerequisites": [], "summary": f"{subject}专项"},
            {"title": f"{subject}项目实战", "learning_objectives": [f"完成{subject}综合项目"], "content_type": "practice", "prerequisites": [f"{subject}专项突破"], "summary": f"{subject}实战"},
            {"title": f"{subject}体系构建", "learning_objectives": [f"构建{subject}知识体系"], "content_type": "practice", "prerequisites": [f"{subject}项目实战"], "summary": f"{subject}体系"},
        ]

    def _build_concept_graph(self, chapters: list[dict], topic: str = "") -> dict:
        """按主题裁剪知识图谱子图，不再返回全量骨架。"""
        from app.services.graph_service import get_graph_service

        gs = get_graph_service()
        if topic:
            return gs.get_subgraph_for_topic(topic)
        return {"nodes": gs.load_skeleton()["nodes"], "edges": gs.load_skeleton()["edges"]}

    async def _revise_node(self, state: PathState) -> dict:
        """Revise: LLM 自我审查 + 修正 drafted 路径"""
        steps = state.get("steps", [])
        student_profile = state.get("student_profile", {})
        concept_graph = state.get("concept_graph", {})
        topic = state.get("topic", "")

        # 构建自查 prompt
        steps_text = json.dumps(steps, ensure_ascii=False)
        profile_text = json.dumps(student_profile, ensure_ascii=False) if student_profile else "（暂无画像）"

        revise_system = (
            f"你是学习路径审核专家。当前学习主题：{topic}。"
            "请审查以下学习路径，检查覆盖度、顺序合理性、与学生画像的匹配度。"
            f"注意：所有章节必须围绕「{topic}」，不要添加其他学科的章节。"
            "如有问题请修正，输出 JSON："
            '{"revised_steps": [{"order": 1, "topic": "...", "status": "pending", "resource_id": null, "rationale": "..."}]}'
        )
        revise_user = f"学习主题：{topic}\n学生画像：{profile_text}\n\n当前路径：{steps_text}\n\n请审查并输出修正后的路径 JSON。"

        result = await self._call_llm_json(
            system_prompt=revise_system,
            user_prompt=revise_user,
            expected_key="revised_steps",
            fallback={},
        )

        if result and result.get("revised_steps"):
            steps = result["revised_steps"]
            # 再次过滤：revise 可能重新引入与 topic 无关的章节
            if topic:
                topic_keywords = set(topic)
                filtered = [s for s in steps if _loose_topic_match(s.get("topic", ""), topic_keywords)]
                if len(filtered) >= 2:
                    steps = filtered
        else:
            # fallback: 原有兴趣方向匹配逻辑
            interest = student_profile.get("interest_direction", [])
            if interest:
                steps = [
                    {**step, "status": "recommended" if any(i in step.get("topic", "") for i in interest) else step.get("status", "pending")}
                    for step in steps
                ]

        response = f"已为您规划 {len(steps)} 步学习路径。"
        return {"steps": steps, "response": response, "version": 2}
