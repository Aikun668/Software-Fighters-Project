import asyncio
import json
import logging
from typing import AsyncIterator, Iterator

from app.agents.exercise_agent import ExerciseAgent
from app.centers.schemas import CenterResult, CenterTask
from app.events.types import (
    StreamEvent,
    confidence_event,
    error_content_event,
    flat_done_event,
    progress_content_event,
    steps_event,
    token_event,
)
from app.services.evaluation_service import (
    generate_report,
    grade_choice,
    grade_code,
    grade_short_answer,
)
from app.services.exercise_analytics_service import (
    analyze_session as analyze_session_service,
)
from app.services.exercise_analytics_service import (
    get_dashboard as get_dashboard_service,
)
from app.services.exercise_categorization_service import categorize_exercises
from app.services.exercise_profile_service import enrich_profile as enrich_profile_service
from app.services.llm_service import PROFILE_EXERCISE
from app.utils.json_parser import parse_llm_json
from app.utils.prompt_guard import sanitize_for_llm
from app.utils.prompt_loader import interpolate_variables, load_prompt_file

logger = logging.getLogger(__name__)

GENERATE_FAILED_MESSAGE = "题目生成失败，请稍后重试"
SOLVE_FAILED_MESSAGE = "解题功能暂时不可用，请稍后重试"


def _chunks(text: str, size: int) -> Iterator[str]:
    """按固定字数切分文本，与 API 现状的 _sse_stream_chunks 同规则。"""
    for i in range(0, len(text), size):
        yield text[i:i + size]


