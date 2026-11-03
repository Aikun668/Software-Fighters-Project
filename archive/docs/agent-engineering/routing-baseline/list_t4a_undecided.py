"""生成 58 条 POLICY_UNDECIDED 的人工裁决清单（按三态分组，含裁决提示）。

只做整理，不裁决：输出 advisory 提示（旧行为 vs gold 草案 vs 三态），
reviewer_decision 字段仍留空等人工填。
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
    print(f"POLICY_UNDECIDED 共 {len(undec)} 条，按三态分组：\n")

    order = ["direct_capability", "direct_chat", "uncertain", "empty"]
    for state in order:
        rows = [
            cid for cid in undec
            if side[cid]["t4a"]["semantic_state"] == state
        ]
        if not rows:
            continue
        print(f"=== {state}（{len(rows)} 条）===")
        for cid in rows:
            r = gold[cid]
            old = side[cid]["old"]["route"] or "(None)"
            print(
                f"  {cid}  旧route={old:>14}  gold_cap={r['gold_capability']:>12}"
                f"  ask_clarify={r['gold_ask_clarify']}  | {r['message'][:26]}"
            )
        print()


if __name__ == "__main__":
    main()
