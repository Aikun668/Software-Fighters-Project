import json
import logging
import re
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent, current_on_token
from app.services.hallucination_guard import kb_verify
from app.services.llm_service import create_llm
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)


class ExerciseState(TypedDict, total=False):
    topic: str
    knowledge_node_id: str | None
    strategy: str | None
    count: int
    difficulty: str
    student_profile: dict
    purpose: str
    plan: list[dict]
    questions: list[dict]
    stage: str
    response: str


_OPTION_LINE_RE = re.compile(
    r"^\s*[（(]?([A-Ha-h])[)）.、．:：]\s*\S",
)


def _question_text_has_options(text: str, options: dict) -> bool:
    """题干里是否已经自带选项行。

    LLM 常在 `question` 文本里直接写出 ``A. xxx`` 形式的选项，
    而结构化的 ``options`` 字段又包含同一批选项。若两者都渲染，
    用户会看到**两遍选项**。此函数用于检测这种重复。
    """
    if not options:
        return False
    keys = {str(k).upper() for k in options}
    found = set()
    for line in text.splitlines():
        m = _OPTION_LINE_RE.match(line)
        if m:
            found.add(m.group(1).upper())
    # 多数选项已在题干出现即认为自带（避免个别 A. 编号误判）
    return len(found & keys) >= max(2, len(keys) - 1)


def format_question_markdown(index: int, question: dict) -> str:
    """单道题的题面 + 选项，格式化为 Markdown（流式下发用）。

    出题是**结构化产物**，逐字吐原始 JSON 会让用户看到乱码，
    故以「一道题」为流式粒度：每校验完一题即下发一题的题面。
    """
    lines = [f"**第 {index} 题**", ""]
    text = str(question.get("question") or question.get("content") or "").strip()
    options = question.get("options")
    if text:
        lines += [text, ""]
    # 题干已自带选项时不再重复罗列（否则选项出现两遍）
    if isinstance(options, dict) and not _question_text_has_options(text, options):
        for key, value in options.items():
            if value is None or value == "":
                continue
            lines.append(f"- **{key}.** {value}")
        lines.append("")
    return "\n".join(lines)


def format_answer_markdown(index: int, question: dict) -> str:
    """单道题的答案与解析，格式化为 Markdown（流式下发用）。"""
    lines = [f"**第 {index} 题**", ""]
    answer = question.get("correct_answer") or question.get("answer")
    if answer:
        lines += [f"**答案：** {answer}", ""]
    explanation = question.get("explanation")
    if explanation:
        lines += [str(explanation), ""]
    return "\n".join(lines)


async def _emit(on_token, text: str) -> None:
    """安全下发流式片段：回调异常不得影响题目生成主流程。"""
    if on_token is None or not text:
        return
    try:
        await on_token(text)
    except Exception:  # noqa: BLE001
        logger.warning("ExerciseAgent on_token raised (non-blocking)", exc_info=True)


