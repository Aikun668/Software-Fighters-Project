"""T4-B 复合语义多意图启用对照：t4b_enabled=True + 真模型语义腿，跑 15 条复合任务。

验证：复合句走语义腿后，多意图救回第二诉求 + 顺序对齐 gold。
"""
import asyncio
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AI = os.path.abspath(os.path.join(HERE, "..", "..", "..", "ai-service"))
sys.path.insert(0, AI)

from dotenv import load_dotenv
load_dotenv(os.path.join(AI, ".env"))

from app.centers.chat_center import ChatCenter  # noqa: E402
from app.services.intent_extractor import IntentExtractor  # noqa: E402

CASES = os.path.join(HERE, "routing_cases.jsonl")
GOLD = os.path.join(HERE, "routing_gold_review.csv")

cc = ChatCenter(
    t4b_enabled=True,
    semantic_extractor=IntentExtractor(use_mock=False),
)

cases = [json.loads(l) for l in open(CASES, encoding="utf-8") if l.strip()]
gold = {r["case_id"]: r for r in csv.DictReader(open(GOLD, encoding="utf-8-sig"))}


def build_ctx(history, message):
    msgs = list(history or []) + [{"role": "user", "content": message}]
    return {"messages": msgs, "style": "standard", "images": [], "user_id": 0, "conversation_id": None}


async def main():
    compound = [c for c in cases if c["category"] == "复合任务"]
    aligned = 0
    for c in compound:
        cid = c["case_id"]
        msg = c["message"]
        plan = await cc.route(msg, mode="auto", context=build_ctx(c.get("history") or [], msg))
        intents = [t.intent for t in plan.tasks]
        g = gold[cid]
        gold_intents = g["gold_intents"].split("|")
        # 对齐：前2个意图（去重后）与 gold 前2个一致
        seen = []
        for i in intents:
            if i not in seen:
                seen.append(i)
        ok = seen[:2] == gold_intents[:2]
        if ok:
            aligned += 1
        print(f"{cid} 启用后={seen}  gold={gold_intents[:2]}  对齐={ok} | {msg[:26]}")

    print(f"\n复合句前2意图对齐 gold: {aligned}/{len(compound)}")


asyncio.run(main())
