"""T4-B 旁路探针：detect_compound_order 对 15 条复合任务的识别率（只读，不改路由）。"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "ai-service")))

from app.services.semantic_router import detect_compound_order  # noqa: E402

CASES = os.path.join(HERE, "routing_cases.jsonl")
GOLD = os.path.join(HERE, "routing_gold_review.csv")

cases = [json.loads(l) for l in open(CASES, encoding="utf-8") if l.strip()]
gold = {r["case_id"]: r for r in csv.DictReader(open(GOLD, encoding="utf-8-sig"))}

compound = [c for c in cases if c["category"] == "复合任务"]
print(f"复合任务 {len(compound)} 条\n")

hit = 0
for c in compound:
    cid = c["case_id"]
    msg = c["message"]
    parts = detect_compound_order(msg)
    g = gold[cid]
    order = g["gold_task_order"]
    mark = ""
    if parts:
        hit += 1
        if order and ">" in order:
            mark = f"  gold顺序={order}"
    print(f"{cid} 切分={parts}{mark}  | {msg[:30]}")

print(f"\n识别出复合结构: {hit}/{len(compound)}")
