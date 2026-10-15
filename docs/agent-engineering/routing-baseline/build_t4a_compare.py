"""T4-A 对照表生成：sidecar（旧行为 + 三态旁路）JOIN Gold Label。

产出 routing_t4a_compare.csv，列：
  case_id / category / message / gold_capability / gold_intents /
  gold_ask_clarify / gold_status / 旧route / 旧intents /
  semantic_state / route_source / semantic_intents / semantic_is_clear /
  是否误触发（规则直通却与 gold 不符） / 是否漏判（gold 明确能力却走了语义）

只做**统计**，不裁决：gold_status 仍以 CSV 为准，reviewer_decision 未被改动。
"""
import csv
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
SIDECAR = os.path.join(HERE, "routing_t4a_sidecar.jsonl")
GOLD = os.path.join(HERE, "routing_gold_review.csv")
OUT = os.path.join(HERE, "routing_t4a_compare.csv")

# 旧 route 与 gold_capability 的对应关系
ROUTE_TO_GOLD = {
    "NORMAL_CHAT": "NORMAL_CHAT",
    "EXERCISE": "EXERCISE",
    "RESOURCE": "RESOURCE",
    "PLAN": "PLAN",
    "VISUALIZATION": "VISUALIZATION",
}


def load_sidecar():
    rows = {}
    with open(SIDECAR, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            rows[r["case_id"]] = r
    return rows


def load_gold():
    with open(GOLD, encoding="utf-8-sig") as fh:
        return {row["case_id"]: row for row in csv.DictReader(fh)}


def main():
    side = load_sidecar()
    gold = load_gold()

    columns = [
        "case_id", "category", "message", "mode",
        "gold_capability", "gold_intents", "gold_ask_clarify", "gold_status",
        "old_route", "old_intents",
        "semantic_state", "route_source", "semantic_called",
        "semantic_intents", "semantic_is_clear", "semantic_error",
    ]
    rows = []
    for cid in sorted(side, key=lambda c: int(c[1:])):
        s = side[cid]
        g = gold[cid]
        t4a = s["t4a"]
        old = s["old"]
        rows.append({
            "case_id": cid,
            "category": s["category"],
            "message": s["message"],
            "mode": s["mode"],
            "gold_capability": g["gold_capability"],
            "gold_intents": g["gold_intents"],
            "gold_ask_clarify": g["gold_ask_clarify"],
            "gold_status": g["gold_status"],
            "old_route": old["route"],
            "old_intents": "|".join(old["intents"]),
            "semantic_state": t4a["semantic_state"],
            "route_source": t4a["route_source"],
            "semantic_called": t4a["semantic_called"],
            "semantic_intents": "|".join(t4a["semantic_intents"] or []),
            "semantic_is_clear": t4a["semantic_is_clear"],
            "semantic_error": t4a["semantic_error"],
        })

    with open(OUT, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)

    # 统计
    from collections import Counter

    states = Counter(r["semantic_state"] for r in rows)
    print(f"rows={len(rows)} -> {OUT}")
    print("\n三态分布:", dict(states))

    # 关键统计：旧行为 vs gold（DRAFT_CONFIRMED 才可严格判对错）
    drafted = [r for r in rows if r["gold_status"] == "DRAFT_CONFIRMED"]
    print(f"\nDRAFT_CONFIRMED={len(drafted)} 条（可严格对错）")

    # 旧行为直接命中 gold_capability 的比例
    def old_hits_gold(r):
        gold_cap = r["gold_capability"]
        if gold_cap in ("待裁决", "待澄清"):
            return None  # 无法判定
        return r["old_route"] == gold_cap

    hit = [r for r in drafted if old_hits_gold(r) is True]
    miss = [r for r in drafted if old_hits_gold(r) is False]
    print(f"  旧行为命中 gold: {len(hit)} / 未命中: {len(miss)}")

    print("\n旧行为未命中 gold 的 DRAFT_CONFIRMED 样例（这是 T4-A 要改善的目标）:")
    for r in miss[:20]:
        print(f"  {r['case_id']} gold={r['gold_capability']:>14} 旧={r['old_route']:>14} 三态={r['semantic_state']:>18} | {r['message'][:30]}")

    # 三态 = uncertain 的 DRAFT_CONFIRMED（说明语义腿有机会纠正）
    unc_drafted = [r for r in drafted if r["semantic_state"] == "uncertain"]
    print(f"\nDRAFT_CONFIRMED 中判为 uncertain 的 {len(unc_drafted)} 条（语义腿介入机会）")


if __name__ == "__main__":
    main()
