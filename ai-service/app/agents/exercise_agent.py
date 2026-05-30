import json
import logging
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.services.llm_service import create_llm
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)


class ExerciseState(TypedDict, total=False):
    topic: str
    count: int
    difficulty: str
    student_profile: dict
    plan: list[dict]
    questions: list[dict]
    stage: str
    response: str


class ExerciseAgent(BaseAgent):
    """练习题生成 Agent —— 基于薄弱点生成个性化题目"""

    def __init__(self, config=None, use_mock_llm: bool = True):
        super().__init__(
            agent_name="exercise_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
        )
        self.use_mock_llm = use_mock_llm
        self.plan_llm = create_llm(temperature=0.3, use_mock=use_mock_llm)

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(ExerciseState)
        graph.add_node("plan", self._plan_node)
        graph.add_node("generate", self._generate_node)
        graph.add_node("review", self._review_node)
        graph.set_entry_point("plan")
        graph.add_edge("plan", "generate")
        graph.add_edge("generate", "review")
        graph.set_finish_point("review")
        return graph.compile()

    async def _plan_node(self, state: ExerciseState) -> dict:
        """规划题目蓝图"""
        topic = state.get("topic", "")
        count = state.get("count", 3)
        difficulty = state.get("difficulty", "medium")
        student_profile = state.get("student_profile", {})
        weak_points = student_profile.get("weak_points", [])

        plan_system = self._load_extra_prompt("pipeline.yaml", key="plan_system")
        plan_user_tpl = self._load_extra_prompt("pipeline.yaml", key="plan_user")
        user_prompt = interpolate_variables(
            plan_user_tpl,
            {
                "topic": topic,
                "count": str(count),
                "difficulty": difficulty,
                "weak_points": ", ".join(weak_points) if weak_points else "无",
            },
        )

        result = await self._call_llm_json(
            system_prompt=plan_system,
            user_prompt=user_prompt,
            expected_key="templates",
            fallback={"templates": []},
        )
        plan = result.get("templates", [])
        if not plan:
            plan = [
                {"question_id": f"q_{i+1}", "topic": topic, "question_type": "choice" if i % 2 == 0 else "short_answer", "difficulty": difficulty}
                for i in range(count)
            ]

        return {"plan": plan, "stage": "planned"}

    async def _generate_node(self, state: ExerciseState) -> dict:
        """生成题目（LLM 产出后经 validate→normalize 把关）"""
        from app.utils.quiz_validator import validate_question

        plan = state.get("plan", [])
        questions = []

        quiz_system = self._load_extra_prompt("pipeline.yaml", key="quiz_system")
        quiz_user_tpl = self._load_extra_prompt("pipeline.yaml", key="quiz_user")

        for template in plan:
            q_type = template.get("question_type", "choice")
            topic = template.get("topic", "")
            difficulty = template.get("difficulty", "medium")
            q_id = template.get("question_id", "q_1")

            user_prompt = interpolate_variables(
                quiz_user_tpl,
                {
                    "question_id": q_id,
                    "topic": topic,
                    "question_type": q_type,
                    "difficulty": difficulty,
                },
            )

            result = await self._call_llm_json(
                system_prompt=quiz_system,
                user_prompt=user_prompt,
                expected_key="question",
                fallback={},
            )

            if result:
                normalized, issues = validate_question(result)
                if issues:
                    logger.warning(f"Question {q_id} has {len(issues)} issue(s): {issues}")
                questions.append(normalized)
            else:
                questions.append(self._mock_question(q_type, topic))

        return {"questions": questions, "stage": "generated"}

    def _mock_question(self, q_type: str, topic: str) -> dict:
        if q_type == "choice":
            return {
                "question_type": "choice",
                "question": f"关于{topic}，以下哪项描述是正确的？",
                "options": {
                    "A": f"{topic}的一种常见应用",
                    "B": f"与{topic}无关的概念",
                    "C": f"{topic}的历史背景",
                    "D": f"{topic}的数学推导",
                },
                "correct_answer": "A",
                "explanation": f"选项A正确描述了{topic}的典型应用。",
            }
        return {
            "question_type": "short_answer",
            "question": f"请简要解释{topic}的核心原理。",
            "options": None,
            "correct_answer": f"{topic}的核心原理是...（参考答案）",
            "explanation": f"{topic}的核心在于理解其基本原理和应用场景。",
        }

    async def _review_node(self, state: ExerciseState) -> dict:
        """Review：组装最终输出"""
        questions = state.get("questions", [])
        topic = state.get("topic", "")
        count = len(questions)

        response = f"已为您生成「{topic}」的 {count} 道练习题。"
        return {"response": response, "stage": "reviewed"}
