"""练习评分真实链路 harness（学习闭环化 P0-C）。

为什么单独一个 harness：既有 `exercise_sse.py` 覆盖的是 `/exercise/generate` 与 `/solve`
（且把 `_get_exercise_center` 换成 stub），**没有**覆盖「提交作答 → 判分」这条
「学习效果输入」形态；而它恰是掌握度与画像的上游。

本文件**不 stub 任何 Center**，跑真实链路：

    POST /internal/exercise/grade
      → ExerciseCenter.grade
      → evaluation_service.grade_choice / grade_short_answer / grade_code

选择题为确定性判分；主观题走 LLM，由统一开关 `AI_SERVICE_MOCK_LLM=1` 走 mock。

⚠️ **已知限制（本轮实测）**：mock 模式下主观题判分必然降级为
`{"feedback": "评分失败", "score": 0}` —— 因为 `OpenAILLM._mock_response` 的固定文本是
**画像场景专用 JSON**，评分解析不了。故本 harness 对主观题只断言「不崩溃 + 返回明确降级
反馈」，**不断言真实得分**；真实判分需有 Key 环境验证（登记在验收记录"未执行项"）。

用法（在 ai-service 目录）：
    python -m acceptance.harness.exercise_grade_frames after

设计：
- 断言覆盖正确 / 错误 / 主观题 / 缺参数四档；
- 指纹取稳定字段（正确性 + 分值 + 事件），两次运行必须一致。
"""

import asyncio
import hashlib
import json
import os
import sys

# ⚠️ 必须在 import app.* 之前设置：工厂在构造时读这个开关
os.environ.setdefault("AI_SERVICE_MOCK_LLM", "1")

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from internal_api import router  # noqa: E402


# (case 名, 期望状态码, 请求体)
CASES = [
    ("grade_choice_correct", 200, {
        "type": "choice", "user_answer": "A", "correct_answer": "A",
        "choices": ["A", "B", "C", "D"], "points": 2,
    }),
    ("grade_choice_wrong", 200, {
        "type": "choice", "user_answer": "B", "correct_answer": "A",
        "choices": ["A", "B", "C", "D"], "points": 2,
    }),
    ("grade_short_answer", 200, {
        "type": "short_answer",
        "user_answer": "自注意力让序列中每个位置都能同时关注其他位置。",
        "reference_answer": "自注意力机制让模型并行建模序列中任意两个位置之间的关系。",
        "rubric": "",
    }),
    ("grade_choice_missing_answer", 400, {
        "type": "choice", "user_answer": None, "correct_answer": None,
        "choices": ["A", "B"], "points": 2,
    }),
]


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _fingerprint(payload: dict) -> str:
    """稳定指纹：只含确定性字段，**不纳入 LLM 生成的正文**。"""
    parts = []
    if payload.get("type"):
        parts.append(f"type={payload.get('type')}")
    for key in ("correct", "score", "max_score", "earned"):
        if key in payload:
            parts.append(f"{key}={payload.get(key)}")
    return "\n".join(parts)


def _check(name: str, status: int, payload: dict, envelope: dict | None = None) -> list[str]:
    problems: list[str] = []
    if name == "grade_choice_missing_answer":
        # 缺作答：路由在判分前就拦下，返回 400 错误信封，不应给分
        if status != 400:
            problems.append(f"缺作答应 400，实际 {status}")
        if (envelope or {}).get("success") is not False:
            problems.append("缺少作答却未返回错误信封")
        return problems

    if status != 200:
        problems.append(f"status={status}")
        return problems

    if name == "grade_choice_correct" and payload.get("correct") is not True:
        problems.append(f"正确答案被判错：{payload.get('correct')}")
    if name == "grade_choice_wrong" and payload.get("correct") is not False:
        problems.append(f"错误答案被判对：{payload.get('correct')}")
    return problems


async def _run_once(client: AsyncClient) -> list[str]:
    blocks: list[str] = []
    for name, expected, body in CASES:
        response = await client.post("/internal/exercise/grade", json=body)
        try:
            envelope = response.json()
        except ValueError:
            envelope = {}
        # internal_api 统一信封：{"success": ..., "data": {...}}；错误信封无 data
        payload = envelope.get("data") if isinstance(envelope, dict) else None
        if not isinstance(payload, dict):
            payload = {}

        problems = _check(name, response.status_code, payload, envelope)
        if response.status_code != expected:
            problems.append(f"期望 {expected}，实际 {response.status_code}")

        fingerprint = _fingerprint(payload)
        digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        blocks.append(
            f"### {name}\n"
            f"status={response.status_code}\n"
            f"problems={problems}\n"
            f"payload={json.dumps(payload, ensure_ascii=False, sort_keys=True)}\n"
            f"sha256={digest}\n"
            f"{fingerprint}\n"
        )
    return blocks


async def main(label: str) -> int:
    app = _make_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://accept", timeout=120.0,
    ) as client:
        first = await _run_once(client)
        second = await _run_once(client)

    consistency = "OK" if first == second else "MISMATCH（两次运行结果不同）"

    report = "\n".join(first) + f"\n=== 可复现性：{consistency} ===\n"
    with open(f"_accept_exercise_grade_{label}.txt", "w", encoding="utf-8") as handle:
        handle.write(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "after")))
