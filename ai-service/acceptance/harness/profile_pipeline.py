#!/usr/bin/env python3
"""画像管线字节存证：**不 stub 工作流**，跑真实 `ProfileWorkflow`。

为什么单独一个 harness：`sse_all_endpoints.py` 的 `profile_chat` 用例把
`_get_profile_workflow` monkeypatch 成了替身，因此**测不到真实画像管线** ——
P3-B3b 合并双层图时，55 条存证全部"一致"，其实什么也没证明。本文件补上这个缺口。

用法（在 ai-service 目录）：
    python -m acceptance.harness.profile_pipeline after

设计：
- 用 `AI_SERVICE_MOCK_LLM=1`（P3-D 引入的环境开关）让 13 个工厂走 mock LLM，
  从而离线可跑，且输出确定 —— 不 patch `_get_mock_flag` 本体；
- 同一 commit 重跑应得到完全相同的 sha256；
- 跨 commit 比对可证明画像管线（含 `semantic_judge` / `audit`）**是否改变行为**。

归一化有两处（缺任一处都会把"语义等价"误报成"行为变化"）：

1. **时间戳**：正则把 ISO 日期/时间折叠成 `<TS>`（与 `plan_endpoints.py` 同法），防跨日/跨秒漂移；
2. **JSON 键序**：`data:` 载荷先 `json.loads` 再 `json.dumps(sort_keys=True)` 重编码。
   起因：P3-E 补丁轮（`deep_solve.py` 接入 `BaseWorkflow`）之后，画像载荷的**字段顺序**
   发生变化 —— 84 个事件逐条语义完全相同，但 raw-text 哈希全变（详见该轮验收记录）。
   键序归一化后，本 harness 只对**内容**负责，顺序抖动不再误报。
"""

import asyncio
import hashlib
import json
import os
import re
import sys

# ⚠️ 必须在 import app.* 之前设置：工厂在构造时读这个开关
os.environ.setdefault("AI_SERVICE_MOCK_LLM", "1")

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from internal_api import router  # noqa: E402

# 归一化：ISO 日期/时间（`2026-09-25`、`2026-09-25T12:34:56`）→ <TS>
_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}(?:T[\d:.]+)?(?:Z|[+-]\d{2}:?\d{2})?")
_DATA_PREFIX = "data: "


def _normalize_json_keys(text: str) -> str:
    """把 `data: {json}` 行的 JSON 键序归一化（`sort_keys=True`），其余行原样保留。

    只影响 **sha256 口径**，不改 harness 打印/落盘的原始文本（人看得到的仍是原始帧）。
    解析失败的行（非 JSON 帧）保持原样，避免掩盖真实畸形。
    """
    lines: list[str] = []
    for line in text.splitlines():
        if not line.startswith(_DATA_PREFIX):
            lines.append(line)
            continue
        try:
            payload = json.loads(line[len(_DATA_PREFIX):])
        except (ValueError, TypeError):
            lines.append(line)
            continue
        lines.append(
            _DATA_PREFIX + json.dumps(payload, ensure_ascii=False, sort_keys=True)
        )
    return "\n".join(lines)


def _entry(text: str) -> dict:
    """画像条目（`weak_points` / `interest_direction` 的元素形状）。"""
    return {"text": text, "confidence": 1, "updated_at": "<TS>"}


FULL_PROFILE = {
    "knowledge_base": 70,
    "cognitive_style": "visual",
    "learning_goal": "掌握机器学习基础",
    "weak_points": [_entry("梯度下降的数学推导")],
    "learning_pace": "fast",
    "interest_direction": [_entry("NLP")],
}

# (case 名, student_profile, 本轮用户消息)
CASES = [
    ("empty_profile_first_turn", {}, "我在学机器学习，刚入门"),
    # 与已有 weak_points 高度相似 → 走 semantic_judge 的候选预筛
    ("similar_weak_point_dedup", {
        "knowledge_base": 50,
        "weak_points": [_entry("梯度下降的数学推导")],
    }, "梯度下降的数学推导我总是搞不清楚"),
    # 6 维全满 → 走 complete 分支（固定文案，与管线产出的 response 覆盖关系）
    ("complete_profile_turn", FULL_PROFILE, "继续"),
]


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


async def main(label: str) -> int:
    blocks: list[str] = []
    app = _make_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", timeout=180.0,
    ) as client:
        for name, profile, message in CASES:
            response = await client.post("/internal/profile/chat", json={
                "user_id": 1,
                "student_profile": profile,
                "messages": [{"role": "user", "content": message}],
            })
            raw = _TS_RE.sub("<TS>", _normalize_json_keys(response.text))
            digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            blocks.append(
                f"### {name}\n"
                f"status={response.status_code}\n"
                f"sha256={digest}\n"
                f"{raw}\n"
            )

    report = "\n".join(blocks)
    with open(f"_accept_profile_pipeline_{label}.txt", "w", encoding="utf-8") as handle:
        handle.write(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "after")))
