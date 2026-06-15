import logging

from app.agents.decompose_agent import DecomposeAgent
from app.agents.diagnose_agent import DiagnoseAgent
from app.agents.image_agent import ImageAgent
from app.agents.layered_explain_agent import LayeredExplainAgent
from app.agents.profile_agent import ProfileAgent
from app.agents.solve_agent import SolveAgent
from app.agents.tutor_agent import TutorAgent
from app.centers.schemas import CenterResult, CenterTask

logger = logging.getLogger(__name__)


class AutoCenter:
    def __init__(
        self,
        tutor_agent: TutorAgent | None = None,
        solve_agent: SolveAgent | None = None,
        decompose_agent: DecomposeAgent | None = None,
        layered_explain_agent: LayeredExplainAgent | None = None,
        diagnose_agent: DiagnoseAgent | None = None,
        image_agent: ImageAgent | None = None,
        profile_agent: ProfileAgent | None = None,
    ):
        self.tutor_agent = tutor_agent
        self.solve_agent = solve_agent
        self.decompose_agent = decompose_agent
        self.layered_explain_agent = layered_explain_agent
        self.diagnose_agent = diagnose_agent
        self.image_agent = image_agent
        self.profile_agent = profile_agent

    async def execute(self, task: CenterTask) -> CenterResult:
        intent = task.intent
        context = task.context or {}
        student_profile = context.get("student_profile", {})
        messages = context.get("messages", [])
        style = context.get("style", "standard")

        if intent == "solve_problem":
            return await self._run_solve(task, messages, student_profile)
        if intent == "explain":
            return await self._run_explain(task, student_profile)
        if intent == "diagnose":
            return await self._run_diagnose(task, student_profile)
        if intent == "profile_building":
            return await self._run_profile_building(task, messages, student_profile)
        return await self._run_tutor(task, messages, student_profile, style)

    async def _run_tutor(
        self,
        task: CenterTask,
        messages: list[dict],
        student_profile: dict,
        style: str,
    ) -> CenterResult:
        agent = self.tutor_agent or TutorAgent()
        try:
            state = await agent.run({
                "messages": messages,
                "student_profile": student_profile,
                "style": style,
            })
            return CenterResult(
                mode="auto",
                intent=task.intent,
                event_type="content",
                payload={
                    "response": state.get("response", ""),
                    "domain": state.get("domain", ""),
                    "blocks": state.get("content_blocks", []),
                },
                agent="TutorAgent",
                sequence=task.sequence,
            )
        except Exception as e:
            logger.error(f"AutoCenter tutor failed: {e}")
            return CenterResult(
                mode="auto",
                intent=task.intent,
                event_type="error",
                error="答疑失败",
                agent="TutorAgent",
                sequence=task.sequence,
            )

    async def _run_explain(
        self,
        task: CenterTask,
        student_profile: dict,
    ) -> CenterResult:
        topic = task.params.get("topic") or task.input
        code_language = task.params.get("language", "python")

        if self._is_broad_topic(topic):
            return await self._run_decompose_then_explain(task, topic, student_profile, code_language)

        agent = self.layered_explain_agent or LayeredExplainAgent()
        try:
            state = await agent.run({
                "topic": topic,
                "context": task.input,
                "student_profile": student_profile,
                "code_language": code_language,
            })
            return CenterResult(
                mode="auto",
                intent=task.intent,
                event_type="content",
                payload={
                    "response": state.get("response", ""),
                    "intuition_layer": state.get("intuition_layer", {}),
                    "formal_layer": state.get("formal_layer", {}),
                    "code_layer": state.get("code_layer", {}),
                    "synthesis": state.get("synthesis", ""),
                    "blocks": self._build_explain_blocks(state),
                },
                agent="LayeredExplainAgent",
                sequence=task.sequence,
            )
        except Exception as e:
            logger.error(f"AutoCenter explain failed: {e}")
            return CenterResult(
                mode="auto",
                intent=task.intent,
                event_type="error",
                error="讲解失败",
                agent="LayeredExplainAgent",
                sequence=task.sequence,
            )

    async def _run_decompose_then_explain(
        self,
        task: CenterTask,
        topic: str,
        student_profile: dict,
        code_language: str,
    ) -> CenterResult:
        decompose = self.decompose_agent or DecomposeAgent()
        try:
            d_state = await decompose.run({
                "topic": topic,
                "context": task.input,
                "student_profile": student_profile,
            })
        except Exception as e:
            logger.error(f"AutoCenter decompose failed: {e}")
            return CenterResult(
                mode="auto",
                intent=task.intent,
                event_type="error",
                error="知识分解失败",
                agent="DecomposeAgent",
                sequence=task.sequence,
            )

        micro_skills = d_state.get("micro_skills", [])
        focus_skill = micro_skills[0].get("name", topic) if micro_skills else topic

        explain = self.layered_explain_agent or LayeredExplainAgent()
        try:
            e_state = await explain.run({
                "topic": focus_skill,
                "context": task.input,
                "student_profile": student_profile,
                "code_language": code_language,
            })
        except Exception as e:
            logger.error(f"AutoCenter layered explain failed: {e}")
            return CenterResult(
                mode="auto",
                intent=task.intent,
                event_type="content",
                payload={
                    "response": d_state.get("response", ""),
                    "macro_topics": d_state.get("macro_topics", []),
                    "micro_skills": micro_skills,
                    "prerequisites": d_state.get("prerequisites", []),
                },
                agent="DecomposeAgent",
                sequence=task.sequence,
            )

        return CenterResult(
            mode="auto",
            intent=task.intent,
            event_type="content",
            payload={
                "response": (
                    f"{d_state.get('summary', '')}\n\n"
                    f"下面以「{focus_skill}」为例，为你做三层讲解：\n\n"
                    f"{e_state.get('response', '')}"
                ),
                "macro_topics": d_state.get("macro_topics", []),
                "micro_skills": micro_skills,
                "prerequisites": d_state.get("prerequisites", []),
                "intuition_layer": e_state.get("intuition_layer", {}),
                "formal_layer": e_state.get("formal_layer", {}),
                "code_layer": e_state.get("code_layer", {}),
                "synthesis": e_state.get("synthesis", ""),
                "blocks": self._build_explain_blocks(e_state),
            },
            agent="DecomposeAgent+LayeredExplainAgent",
            sequence=task.sequence,
        )

    async def _run_diagnose(
        self,
        task: CenterTask,
        student_profile: dict,
    ) -> CenterResult:
        topic = task.params.get("topic") or task.input
        agent = self.diagnose_agent or DiagnoseAgent()
        try:
            state = await agent.run({
                "topic": topic,
                "skills": task.params.get("skills") or [topic],
                "prior_mastery": task.params.get("prior_mastery", {}),
                "attempts": task.params.get("attempts", []),
                "student_profile": student_profile,
            })
            return CenterResult(
                mode="auto",
                intent=task.intent,
                event_type="content",
                payload={
                    "response": state.get("response", ""),
                    "mastery_vector": state.get("mastery_vector", {}),
                    "report": state.get("report", {}),
                    "next_skill": state.get("next_skill", ""),
                    "confidence": state.get("confidence", 0),
                },
                agent="DiagnoseAgent",
                sequence=task.sequence,
                profile_delta={"mastery_vector": state.get("mastery_vector", {})},
            )
        except Exception as e:
            logger.error(f"AutoCenter diagnose failed: {e}")
            return CenterResult(
                mode="auto",
                intent=task.intent,
                event_type="error",
                error="诊断失败",
                agent="DiagnoseAgent",
                sequence=task.sequence,
            )

    async def _run_profile_building(
        self,
        task: CenterTask,
        messages: list[dict],
        student_profile: dict,
    ) -> CenterResult:
        agent = self.profile_agent or ProfileAgent()
        try:
            state = await agent.run({
                "messages": messages or [{"role": "user", "content": task.input}],
                "current_profile": student_profile,
                "user_id": task.context.get("user_id", 1) if task.context else 1,
            })
            return CenterResult(
                mode="auto",
                intent=task.intent,
                event_type="content",
                payload={
                    "response": state.get("response", ""),
                    "current_profile": state.get("current_profile", {}),
                    "profile_changed": state.get("profile_changed", False),
                },
                agent="ProfileAgent",
                sequence=task.sequence,
                profile_delta=state.get("current_profile", {}),
            )
        except Exception as e:
            logger.error(f"AutoCenter profile building failed: {e}")
            return CenterResult(
                mode="auto",
                intent=task.intent,
                event_type="error",
                error="画像构建失败",
                agent="ProfileAgent",
                sequence=task.sequence,
            )

    async def _run_solve(
        self,
        task: CenterTask,
        messages: list[dict],
        student_profile: dict,
    ) -> CenterResult:
        agent = self.solve_agent or SolveAgent()
        context_parts = []
        for m in messages[-6:]:
            role_label = "学生" if m.get("role") == "user" else "AI"
            context_parts.append(f"[{role_label}]: {m.get('content', '')[:200]}")
        context = "\n".join(context_parts)

        try:
            state = await agent.run({
                "question": task.input,
                "context": context,
                "student_profile": student_profile,
            })
            return CenterResult(
                mode="auto",
                intent=task.intent,
                event_type="content",
                payload={
                    "steps": state.get("steps", []),
                    "solution": state.get("solution", ""),
                    "confidence": state.get("confidence_score"),
                },
                agent="SolveAgent",
                sequence=task.sequence,
            )
        except Exception as e:
            logger.error(f"AutoCenter solve failed: {e}")
            return CenterResult(
                mode="auto",
                intent=task.intent,
                event_type="error",
                error="解题失败",
                agent="SolveAgent",
                sequence=task.sequence,
            )

    @staticmethod
    def _is_broad_topic(topic: str) -> bool:
        broad_terms = {
            "概述", "基础", "导论", "入门", "是什么", "简介",
            "机器学习", "深度学习", "人工智能", "神经网络",
            "计算机视觉", "自然语言处理", "强化学习",
        }
        return any(term in topic for term in broad_terms) or len(topic) <= 8

    @staticmethod
    def _build_explain_blocks(state: dict) -> list[dict]:
        blocks = []
        intuition = state.get("intuition_layer", {})
        formal = state.get("formal_layer", {})
        code = state.get("code_layer", {})
        if intuition.get("analogy"):
            blocks.append({
                "type": "text",
                "heading": "直觉理解",
                "content": f"{intuition.get('analogy')}\n\n核心直觉：{intuition.get('key_idea', '')}",
            })
        if formal.get("definition"):
            blocks.append({
                "type": "text",
                "heading": "形式化定义",
                "content": f"{formal.get('definition')}\n\n{formal.get('formula', '')}".strip(),
            })
        if code.get("code"):
            language = code.get("language", "python")
            blocks.append({
                "type": "code",
                "heading": f"{language} 代码示例",
                "content": f"```{language}\n{code.get('code')}\n```\n\n{code.get('description', '')}".strip(),
            })
        return blocks
