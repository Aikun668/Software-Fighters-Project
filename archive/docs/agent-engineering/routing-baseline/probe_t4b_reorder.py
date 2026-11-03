"""T4-B 顺序重排启用对照：t4b_enabled=True 跑 140 条，复合句顺序 vs gold_task_order。"""
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

cases = [json.loads(l) for l in open(CASES, encoding="utf-8") if l.strip()]
gold = {r["case_id"]: r for r in csv.DictReader(open(GOLD, encoding="utf-8-sig"))}

cc = ChatCenter(t4b_enabled=True)


def build_ctx(history, message):
    msgs = list(history or []) + [{"role": "user", "content": message}]
    return {"messages": msgs, "style": "standard", "images": [], "user_id": 0, "conversation_id": None}


async def main():
    compound = [c for c in cases if c["category"] == "复合任务"]
    improved = 0
    for c in compound:
        cid = c["case_id"]
        msg = c["message"]
        plan = await cc.route(msg, mode="auto", context=build_ctx(c.get("history") or [], msg))
        intents = [t.intent for t in plan.tasks]
        g = gold[cid]
        order = g["gold_task_order"]
        gold_intents = [x.split("(")[0] for x in order.split(">")] if ">" in order else g["gold_intents"].split("|")
        # 是否顺序对齐：前两个意图与 gold 前两个一致
        ok = intents[:2] == gold_intents[:2] if len(gold_intents) >= 2 else True
        if ok and len(intents) >= 2:
            improved += 1
        print(f"{cid} 启用后意图={intents}  gold={gold_intents}  对齐={ok} | {msg[:26]}")

    print(f"\n复合句顺序对齐 gold: {improved}/{len(compound)}")


asyncio.run(main())
