"""T4-B 指代消解启用对照：t4b_enabled=True 跑 20 条多轮上下文，看指代消解 vs gold。"""
import asyncio
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "ai-service")))

from app.centers.chat_center import ChatCenter  # noqa: E402

CASES = os.path.join(HERE, "routing_cases.jsonl")
GOLD = os.path.join(HERE, "routing_gold_review.csv")

cc = ChatCenter(t4b_enabled=True)

cases = [json.loads(l) for l in open(CASES, encoding="utf-8") if l.strip()]
gold = {r["case_id"]: r for r in csv.DictReader(open(GOLD, encoding="utf-8-sig"))}


def build_ctx(history, message):
    msgs = list(history or []) + [{"role": "user", "content": message}]
    return {"messages": msgs, "style": "standard", "images": [], "user_id": 0, "conversation_id": None}


async def main():
    multi = [c for c in cases if c.get("history")]
    rescued = 0
    for c in multi:
        cid = c["case_id"]
        msg = c["message"]
        plan = await cc.route(msg, mode="auto", context=build_ctx(c.get("history") or [], msg))
        intents = [t.intent for t in plan.tasks]
        g = gold[cid]
        gold_intents = g["gold_intents"].split("|")
        ok = intents[:1] == gold_intents[:1]
        if ok:
            rescued += 1
        print(f"{cid} 启用后={intents}  gold={gold_intents[:1]}  首意图对齐={ok} | {msg[:20]}")

    print(f"\n指代消解后首意图对齐 gold: {rescued}/{len(multi)}")


asyncio.run(main())
