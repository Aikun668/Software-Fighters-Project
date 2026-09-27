import logging
from typing import Any

from app.agents.exercise_agent import ExerciseAgent
from app.services.evaluation_service import grade_choice, grade_short_answer

logger = logging.getLogger(__name__)


class DiagnoseAgent:
    """BKT 诊断 Agent — 根据答题表现更新技能掌握度并给出诊断报告。"""

    _DEFAULT_P_LEARN = 0.3
    _DEFAULT_P_SLIP = 0.1
    _DEFAULT_P_GUESS = 0.2
    _DEFAULT_P_TRANS = 0.1

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        exercise_agent: ExerciseAgent | None = None,
        use_mock_llm: bool = False,
        p_learn: float = _DEFAULT_P_LEARN,
        p_slip: float = _DEFAULT_P_SLIP,
        p_guess: float = _DEFAULT_P_GUESS,
        p_trans: float = _DEFAULT_P_TRANS,
    ):
        self.config = config or {}
        self.exercise_agent = exercise_agent
        # P0-B：非 BaseAgent 子类，需显式持有旗标以统一装配口径
        self.use_mock_llm = use_mock_llm
        self.p_learn = p_learn
        self.p_slip = p_slip
        self.p_guess = p_guess
        self.p_trans = p_trans

    async def run(self, state: dict) -> dict:
        topic = state.get("topic", "")
        skills = state.get("skills") or [topic]
        prior_mastery = state.get("prior_mastery") or {}
        attempts = state.get("attempts", [])
        student_profile = state.get("student_profile", {})

        if not attempts and self.exercise_agent is not None:
            attempts = await self._generate_attempts(topic, skills, student_profile)

        graded = await self._grade_attempts(attempts)
        mastery_vector = self._update_bkt(skills, prior_mastery, graded)
        report = self._build_report(skills, mastery_vector, graded)

        logger.info(f"DiagnoseAgent: topic='{topic}' skills={len(skills)} attempts={len(graded)}")

        return {
            "mastery_vector": mastery_vector,
            "report": report,
            "next_skill": report["next_skill"],
            "confidence": report["confidence"],
            "response": report["response"],
        }

    async def _generate_attempts(self, topic: str, skills: list[str], student_profile: dict) -> list[dict]:
        try:
            agent = self.exercise_agent or ExerciseAgent(use_mock_llm=self.use_mock_llm)
            state = await agent.run({
                "topic": topic,
                "count": len(skills) * 2 or 3,
                "difficulty": "medium",
                "student_profile": student_profile,
                "purpose": "diagnose",
            })
            questions = state.get("questions", [])
            return [
                {
                    "skill": q.get("topic", topic),
                    "question": q,
                    "user_answer": "",
                    "is_correct": False,
                }
                for q in questions
            ]
        except Exception as e:
            logger.warning(f"DiagnoseAgent failed to generate attempts: {e}", exc_info=True)
            return []

    async def _grade_attempts(self, attempts: list[dict]) -> list[dict]:
        graded = []
        for attempt in attempts:
            question = attempt.get("question", {})
            user_answer = attempt.get("user_answer", "")
            q_type = question.get("question_type", "choice")

            if not user_answer:
                graded.append({**attempt, "is_correct": False, "score": 0, "max_score": 1})
                continue

            if q_type == "choice":
                result = grade_choice(
                    user_answer,
                    question.get("correct_answer", ""),
                    list(question.get("options", {}).values()) if isinstance(question.get("options"), dict) else question.get("options"),
                )
            elif q_type == "short_answer":
                result = await grade_short_answer(
                    user_answer,
                    question.get("correct_answer", ""),
                    question.get("rubric", ""),
                )
            else:
                result = {"correct": False, "score": 0, "max_score": 1}

            graded.append({
                **attempt,
                "is_correct": bool(result.get("correct", False)),
                "score": result.get("score", 0),
                "max_score": result.get("max_score", 1),
            })
        return graded

    def _update_bkt(
        self,
        skills: list[str],
        prior_mastery: dict[str, float],
        graded: list[dict],
    ) -> dict[str, float]:
        mastery = {skill: prior_mastery.get(skill, self.p_learn) for skill in skills}
        attempts_by_skill: dict[str, list[bool]] = {skill: [] for skill in skills}

        for attempt in graded:
            skill = attempt.get("skill") or attempt.get("question", {}).get("topic")
            if skill in attempts_by_skill:
                attempts_by_skill[skill].append(attempt.get("is_correct", False))

        for skill in skills:
            p_know = mastery[skill]
            for correct in attempts_by_skill.get(skill, []):
                p_know = self._bkt_step(p_know, correct)
            mastery[skill] = round(min(max(p_know, 0.0), 1.0), 3)

        return mastery

    def _bkt_step(self, p_know: float, correct: bool) -> float:
        p_know = min(max(p_know, 0.0), 1.0)
        p_slip = min(max(self.p_slip, 0.0), 1.0)
        p_guess = min(max(self.p_guess, 0.0), 1.0)
        p_trans = min(max(self.p_trans, 0.0), 1.0)

        if correct:
            numerator = p_know * (1 - p_slip)
            denominator = numerator + (1 - p_know) * p_guess
        else:
            numerator = p_know * p_slip
            denominator = numerator + (1 - p_know) * (1 - p_guess)

        p_know_given_obs = numerator / denominator if denominator > 0 else p_know
        return p_know_given_obs + (1 - p_know_given_obs) * p_trans

    def _build_report(
        self,
        skills: list[str],
        mastery_vector: dict[str, float],
        graded: list[dict],
    ) -> dict:
        strengths = [s for s in skills if mastery_vector.get(s, 0) >= 0.75]
        weaknesses = [s for s in skills if mastery_vector.get(s, 0) < 0.6]
        next_skill = weaknesses[0] if weaknesses else min(skills, key=lambda s: mastery_vector.get(s, 0))

        suggestions = []
        if weaknesses:
            suggestions.append(f"针对「{next_skill}」进行专项练习，巩固基础概念。")
        if len(graded) >= 2:
            correct_count = sum(1 for a in graded if a.get("is_correct"))
            suggestions.append(f"本次共 {len(graded)} 题，答对 {correct_count} 题，可继续通过同类题目强化薄弱点。")
        if strengths:
            suggestions.append(f"「{strengths[0]}」掌握较好，可作为锚点横向迁移到其他知识点。")

        confidence = min(0.95, 0.5 + 0.1 * len(graded)) if graded else 0.5

        return {
            "strengths": strengths[:3] or ["暂无显著优势项"],
            "weaknesses": weaknesses[:3] or ["暂无显著薄弱项"],
            "suggestions": suggestions[:3] or ["建议通过练习积累更多诊断数据。"],
            "next_skill": next_skill,
            "confidence": round(confidence, 2),
            "response": (
                f"诊断完成。当前「{next_skill}」为最薄弱环节(掌握度 {mastery_vector.get(next_skill, 0):.0%})，"
                f"建议优先针对该技能进行专项练习。"
            ),
        }