@kb_verify(fields=["questions[*].question", "questions[*].answer"])
class ExerciseAgent(BaseAgent):
    """练习题生成 Agent —— 基于薄弱点生成个性化题目"""

    def __init__(self, config=None, use_mock_llm: bool = False,
                 model_profile=None):
        super().__init__(
            agent_name="exercise_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
            model_profile=model_profile,
        )
        self.use_mock_llm = use_mock_llm
        if not hasattr(self, "plan_llm"):
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
        knowledge_node_id = state.get("knowledge_node_id")
        strategy = state.get("strategy")
        count = state.get("count", 3)
        difficulty = state.get("difficulty", "medium")
        student_profile = state.get("student_profile", {})
        purpose = state.get("purpose", "")
        weak_points = student_profile.get("weak_points", [])

        # Derive topic from node_id if not explicitly given
        effective_topic = topic or (knowledge_node_id or "")

        strategy_hint = ""
        if strategy == "weakness":
            strategy_hint = "侧重用户薄弱的知识子概念，适当降低难度以建立信心。"
            difficulty = "easy"
        elif strategy == "review":
            strategy_hint = "生成与常见错题同类但不同问法的变体题，帮助巩固。"
        elif strategy == "new":
            strategy_hint = "生成全新题目，覆盖用户尚未接触的知识点或更高难度。"

        conditions = {"warmup": purpose == "warmup_not_exam"}
        # 走 _load_prompt（而非裸 build_prompt）：让平台安全人设挂在 **system 栏**。
        # 修 _load_extra_prompt 之前，这段人设是被错误地粘进 user 消息里的；
        # 纠正注入位置后必须在此显式补回，否则出题链路会完全失去平台身份约束。
        plan_system = self._load_prompt(
            "pipeline.yaml", conditions=conditions, key="plan_system"
        )
        plan_user_tpl = self._load_extra_prompt("pipeline.yaml", key="plan_user")
        user_prompt = interpolate_variables(
            plan_user_tpl,
            {
                "topic": effective_topic,
                "count": str(count),
                "difficulty": difficulty,
                "weak_points": ", ".join(weak_points) if weak_points else "无",
                "purpose": purpose,
                "strategy_hint": strategy_hint,
            },
        )

        result = await self._call_llm_json(
            system_prompt=plan_system,
            user_prompt=user_prompt,
            expected_key="templates",
            fallback={"templates": []},
            validator=self._validate_templates,
        )
        plan = result.get("templates", [])
        if not plan:
            types = ["choice", "short_answer", "code"]
            plan = [
                {"question_id": f"q_{i+1}", "topic": effective_topic, "question_type": types[i % 3], "difficulty": difficulty}
                for i in range(count)
            ]

        return {"plan": plan, "stage": "planned"}

    @staticmethod
    def _validate_question(result: dict) -> list[str]:
        """包装 quiz_validator，只返回 issues（适配 _call_llm_json validator 签名）"""
        from app.utils.quiz_validator import validate_question
        _, issues = validate_question(result)
        return issues

    @staticmethod
    def _validate_templates(result: dict) -> list[str]:
        """验证模板数组的结构完整性"""
        issues = []
        templates = result.get("templates", [])
        if not isinstance(templates, list) or len(templates) == 0:
            issues.append("templates 必须是非空数组")
            return issues
        for i, t in enumerate(templates):
            if not isinstance(t.get("question_id"), str) or not t["question_id"]:
                issues.append(f"templates[{i}] 缺少或 question_id 为空")
            if not isinstance(t.get("topic"), str) or not t["topic"]:
                issues.append(f"templates[{i}] 缺少或 topic 为空")
        return issues

    async def _generate_node(self, state: ExerciseState) -> dict:
        """生成题目（LLM 产出后经 validate→normalize 把关）。

        流式：每校验完一题即通过 `current_on_token` 下发该题题面，
        用户能看到题目**逐题出现**（而非等待全部完成）。
        """
        from app.utils.quiz_validator import validate_question

        plan = state.get("plan", [])
        purpose = state.get("purpose", "")
        knowledge_node_id = state.get("knowledge_node_id")
        questions = []
        # P3-B3a：回调来自模块级 ContextVar（按协程隔离），与 TutorAgent 同一机制
        on_token = current_on_token.get()

        conditions = {"warmup": purpose == "warmup_not_exam"}
        # 同上：平台人设必须落在 system 栏，不能靠 user 模板夹带
        quiz_system = self._load_prompt(
            "pipeline.yaml", conditions=conditions, key="quiz_system"
        )
        quiz_user_tpl = self._load_extra_prompt("pipeline.yaml", key="quiz_user")

        total = len(plan)
        if on_token is not None and total:
            await _emit(on_token, f"已为你生成 {total} 道练习题：\n\n")

        for index, template in enumerate(plan, 1):
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
                    "purpose": purpose,
                },
            )

            result = await self._call_llm_json(
                system_prompt=quiz_system,
                user_prompt=user_prompt,
                expected_key="question",
                fallback={},
                validator=self._validate_question,
            )

            if result:
                normalized, issues = validate_question(result)
                if issues:
                    logger.warning(f"Question {q_id} has {len(issues)} issue(s): {issues}")
                normalized["topic"] = topic
                if knowledge_node_id:
                    normalized["knowledge_node_id"] = knowledge_node_id
                questions.append(normalized)
            else:
                mock_q = self._mock_question(q_type, topic)
                mock_q, _issues = validate_question(mock_q)
                mock_q["topic"] = topic
                if knowledge_node_id:
                    mock_q["knowledge_node_id"] = knowledge_node_id
                questions.append(mock_q)

            # 校验通过后立即下发该题题面（结构化产物 → Markdown，不吐原始 JSON）
            await _emit(on_token, format_question_markdown(index, questions[-1]) + "\n")

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
        if q_type == "code":
            return {
                "question_type": "code",
                "question": f"请编写代码实现{topic}的核心逻辑，要求函数签名正确且包含必要的注释。",
                "options": None,
                "correct_answer": f"# 参考实现\ndef {topic.lower().replace(' ', '_')}(input_data):\n    # TODO: 实现{topic}的核心逻辑\n    pass",
                "explanation": f"代码需要正确实现{topic}的算法流程，注意边界条件处理。",
            }
        return {
            "question_type": "short_answer",
            "question": f"请简要解释{topic}的核心原理。",
            "options": None,
            "correct_answer": f"{topic}的核心原理是...（参考答案）",
            "explanation": f"{topic}的核心在于理解其基本原理和应用场景。",
        }

    async def _review_node(self, state: ExerciseState) -> dict:
        """Review：组装最终输出，并把**参考答案**流式下发。

        为什么要在这里也发 token：前端收到 token 后会跳过收尾帧（防重复），
        答案若只放在收尾帧里就不会显示。题面在 `_generate_node` 逐题下发，
        答案在此统一下发（顺序即「先做题、后对答案」）。
        """
        questions = state.get("questions", [])
        topic = state.get("topic", "")
        count = len(questions)

        response = f"已为您生成「{topic}」的 {count} 道练习题。"

        on_token = current_on_token.get()
        if on_token is not None and questions:
            await _emit(on_token, "\n---\n\n**参考答案**\n\n")
            for index, question in enumerate(questions, 1):
                await _emit(on_token, format_answer_markdown(index, question) + "\n")

        return {"response": response, "stage": "reviewed"}