class ExerciseCenter:
    def __init__(
        self,
        exercise_agent: ExerciseAgent | None = None,
        solve_agent=None,
        llm_service=None,
        use_mock_llm: bool = False,
    ):
        self.exercise_agent = exercise_agent
        self.solve_agent = solve_agent
        self.llm_service = llm_service
        # P0-B：惰性构造的 Agent 继承本旗标；`_llm()` 走 get_llm_service()，
        # 后者已由统一环境开关接管（app/services/llm_service.py::_env_mock_flag）。
        self.use_mock_llm = use_mock_llm
        # 节流节奏：API 现状 0.3s / 0.5s / 0.03s / 4 字，离线测试注入 0
        self.plan_progress_delay = 0.3
        self.generate_progress_delay = 0.5
        self.token_delay = 0.03
        self.chunk_size = 4

    def _exercise_agent(self) -> ExerciseAgent:
        if self.exercise_agent is None:
            self.exercise_agent = ExerciseAgent(
                model_profile=PROFILE_EXERCISE, use_mock_llm=self.use_mock_llm
            )
        return self.exercise_agent

    def _solve_agent_instance(self):
        if self.solve_agent is None:
            from app.agents.solve_agent import SolveAgent
            self.solve_agent = SolveAgent(use_mock_llm=self.use_mock_llm)
        return self.solve_agent

    def _llm(self):
        if self.llm_service is None:
            from app.services.llm_service import get_llm_service
            self.llm_service = get_llm_service()
        return self.llm_service

    async def execute(self, task: CenterTask, on_token=None) -> CenterResult:
        context = task.context or {}
        student_profile = context.get("student_profile", {})
        topic = task.params.get("topic") or task.input
        count = task.params.get("count", 3)
        difficulty = task.params.get("difficulty", "medium")

        agent = self._exercise_agent()
        try:
            run_state: dict = {
                "topic": topic,
                "count": count,
                "difficulty": difficulty,
                "student_profile": student_profile,
                "purpose": task.params.get("purpose", ""),
            }
            # 流式：把 on_token 透传给 agent.run → 节点内经 current_on_token 下发
            # 题面/答案片段（None 时维持原非流式路径）
            if on_token is not None:
                run_state["_on_token"] = on_token
            state = await agent.run(run_state)
            return CenterResult(
                mode="exercise",
                intent=task.intent,
                event_type="exercise",
                payload={
                    "type": "exercise",
                    "topic": topic,
                    "count": len(state.get("questions", [])),
                    "questions": state.get("questions", []),
                    "response": state.get("response", ""),
                },
                agent="ExerciseAgent",
                sequence=task.sequence,
            )
        except Exception as e:
            logger.error(f"ExerciseCenter failed: {e}")
            return CenterResult(
                mode="exercise",
                intent=task.intent,
                event_type="error",
                error="练习生成失败",
                agent="ExerciseAgent",
                sequence=task.sequence,
            )

    async def generate_stream(
        self,
        *,
        topic: str,
        knowledge_node_id: str | None,
        strategy: str,
        count: int,
        difficulty: str,
        student_profile: dict,
    ) -> AsyncIterator[StreamEvent]:
        """出题流：progress(plan) → ExerciseAgent.run → progress(generate) → done(questions)。

        失败路径与现状一致：progress(plan) 已发出，随后 error + done。
        """
        display_topic = knowledge_node_id or topic
        try:
            await asyncio.sleep(self.plan_progress_delay)
            yield progress_content_event("plan", f"正在规划「{display_topic}」的练习题...")

            state = await self._exercise_agent().run({
                "topic": topic,
                "knowledge_node_id": knowledge_node_id,
                "strategy": strategy,
                "count": count,
                "difficulty": difficulty,
                "student_profile": student_profile,
            })

            await asyncio.sleep(self.generate_progress_delay)
            num_q = len(state.get("questions", []))
            yield progress_content_event("generate", f"已生成 {num_q} 道题目")

            yield flat_done_event({"questions": state.get("questions", [])})
        except Exception as e:
            logger.error(f"Exercise generate stream failed: {e}")
            yield error_content_event(GENERATE_FAILED_MESSAGE)
            yield flat_done_event()

    async def solve_stream(self, *, question: str, context: str) -> AsyncIterator[StreamEvent]:
        """解题流：SolveAgent.run → steps → token* → confidence → done。

        失败路径与现状一致：无前置事件，只有 error + done。
        """
        try:
            state = await self._solve_agent_instance().run({
                "question": question,
                "context": context,
            })

            steps = state.get("steps", [])
            if steps:
                yield steps_event(steps)

            solution = state.get("solution", "")
            if solution:
                for chunk in _chunks(solution, self.chunk_size):
                    await asyncio.sleep(self.token_delay)
                    yield token_event(chunk)

            confidence = state.get("confidence_score")
            if confidence is not None:
                yield confidence_event(confidence)

            yield flat_done_event()
        except Exception as e:
            logger.error(f"Solve stream failed: {e}")
            yield error_content_event(SOLVE_FAILED_MESSAGE)
            yield flat_done_event()

    async def analyze_errors(self, *, errors: list[dict], level: str) -> dict:
        """错因分析：prompt 加载 → sanitize → 插值 → LLM → 解析 JSON。

        异常向上传播，由 API 层映射 500（与收口前一致）。
        """
        sys_prompt = load_prompt_file("tutor_agent", "error_analysis.yaml", key="system")
        user_tpl = load_prompt_file("tutor_agent", "error_analysis.yaml", key="user_template")
        sanitized_errors = [
            {k: sanitize_for_llm(v) if isinstance(v, str) else v for k, v in e.items()}
            for e in errors
        ]
        user_prompt = interpolate_variables(
            user_tpl,
            {"errors": json.dumps(sanitized_errors, ensure_ascii=False), "level": str(level)},
        )

        raw = await self._llm().chat(
            [{"role": "user", "content": user_prompt}],
            system_prompt=sys_prompt,
        )
        return parse_llm_json(raw, fallback={})

    async def grade(
        self,
        *,
        question_type: str,
        user_answer: str | None = None,
        correct_answer: str | None = None,
        choices: list | None = None,
        multi: bool = False,
        points: int = 1,
        reference_answer: str = "",
        rubric: str = "",
    ) -> dict:
        """批改：按题型转调 evaluation_service 的对应规则。"""
        if question_type == "choice":
            return grade_choice(
                user_answer, correct_answer, choices, multi=multi, points=points,
            )
        if question_type == "code":
            return await grade_code(user_answer, reference_answer, rubric)
        return await grade_short_answer(user_answer, reference_answer, rubric)

    async def evaluation_report(self, *, evaluation_results: dict) -> dict:
        """练习评估报告。"""
        return generate_report(evaluation_results)

    async def categorize(
        self, *, exercises: list[dict], knowledge_nodes: list[dict], course_id: str,
    ) -> dict:
        """练习题 → 知识图谱节点匹配。"""
        results = await categorize_exercises(exercises, knowledge_nodes, course_id)
        return {"results": results}

    async def analyze_session(
        self, *, records: list[dict], masteries: dict, course_id: str,
    ) -> dict:
        """单次练习会话分析。"""
        return analyze_session_service(records, masteries, course_id)

    async def dashboard(
        self,
        *,
        user_id: int,
        masteries: dict,
        recent_records: list[dict],
        course_id: str,
    ) -> dict:
        """练习仪表盘。"""
        return get_dashboard_service(user_id, masteries, recent_records, course_id)

    async def enrich_profile(
        self,
        *,
        user_id: int,
        student_profile: dict | None,
        recent_records: list[dict] | None,
        session_analysis: dict | None,
    ) -> dict:
        """练习数据反哺学生画像。"""
        return enrich_profile_service(
            user_id, student_profile, recent_records, session_analysis,
        )

    async def generate_consolidation(
        self, *, topic: str, knowledge_node_id: str | None, is_near_end: bool,
    ) -> dict:
        """完成学习步骤后的巩固题：review 策略、count 2/3、purpose=consolidation。"""
        state = await self._exercise_agent().run({
            "topic": topic,
            "knowledge_node_id": knowledge_node_id or None,
            "strategy": "review",
            "count": 3 if is_near_end else 2,
            "difficulty": "medium",
            "student_profile": {},
            "purpose": "consolidation",
        })
        return {"questions": state.get("questions", [])}

    async def generate_warmup(self, *, node_names: list[str]) -> dict:
        """回归检测热身题：每个节点 1 道 easy 题，逐节点降级（单节点失败不拖垮其余）。"""
        questions: list[dict] = []
        for node_name in node_names:
            try:
                state = await self._exercise_agent().run({
                    "topic": node_name,
                    "count": 1,
                    "difficulty": "easy",
                    "purpose": "warmup_not_exam",
                })
            except Exception as e:
                logger.warning(f"Failed to generate warmup question for '{node_name}': {e}")
                continue
            questions.extend(
                {**q, "review_node": node_name} for q in state.get("questions", [])
            )
        return {"questions": questions}
