import logging

from app.services.llm_service import get_llm_service
from app.utils.json_parser import parse_llm_json
from app.utils.prompt_guard import sanitize_for_llm

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
{sanitize_for_llm(user_answer)}

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


async def grade_code(user_code: str, reference_solution: str = "", test_cases: str = "") -> dict:
    """LLM 批改代码题：语法、逻辑、边界case 三维评分。"""
    if not user_code or not user_code.strip():
        return {
            "type": "code",
            "correct": False,
            "score": 0,
            "earned": 0,
            "max_score": 100,
            "feedback": "未提交代码",
            "syntax_ok": False,
            "logic_ok": False,
            "edge_cases_ok": False,
            "ai_comment": "",
        }

    prompt = f"""你是一位严格的编程导师。请评估以下学生代码。

【题目要求 / 参考解答】
{reference_solution or "（未提供，请根据代码本身质量评估）"}

【测试用例】
{test_cases or "（未提供）"}

【学生代码】
{sanitize_for_llm(user_code)}

请从三个维度评估并以 JSON 格式输出（只输出 JSON）：
{{
  "score": <0-100的整数>,
  "syntax_ok": <true/false, 语法/缩进是否基本正确>,
  "logic_ok": <true/false, 算法思路是否正确>,
  "edge_cases_ok": <true/false, 边界条件是否处理>,
  "feedback": "<简评：指出优点+具体改进建议>"
}}"""

    try:
        llm = get_llm_service()
        response = await llm.chat([{"role": "user", "content": prompt}])
        result = parse_llm_json(response, fallback={}, expected_key="score")
        if not isinstance(result, dict) or "score" not in result:
            logger.warning(f"LLM code judge returned invalid response: {str(response)[:100]}")
            return {
                "type": "code", "correct": False, "score": 0, "earned": 0, "max_score": 100,
                "feedback": "评分失败", "syntax_ok": False, "logic_ok": False,
                "edge_cases_ok": False, "ai_comment": "",
            }
        result["type"] = "code"
        result["score"] = int(result.get("score", 0))
        result["earned"] = result["score"]
        result["max_score"] = 100
        result["correct"] = result["score"] >= 60
        result["ai_comment"] = result.get("feedback", "")
        result.setdefault("syntax_ok", False)
        result.setdefault("logic_ok", False)
        result.setdefault("edge_cases_ok", False)
        return result
    except Exception as e:
        logger.error(f"LLM code judge error: {e}")
        return {
            "type": "code", "correct": False, "score": 0, "earned": 0, "max_score": 100,
            "feedback": "评分服务暂时不可用，请稍后重试",
            "syntax_ok": False, "logic_ok": False, "edge_cases_ok": False, "ai_comment": "",
        }


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


def generate_report(evaluation_results: dict, student_profile: dict | None = None) -> dict:
    """从评估结果生成结构化报告（纯函数）。

    Args:
        evaluation_results: 评估结果 {results, overall_score, weak_modules, ...}
        student_profile: 可选的学生画像，用于合并弱项推荐
    """
    results = evaluation_results.get("results", [])
    overall_score = evaluation_results.get("overall_score", 0)
    weak_modules = evaluation_results.get("weak_modules", [])
    total_score = evaluation_results.get("total_score", 0)
    max_score = evaluation_results.get("max_score", 0)

    def _is_correct(r: dict) -> bool:
        if "correct" in r:
            return bool(r["correct"])
        score = r.get("score", 0)
        is_short = r.get("type") == "short_answer"
        default_max = 100 if is_short else 1
        max_s = r.get("max_score", default_max) or 1
        return (score / max_s) >= 0.6

    correct_count = sum(1 for r in results if _is_correct(r))
    total_count = len(results)
    accuracy = round(correct_count / total_count * 100) if total_count > 0 else 0

    strengths = []
    improvements = []
    for r in results:
        if r.get("correct"):
            strengths.append(r.get("question", ""))
        else:
            improvements.append(r.get("question", ""))

    # 维度得分（按 module 分组）
    dimension_scores: dict[str, float] = {}
    module_totals: dict[str, list[float]] = {}
    for r in results:
        mod = r.get("module", "general")
        module_totals.setdefault(mod, []).append(
            r.get("earned", 0) / max(r.get("max_score", 1), 1)
        )
    for mod, ratios in module_totals.items():
        dimension_scores[mod] = round(sum(ratios) / len(ratios) * 100)

    # 建议
    suggestions: list[str] = []
    if overall_score < 50:
        suggestions.append(f"建议重点复习 {', '.join(weak_modules)} 相关知识点，重新学习基础内容")
    elif overall_score < 75:
        suggestions.append("建议针对薄弱模块进行深入练习")
    if weak_modules:
        suggestions.extend(f"需要加强 {wm} 的学习" for wm in weak_modules[:3])
    if overall_score >= 85:
        suggestions.append("掌握良好，建议挑战更高难度的内容")

    # 合并 profile 中的 weak_points
    recommended_weak_points = list(weak_modules)
    if student_profile:
        existing_weak = student_profile.get("weak_points") or []
        if isinstance(existing_weak, list):
            for w in existing_weak:
                if isinstance(w, str) and w not in recommended_weak_points:
                    recommended_weak_points.append(w)

    return {
        "overall_score": overall_score,
        "accuracy_pct": accuracy,
        "correct_count": correct_count,
        "total_count": total_count,
        "total_questions": total_count,
        "total_score": total_score,
        "max_score": max_score,
        "weak_modules": weak_modules,
        "dimension_scores": dimension_scores,
        "suggestions": suggestions,
        "recommended_weak_points": recommended_weak_points,
        "strength_areas": strengths[:5],
        "improvement_areas": improvements[:5],
    }
