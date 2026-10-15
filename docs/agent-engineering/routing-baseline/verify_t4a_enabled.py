"""T4-A 最终启用验收：t4a_enabled=True + 真模型语义腿，跑 140 条，对账更新后的 Gold。

真调 DeepSeek（用户已授权）。只读，不改任何 Gold/代码。

输出：
  1. 三态分布
  2. 启用接管了多少条、每条接管前后 vs gold
  3. 对 DRAFT_CONFIRMED（gold_capability 明确）的改善/变差统计
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

from dotenv import load_dotenv
load_dotenv(os.path.join(AI_SERVICE, ".env"))

from app.centers.chat_center import ChatCenter  # noqa: E402
from app.services.intent_extractor import IntentExtractor  # noqa: E402

CASES = os.path.join(HERE, "routing_cases.jsonl")
GOLD = os.path.join(HERE, "routing_gold_review.csv")

# 启用接管 + 真模型语义腿
_center = ChatCenter(
    t4a_enabled=True,
    semantic_extractor=IntentExtractor(use_mock=False),
)


def load_cases():
    with open(CASES, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_gold():
    with open(GOLD, encoding="utf-8-sig") as fh:
        return {r["case_id"]: r for r in csv.DictReader(fh)}


def build_context(history, message):
    messages = list(history or []) + [{"role": "user", "content": message}]
    return {"messages": messages, "style": "standard", "images": [],
            "user_id": 0, "conversation_id": None}


async def main():
    cases = load_cases()
    gold = load_gold()
    states = {}
    taken = []
    for case in cases:
        cid = case["case_id"]
        message = case.get("message", "")
        mode = case.get("mode", "auto")
        ctx = build_context(case.get("history") or [], message)
        plan = await _center.route(message=message, mode=mode, context=ctx)
        meta = plan.intent_meta or {}
        st = meta.get("semantic_state")
        states[cid] = st
        intents = [t.intent for t in plan.tasks]
        # 被接管 = 不确定态 + 最终不是纯 tutor_question
        if st == "uncertain" and intents != ["tutor_question"]:
            taken.append((cid, message, intents, gold[cid]))

    from collections import Counter
    print("三态分布:", dict(Counter(states.values())))
    print(f"启用接管了 {len(taken)} 条\n")

    # 对账：接管后 vs gold（只看 gold_capability 明确、非"待澄清"的）
    improved, worsened, same = [], [], []
    for cid, msg, intents, g in taken:
        gc = g["gold_capability"]
        if gc in ("待澄清", "待裁决"):
            continue
        # 接管后的 mode 集合
        from app.services.capability_map import INTENT_CENTER_MAP as ICM
        modes = {ICM.get(i) for i in intents}
        gold_modes = {ICM.get(i) for i in g["gold_intents"].split("|") if i}
        if modes & gold_modes:
            improved.append((cid, msg, intents, gc))
        else:
            worsened.append((cid, msg, intents, gc))

    print(f"接管且 gold 明确：改善 {len(improved)} / 变差 {len(worsened)}")
    print("\n改善样例:")
    for cid, msg, intents, gc in improved[:15]:
        print(f"  {cid} -> {intents}  gold={gc} | {msg[:22]}")
    print("\n变差样例:")
    for cid, msg, intents, gc in worsened[:15]:
        print(f"  {cid} -> {intents}  gold={gc} | {msg[:22]}")


asyncio.run(main())
