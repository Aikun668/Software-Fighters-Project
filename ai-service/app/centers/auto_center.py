import logging

from app.agents.diagnose_agent import DiagnoseAgent
from app.agents.profile_agent import DIMENSIONS, ProfileAgent
from app.agents.solve_agent import SolveAgent
from app.agents.tutor_agent import TutorAgent
from app.agents.visualize.visualize_pipeline import VisualizePipeline
from app.centers.schemas import CenterResult, CenterTask
from app.services.llm_service import PROFILE_CODE

logger = logging.getLogger(__name__)

# ── P1-1 Layer 1: 预过滤关键词，减少不必要的 LLM 调用 ──
_MUST_VISUALIZE_KW = [
    "步骤", "流程", "架构", "结构", "对比", "区别", "比较",
    "变化", "趋势", "关系", "层次", "示意图", "如图",
    "阶段", "管线", "流水线", "管道",
]
_SKIP_KW = ["定义", "概念", "是什么", "简称"]


def _prefilter_visualize(question: str, answer: str) -> bool:
    """快速预过滤：强信号直接放行，明显弱信号跳过，中间地带交给 LLM。"""
    combined = question + answer[:300]
    if any(kw in combined for kw in _MUST_VISUALIZE_KW):
        return True
    if any(kw in combined for kw in _SKIP_KW) and answer.count("。") < 3:
        return False
    return True


class AutoCenter:
    def __init__(
        self,
        tutor_agent: TutorAgent | None = None,
        solve_agent: SolveAgent | None = None,
        diagnose_agent: DiagnoseAgent | None = None,
        profile_agent: ProfileAgent | None = None,
        visualize_pipeline: VisualizePipeline | None = None,
    ):
        self.tutor_agent = tutor_agent
        self.solve_agent = solve_agent
        self.diagnose_agent = diagnose_agent
        self.profile_agent = profile_agent
        self.visualize_pipeline = visualize_pipeline

    async def execute(self, task: CenterTask) -> CenterResult:
        intent = task.intent
        context = task.context or {}
        student_profile = context.get("student_profile", {})
        messages = context.get("messages", [])
        style = context.get("style", "standard")

        if intent == "solve_problem":
            return await self._run_solve(task, messages, student_profile)
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
            blocks = state.get("content_blocks", [])
            response = state.get("response", "")

            # ── 图解增强：Tutor 回答后判断是否需要补图 ──
            viz_blocks = await self._maybe_visualize(messages, response)
            if viz_blocks:
                blocks = list(blocks) + viz_blocks

            return CenterResult(
                mode="auto",
                intent=task.intent,
                event_type="content",
                payload={
                    "response": response,
                    "domain": state.get("domain", ""),
                    "blocks": blocks,
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

    async def _maybe_visualize(
        self,
        messages: list[dict],
        answer: str,
    ) -> list[dict]:
        """Tutor 回答完成后，检查是否适合生成图解。"""
        if not answer.strip():
            return []

        question = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                question = m.get("content", "")
                break
        if not question.strip():
            return []

        if not _prefilter_visualize(question, answer):
            return []

        try:
            pipeline = self.visualize_pipeline or VisualizePipeline()
            result = await pipeline.run(question=question, answer=answer[:3000])
        except Exception as e:
            logger.warning(f"VisualizePipeline failed (non-blocking): {e}")
            return []

        if not result.should_visualize or not result.code:
            return []

        logger.info(
            "Tutor 图解增强: type=%s, title=%s, code_len=%d",
            result.render_type, result.title, len(result.code),
        )
        return [{
            "type": "visualization",
            "sub_type": result.render_type,
            "heading": result.title,
            "content": result.code,
        }]

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

            current_profile = state.get("current_profile", {})
            response = state.get("response", "")
            profile_changed = state.get("profile_changed", False)
            profile_complete = False
            filled_dims = 0

            # ── 完备度检测（与 ProfileWorkflow.director 逻辑一致）──
            filled_dims = sum(
                1 for k, v in current_profile.items()
                if v is not None and v != [] and v != {} and k in DIMENSIONS
            )
            if filled_dims >= 4:
                profile_complete = True
                summary = (
                    f"太棒了！我已经对你的学习情况有了比较全面的了解"
                    f"（已收集 {filled_dims}/{len(DIMENSIONS)} 个维度）。"
                    f"接下来我可以为你：\n"
                    f"1. 生成个性化的学习资源\n"
                    f"2. 规划适合你的学习路径\n"
                    f"3. 推荐针对性的练习题\n"
                    f"你想从哪里开始？"
                )
                response = f"{response}\n\n{summary}" if response else summary

            return CenterResult(
                mode="auto",
                intent=task.intent,
                event_type="content",
                payload={
                    "response": response,
                    "current_profile": current_profile,
                    "profile_changed": profile_changed,
                    "profile_complete": profile_complete,
                    "filled_dimensions": filled_dims,
                },
                agent="ProfileAgent",
                sequence=task.sequence,
                profile_delta=current_profile,
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
        agent = self.solve_agent or SolveAgent(model_profile=PROFILE_CODE)
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

