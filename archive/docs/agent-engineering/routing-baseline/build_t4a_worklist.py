"""生成 58 条 POLICY_UNDECIDED 的人工裁决工作单（CSV，可直接编辑）。

只做整理、不裁决：把 gold CSV 里 58 条待裁决行抽出，附上旁路侧车里的
旧路由行为与三态判定两列，reviewer_decision 留空等人工填。

输出：routing_t4a_undecided_worklist.csv（UTF-8-BOM，Excel 可直接打开填列）
"""
import csv
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
GOLD = os.path.join(HERE, "routing_gold_review.csv")
SIDE = os.path.join(HERE, "routing_t4a_sidecar.jsonl")
OUT = os.path.join(HERE, "routing_t4a_undecided_worklist.csv")

COLUMNS = [
    "case_id", "category", "message", "mode",
    "gold_capability", "gold_intents", "gold_task_order", "gold_ask_clarify",
    "gold_reason", "old_route", "semantic_state", "reviewer_decision",
]


def main():
    gold = {}
    with open(GOLD, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            gold[r["case_id"]] = r

    side = {}
    with open(SIDE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            side[r["case_id"]] = r

    undec = [cid for cid, r in gold.items() if r["gold_status"] == "POLICY_UNDECIDED"]
    undec.sort(key=lambda c: int(c[1:]))

    rows = []
    for cid in undec:
        r = gold[cid]
        s = side[cid]
        rows.append({
            "case_id": cid,
            "category": r["category"],
            "message": r["message"],
            "mode": r["mode"],
            "gold_capability": r["gold_capability"],
            "gold_intents": r["gold_intents"],
            "gold_task_order": r["gold_task_order"],
            "gold_ask_clarify": r["gold_ask_clarify"],
            "gold_reason": r["gold_reason"],
            "old_route": s["old"]["route"] or "",
            "semantic_state": s["t4a"]["semantic_state"],
            "reviewer_decision": "",
        })

    with open(OUT, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)

    print(f"rows={len(rows)} -> {OUT}")
    print("列：case_id / category / message / mode / gold_capability / gold_intents /")
    print("     gold_task_order / gold_ask_clarify / gold_reason / old_route /")
    print("     semantic_state / reviewer_decision（待填）")


if __name__ == "__main__":
    main()
