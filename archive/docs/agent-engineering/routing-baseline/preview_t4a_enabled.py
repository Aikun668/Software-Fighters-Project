"""T4-A 启用预演（只读，不改任何提交产物）：t4a_enabled=True 时 140 条会被接管成什么。

对照 gold：只统计「接管是否让旧行为更接近 gold」。不做任何裁决、不写 reviewer_decision。

运行：
    cd ai-service
    PYTHONUTF8=1 python ../docs/agent-engineering/routing-baseline/preview_t4a_enabled.py
"""
import asyncio
import csv
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
AI_SERVICE = os.path.abspath(os.path.join(HERE, "..", "..", "..", "ai-service"))
sys.path.insert(0, AI_SERVICE)

from app.centers.chat_center import ChatCenter  # noqa: E402

CASES = os.path.join(HERE, "routing_cases.jsonl")
GOLD = os.path.join(HERE, "routing_gold_review.csv")

# 启用接管：t4a_enabled=True；语义腿用默认 IntentExtractor（离线 mock 关键词，
# 真 LLM 由 INTENT_USE_LLM=1 打开，本预演不真调模型、不花钱）
_center = ChatCenter(t4a_enabled=True)


def load_cases():
    with open(CASES, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def build_context(history, message):
    messages = list(history or []) + [{"role": "user", "content": message}]
    return {"messages": messages, "style": "standard", "images": [],
            "user_id": 0, "conversation_id": None}


def load_gold():
    with open(GOLD, encoding="utf-8-sig") as fh:
        return {r["case_id"]: r for r in csv.DictReader(fh)}


async def main():
    cases = load_cases()
    gold = load_gold()

    taken = []   # (case_id, message, old_intents, new_intents, gold_cap)
    for case in cases:
        message = case.get("message", "")
        mode = case.get("mode", "auto")
        ctx = build_context(case.get("history") or [], message)
        plan = await _center.route(message=message, mode=mode, context=ctx)
        meta = plan.intent_meta or {}
        if meta.get("semantic_state") == "uncertain" and meta.get("route_source") == "semantic":
            new_intents = [t.intent for t in plan.tasks]
            # 是否被接管：不再是纯 tutor_question
            taken.append((case["case_id"], message, new_intents, gold[case["case_id"]]))

    print(f"启用接管预演（mock 语义腿）：{len(taken)} 条 UNCERTAIN 且调用了语义")
    taken_changed = [t for t in taken if t[2] != ["tutor_question"]]
    print(f"其中语义结果接管了路由（不再 tutor_question）: {len(taken_changed)} 条")

    # 逐条看「接管结果 vs gold」
    print("\n接管明细（gold_cap 为空=待裁决/待澄清）:")
    for cid, msg, intents, g in taken_changed:
        gold_intents = g["gold_intents"].replace("|", ",")
        print(f"  {cid}  {intents}  gold=[{gold_intents}] cap={g['gold_capability']}  | {msg[:24]}")

    # 与 gold 对齐统计（仅 DRAFT_CONFIRMED 且 gold 有明确能力）
    def center_of(intent):
        return INTENT_CENTER.get(intent)

    from app.services.capability_map import INTENT_CENTER_MAP as INTENT_CENTER

    improved = 0
    worsened = 0
    for cid, msg, intents, g in taken_changed:
        if g["gold_status"] != "DRAFT_CONFIRMED":
            continue
        gold_cap = g["gold_capability"]
        if gold_cap in ("待裁决", "待澄清"):
            continue
        # 接管后的 mode 是否命中 gold 能力对应的 center
        gold_intents = g["gold_intents"].split("|")
        new_modes = {INTENT_CENTER.get(i) for i in intents}
        gold_modes = {INTENT_CENTER.get(i) for i in gold_intents}
        if new_modes & gold_modes:
            improved += 1
        else:
            worsened += 1
    print(f"\nDRAFT_CONFIRMED 且被接管: 改善 {improved} / 变差 {worsened}")


if __name__ == "__main__":
    asyncio.run(main())
