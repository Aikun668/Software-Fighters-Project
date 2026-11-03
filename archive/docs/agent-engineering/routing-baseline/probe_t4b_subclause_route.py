"""T4-B 子句级路由探针：完整模拟「切分→每子句 gate+router→按顺序合并」，看能救回多少被吞诉求。

只读，不改任何路由。对 15 条复合任务，输出子句级路由产出的意图序列 vs gold。
"""
import asyncio
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "ai-service")))

from app.services.capability_gate import CapabilityGate, CapabilityKind  # noqa: E402
from app.services.semantic_router import detect_compound_order  # noqa: E402
from app.centers.router_agent import RouterAgent  # noqa: E402
from app.services.intent_extractor import IntentExtractor  # noqa: E402

CASES = os.path.join(HERE, "routing_cases.jsonl")
GOLD = os.path.join(HERE, "routing_gold_review.csv")

gate = CapabilityGate()
router = RouterAgent(intent_extractor=IntentExtractor(use_mock=True))
cases = [json.loads(l) for l in open(CASES, encoding="utf-8") if l.strip()]
gold = {r["case_id"]: r for r in csv.DictReader(open(GOLD, encoding="utf-8-sig"))}


def subclause_intents(subclauses):
    """子句级路由：每子句 gate+router，返回按顺序的意图列表。"""
    intents = []
    for sub in subclauses:
        d = gate.decide(sub)
        if d.kind is CapabilityKind.NORMAL_CHAT:
            intents.append("tutor_question")
        else:
            rd = router.decide(sub)
            for c in rd.candidates:
                intents.append(c.intent)
    # 去重保序
    seen = []
    for i in intents:
        if i not in seen:
            seen.append(i)
    return seen


compound = [c for c in cases if c["category"] == "复合任务"]
print(f"复合任务 {len(compound)} 条\n")

aligned = 0
for c in compound:
    cid = c["case_id"]
    msg = c["message"]
    subs = detect_compound_order(msg)
    if not subs:
        print(f"{cid} 无连接词(切分失败) | gold={gold[cid]['gold_intents']} | {msg[:26]}")
        continue
    intents = subclause_intents(subs)
    g = gold[cid]
    gold_intents = g["gold_intents"].split("|")
    # 对齐：前两个意图与 gold 前两个一致（gold_intents 取去重后的前两个）
    gold2 = gold_intents[:2]
    ok = intents[:2] == gold2
    if ok:
        aligned += 1
    print(f"{cid} 子句级={intents}  gold={gold_intents}  前2对齐={ok} | {msg[:26]}")

print(f"\n子句级路由前2意图对齐 gold: {aligned}/15")
