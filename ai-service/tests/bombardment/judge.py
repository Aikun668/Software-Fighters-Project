"""LLM 裁判 — 用场景化的评审提示词评测 AI 回复质量。

设计原则:
  - 每个场景自带 rubric（评分标准），裁判严格按维度打分
  - 输出结构化 JSON，方便量化汇总
  - 裁判本身也是 LLM 调用，走同一 AI 服务的 /api/chat
"""

import json
import re

import requests
import requests.exceptions

JUDGE_URL = "http://127.0.0.1:8001/internal/eval/judge"
JUDGE_TIMEOUT = 90  # 裁判调用超时


def call_judge(rubric_template: str, response_text: str) -> dict:
    """调用 LLM 裁判（走独立 /eval/judge 端点，不经 Agent 包装）。"""
    rubric = rubric_template.replace("{response}", response_text[:3000])

    message = (
        "请严格按以下JSON格式输出评分结果，不要输出任何其他内容:\n"
        '{"scores": {"维度1": 0.X, "维度2": 0.X}, "total": 0.X, "verdict": "PASS或WARN或FAIL", "comment": "一句话点评"}\n\n'
        + rubric
    )

    body = {"message": message, "system_prompt": "你是一个严格的评审专家。只输出要求的JSON格式。"}

    try:
        r = requests.post(JUDGE_URL, json=body, timeout=JUDGE_TIMEOUT)
        if r.status_code != 200:
            return _judge_fallback(f"HTTP {r.status_code}")

        data = r.json()
        if data.get("success"):
            text = data.get("data", {}).get("response", "")
            if text:
                return _parse_judge_json(text)

        return _judge_fallback(f"裁判响应异常: {data.get('error', 'unknown')}")

    except (requests.exceptions.Timeout, requests.Timeout):
        return _judge_fallback("裁判超时")
    except Exception as e:
        return _judge_fallback(str(e))


def _parse_judge_json(text: str) -> dict:
    """从裁判输出中提取 JSON 评分。鲁棒处理多种输出格式。"""
    # 1. 提取 markdown code block 中的 JSON
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 2. 直接匹配含有 scores 的 JSON 对象（贪婪）
    m = re.search(r"\{[\s\S]*\"scores\"[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    # 3. 尝试整个文本作为 JSON
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # 4. 兜底: 正则提取各维度数字评分
    dim_scores = {}
    for m in re.finditer(r"['\"]?([^'\"]+)['\"]?\s*[:：]\s*([0-9.]+)", text):
        key = m.group(1).strip()
        val = float(m.group(2))
        if 0 <= val <= 1:
            dim_scores[key] = val
    if dim_scores:
        avg = sum(dim_scores.values()) / len(dim_scores)
        return {
            "scores": dim_scores,
            "total": round(avg, 2),
            "verdict": "PASS" if avg >= 0.6 else "WARN",
            "comment": "regex fallback",
        }

    return _judge_fallback(f"无法解析裁判输出: {text[:200]}")


def _judge_fallback(reason: str) -> dict:
    return {
        "scores": {},
        "total": 0.0,
        "verdict": "ERROR",
        "comment": reason,
    }


def run_judges_parallel(scenarios_with_responses: list[tuple[dict, str]]) -> list[dict]:
    """顺序运行裁判（避免轰炸后服务过载导致连接重置）。"""
    results = []

    for i, (scenario, response) in enumerate(scenarios_with_responses):
        rubric = scenario["judge"]["rubric"]
        result = call_judge(rubric, response)
        result["scenario_id"] = scenario["id"]
        result["category"] = scenario["category"]
        result["description"] = scenario["description"]
        result["pass_threshold"] = scenario["judge"]["pass_threshold"]
        results.append(result)

    return results
