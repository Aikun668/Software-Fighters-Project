"""T4-B 旁路探针：子句级 gate 能否救回被吞的第二诉求（只读，不改路由）。

对 15 条复合任务：detect_compound_order 切分后，每个子句独立跑 CapabilityGate，
看「整体 gate 判出的能力」vs「子句级 gate 判出的能力集合」。
若子句级能识别出两个不同能力，证明"切分+子句级路由"能救回被吞诉求。
"""
import asyncio
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "ai-service")))

from app.services.capability_gate import CapabilityGate  # noqa: E402
from app.services.semantic_router import detect_compound_order  # noqa: E402

CASES = os.path.join(HERE, "routing_cases.jsonl")
GOLD = os.path.join(HERE, "routing_gold_review.csv")

gate = CapabilityGate()
cases = [json.loads(l) for l in open(CASES, encoding="utf-8") if l.strip()]
gold = {r["case_id"]: r for r in csv.DictReader(open(GOLD, encoding="utf-8-sig"))}

compound = [c for c in cases if c["category"] == "复合任务"]

print(f"复合任务 {len(compound)} 条\n")
rescued = 0
for c in compound:
    cid = c["case_id"]
    msg = c["message"]
    whole = gate.decide(msg).kind.value
    parts = detect_compound_order(msg)
    sub_kinds = []
    if parts:
        for p in parts:
            sub_kinds.append(gate.decide(p).kind.value)
    g = gold[cid]
    gold_intents = g["gold_intents"]
    # 子句级识别出 ≥2 个不同能力 = 救回第二诉求
    distinct = len(set(sub_kinds))
    rescued_flag = distinct >= 2
    if rescued_flag:
        rescued += 1
    print(f"{cid} 整体={whole} 子句={sub_kinds} distinct={distinct} 救回={rescued_flag} | gold={gold_intents} | {msg[:26]}")

print(f"\n子句级能识别≥2能力（救回诉求）: {rescued}/{len(compound)}")
