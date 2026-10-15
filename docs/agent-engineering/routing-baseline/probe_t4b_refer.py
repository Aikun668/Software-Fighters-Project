"""多轮指代消解探针：检测当前消息是指代 + history 上轮意图，看"复用上轮意图"能否消解。

策略：当前消息含指代词（再来/再画/改成/换/调/还有/展开/难度/反过来/加/整理/详细），
且 history 有上一轮 user 消息 → 复用上轮 user 消息的意图（用 router.decide 判上轮意图）。
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "ai-service")))

from app.centers.router_agent import RouterAgent  # noqa: E402
from app.services.intent_extractor import IntentExtractor  # noqa: E402

CASES = os.path.join(HERE, "routing_cases.jsonl")
GOLD = os.path.join(HERE, "routing_gold_review.csv")

router = RouterAgent(intent_extractor=IntentExtractor(use_mock=True))
cases = [json.loads(l) for l in open(CASES, encoding="utf-8") if l.strip()]
gold = {r["case_id"]: r for r in csv.DictReader(open(GOLD, encoding="utf-8-sig"))}

REFER_MARKS = ("再来", "再画", "改成", "换成", "调高", "调低", "还有", "展开", "反过来",
               "加个", "整理成", "详细", "配套", "难度", "补哪块", "举个例子", "别的", "代码实现")

multi = [c for c in cases if c.get("history")]
print(f"多轮指代 {len(multi)} 条\n")

rescued = 0
for c in multi:
    cid = c["case_id"]
    msg = c["message"]
    is_refer = any(m in msg for m in REFER_MARKS)
    # 上一轮 user 消息
    prev_user = next((h["content"] for h in reversed(c["history"]) if h["role"] == "user"), "")
    prev_intents = [ca.intent for ca in router.decide(prev_user).candidates] if prev_user else []
    g = gold[cid]
    gold_intents = g["gold_intents"].split("|")
    ok = is_refer and bool(prev_intents) and prev_intents[0] in gold_intents
    if ok:
        rescued += 1
    print(f"{cid} 指代={is_refer} 上轮意图={prev_intents} gold={gold_intents[:2]} 复用可救={ok} | {msg[:20]}")

print(f"\n复用上轮意图可消解: {rescued}/{len(multi)}")
