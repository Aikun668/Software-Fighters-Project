import logging

from app.services.llm_service import get_llm_service
from app.utils.json_parser import parse_llm_json

logger = logging.getLogger(__name__)


def grade_choice(user_answer: str, correct_answer: str, choices: list[str] | None = None, multi: bool = False, points: int = 1) -> dict:
    if multi:
        user_set = set(a.strip().upper() for a in user_answer.replace(" ", "").split(",") if a)
        correct_set = set(a.strip().upper() for a in correct_answer.replace(" ", "").split(",") if a)
        is_correct = user_set == correct_set
    else:
        user_clean = user_answer.strip().upper()
        correct_clean = correct_answer.strip().upper()
        is_correct = user_clean == correct_clean

    return {
        "type": "choice",
        "correct": is_correct,
        "score": points if is_correct else 0,
        "earned": points if is_correct else 0,
        "max_score": points,
        "user_answer": user_answer,
        "correct_answer": correct_answer,
        "feedback": "回答正确" if is_correct else f"回答错误，正确答案是 {correct_answer}",
    }


async def grade_short_answer(user_answer: str, reference_answer: str, rubric: str = "") -> dict:
    if not user_answer or not user_answer.strip():
        return {
            "type": "short_answer",
            "correct": False,
            "score": 0,
            "earned": 0,
            "max_score": 100,
            "feedback": "未作答",
            "ai_comment": "",
            "key_points_matched": [],
            "key_points_missed": ["所有要点"],
        }

    rubric_text = rubric or "根据参考答案评估学生回答的准确性和完整性"

    prompt = f"""你是一位严格的AI学习评估专家。请根据以下信息批改学生的简答题回答。

【参考答案】
{reference_answer}

【评分标准】
{rubric_text}

【学生回答】
{user_answer}

请以JSON格式输出评估结果（只输出JSON，不要其他文字）：
{{
  "score": <0-100的整数分数>,
  "feedback": "<简短评语，指出优点和不足>",
  "key_points_matched": ["<匹配到的要点1>", "<要点2>"],
  "key_points_missed": ["<遗漏的要点1>", "<要点2>"]
}}"""

    try:
        llm = get_llm_service()
        response = await llm.chat([{"role": "user", "content": prompt}])
        result = parse_llm_json(response, fallback={}, expected_key="score")
        if not isinstance(result, dict) or "score" not in result:
            logger.warning(f"LLM judge returned non-JSON or missing score: {response[:100]}")
            return {"type": "short_answer", "correct": False, "score": 0, "earned": 0,
                    "max_score": 100, "feedback": "评分失败",
                    "ai_comment": "", "key_points_matched": [], "key_points_missed": []}
        result["type"] = "short_answer"
        result["score"] = int(result.get("score", 0))
        result["earned"] = result["score"]
        result["max_score"] = 100
        result["correct"] = result["score"] >= 60
        result["ai_comment"] = result.get("feedback", "")
        return result
    except Exception as e:
        logger.error(f"LLM judge error: {e}")
        return {"type": "short_answer", "correct": False, "score": 0, "earned": 0,
                "max_score": 100, "feedback": "评分服务暂时不可用，请稍后重试",
                "ai_comment": "", "key_points_matched": [], "key_points_missed": []}


async def evaluate_session(answers: list[dict]) -> dict:
    results = []
    total_score = 0
    max_score = 0

    for ans in answers:
        if ans.get("type") == "choice":
            result = grade_choice(
                ans["user_answer"],
                ans["correct_answer"],
                ans.get("choices", []),
                multi=ans.get("multi", False),
                points=ans.get("points", 1),
            )
        elif ans.get("type") == "short_answer":
            result = await grade_short_answer(
                ans["user_answer"],
                ans.get("reference_answer", ""),
                ans.get("rubric", "")
            )
        else:
            continue

        result["question"] = ans.get("question", "")
        result["module"] = ans.get("module", "general")
        results.append(result)
        total_score += result["earned"]
        max_score += result["max_score"]

    overall_score = round(total_score / max_score * 100) if max_score > 0 else 0

    module_scores = {}
    for r in results:
        mod = r["module"]
        if mod not in module_scores:
            module_scores[mod] = {"total": 0, "count": 0}
        module_scores[mod]["total"] += r["earned"]
        module_scores[mod]["count"] += r["max_score"]

    weak_modules = [
        mod for mod, scores in module_scores.items()
        if scores["count"] > 0 and scores["total"] / scores["count"] < 0.6
    ]

    return {
        "results": results,
        "total_score": total_score,
        "max_score": max_score,
        "overall_score": overall_score,
        "weak_modules": weak_modules,
    }
