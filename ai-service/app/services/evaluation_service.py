import json
import logging

from app.services.llm_service import get_llm_service

logger = logging.getLogger(__name__)


def grade_choice(user_answer: str, correct_answer: str, choices: list[str] | None = None) -> dict:
    user_clean = user_answer.strip().upper()
    correct_clean = correct_answer.strip().upper()
    is_correct = user_clean == correct_clean

    result = {
        "type": "choice",
        "correct": is_correct,
        "score": 1 if is_correct else 0,
        "user_answer": user_answer,
        "correct_answer": correct_answer,
    }
    return result


async def grade_short_answer(user_answer: str, reference_answer: str, rubric: str = "") -> dict:
    if not user_answer or not user_answer.strip():
        return {
            "type": "short_answer",
            "score": 0,
            "feedback": "未作答",
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
        start = response.find('{')
        end = response.rfind('}') + 1
        if start >= 0 and end > start:
            result = json.loads(response[start:end])
            result["type"] = "short_answer"
            result["score"] = int(result.get("score", 0))
            return result
        else:
            logger.warning(f"LLM judge returned non-JSON: {response[:100]}")
            return {"type": "short_answer", "score": 0, "feedback": "评分失败", "key_points_matched": [], "key_points_missed": []}
    except Exception as e:
        logger.error(f"LLM judge error: {e}")
        return {"type": "short_answer", "score": 0, "feedback": "评分服务暂时不可用，请稍后重试", "key_points_matched": [], "key_points_missed": []}


async def evaluate_session(answers: list[dict]) -> dict:
    results = []
    total_score = 0
    max_score = 0

    for ans in answers:
        if ans.get("type") == "choice":
            result = grade_choice(
                ans["user_answer"],
                ans["correct_answer"],
                ans.get("choices", [])
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
        normalized = result["score"] if ans.get("type") == "short_answer" else result["score"] * 100
        total_score += normalized
        max_score += 100

    overall_score = round(total_score / max_score * 100) if max_score > 0 else 0

    module_scores = {}
    for r in results:
        mod = r["module"]
        if mod not in module_scores:
            module_scores[mod] = {"total": 0, "count": 0}
        normalized = r["score"] if r["type"] == "short_answer" else r["score"] * 100
        module_scores[mod]["total"] += normalized
        module_scores[mod]["count"] += 1

    weak_modules = [
        mod for mod, scores in module_scores.items()
        if scores["count"] > 0 and scores["total"] / scores["count"] / 100 < 0.6
    ]

    return {
        "results": results,
        "total_score": total_score,
        "max_score": max_score,
        "overall_score": overall_score,
        "weak_modules": weak_modules,
    }
