"""评测集数据一致性复查（Task 9 · 人工复查的机械辅助）。

把 chat_foundation_v1.jsonl 的每条样例跑过真实的 CapabilityGate（确定性规则、
无 LLM），报告 expected_route 与实际路由不一致的条目。

用途：
1. 防止标定错误（如把“知识图谱是什么？”误标成 VISUALIZATION）；
2. 暴露 CapabilityGate 与评测集的分歧——分歧条目需要人工裁决：
   是评测集措辞歧义（改数据），还是门控规则缺陷（回 Task 4 修）。

用法（在 ai-service 目录）：
    python ../evals/verify_routes.py

退出码：0 = 60/60 一致；1 = 存在分歧（附清单）。
"""

import json
import sys
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EVALS_DIR.parent
AI_SERVICE = PROJECT_ROOT / "ai-service"
sys.path.insert(0, str(AI_SERVICE))

from app.services.capability_gate import CapabilityGate  # noqa: E402


def main() -> int:
    eval_file = EVALS_DIR / "chat_foundation_v1.jsonl"
    entries = [json.loads(line) for line in eval_file.read_text(encoding="utf-8").splitlines() if line.strip()]

    gate = CapabilityGate()
    mismatches = []
    for e in entries:
        decision = gate.decide(e["current_message"], mode="auto")
        actual = decision.kind.value
        if actual != e["expected_route"]:
            mismatches.append((e["id"], e["category"], e["current_message"], e["expected_route"], actual, decision.reason))

    print(f"共 {len(entries)} 条；CapabilityGate 一致 {len(entries) - len(mismatches)} 条，分歧 {len(mismatches)} 条\n")
    if mismatches:
        print(f"{'id':8} {'类别':18} {'当前消息':40} {'标定':16} {'实际':16} 原因")
        for mid, cat, msg, exp, act, reason in mismatches:
            print(f"{mid:8} {cat:18} {msg[:38]:40} {exp:16} {act:16} {reason}")

    # 类别数量核对
    expect_counts = {"normal_qa": 20, "context_followup": 12, "user_correction": 8,
                     "ambiguous_followup": 8, "capability_request": 8, "no_false_trigger": 4}
    got_counts: dict[str, int] = {}
    for e in entries:
        got_counts[e["category"]] = got_counts.get(e["category"], 0) + 1
    print()
    for cat, want in expect_counts.items():
        got = got_counts.get(cat, 0)
        mark = "OK " if got == want else "BAD"
        print(f"[{mark}] {cat}: {got}/{want}")

    return 0 if not mismatches else 1


if __name__ == "__main__":
    sys.exit(main())
