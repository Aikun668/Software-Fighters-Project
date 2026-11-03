"""FINAL 总对照：旧路由 vs 全启用新路由（t4a+t4b on，mock 语义腿离线可复现）。

按 master plan FINAL 第 2 步六分类统计误触发/漏判：
  明确产物 / 普通答疑 / 否定表达 / 复合任务 / 多轮指代 / 需澄清

输出口径：
  - old：旧路由（T0 行为）
  - new：新路由（T4-A 三态 + T4-B 复合/指代 + T4-C 8类意图，全启用）
  - gold：已确认 gold_capability（非"待裁决/待澄清"的才判对错）

只统计、不裁决；gold 确认状态在报告里如实标注。
"""
import asyncio
import csv
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
AI_SERVICE = os.path.abspath(os.path.join(HERE, "..", "..", "..", "ai-service"))
sys.path.insert(0, AI_SERVICE)

from app.centers.chat_center import ChatCenter  # noqa: E402
from app.services.intent_extractor import IntentExtractor  # noqa: E402
from app.services.capability_map import INTENT_CENTER_MAP  # noqa: E402

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(AI_SERVICE, ".env"))

CASES = os.path.join(HERE, "routing_cases.jsonl")
GOLD = os.path.join(HERE, "routing_gold_review.csv")
OUT = os.path.join(HERE, "routing_final_compare.csv")

# 全启用新路由 + 真模型语义腿（生产真实状态；mock 腿与旧路由同源、会失真）
_new_center = ChatCenter(
    t4a_enabled=True,
    t4b_enabled=True,
    semantic_extractor=IntentExtractor(use_mock=False),
)


def load_cases():
    with open(CASES, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def load_gold():
    with open(GOLD, encoding="utf-8-sig") as fh:
        return {r["case_id"]: r for r in csv.DictReader(fh)}


def build_ctx(history, message):
    msgs = list(history or []) + [{"role": "user", "content": message}]
    return {"messages": msgs, "style": "standard", "images": [],
            "user_id": 0, "conversation_id": None}


# category → master plan 六分类
CATEGORY_TO_CLASS = {
    "普通概念答疑": "普通答疑",
    "明确生成练习题": "明确产物",
    "明确生成学习资源": "明确产物",
    "学习规划": "明确产物",
    "可视化": "明确产物",
    "解答已有题目": "明确产物",
    "隐式需求非标准表达": "明确产物",
    "诊断与画像相关": "明确产物",
    "复合任务": "复合任务",
    "多轮上下文与指代": "多轮指代",
    "否定表达引用内容干扰": "否定表达",
    "空输入模糊请求缺少参数": "需澄清",
}


async def run_new(message, history):
    plan = await _new_center.route(
        message=message, mode="auto", context=build_ctx(history, message)
    )
    # 最终 center（task.mode），不是 intent —— 这才是「路由到哪」的正确口径
    modes = [t.mode for t in plan.tasks]
    return modes


async def main():
    cases = load_cases()
    gold = load_gold()

    from collections import Counter, defaultdict

    stats = defaultdict(lambda: Counter())  # 分类 -> {old_hit, old_miss, new_hit, new_miss}
    rows = []

    for c in cases:
        cid = c["case_id"]
        g = gold[cid]
        gold_cap = g["gold_capability"]
        if gold_cap in ("待裁决", "待澄清"):
            continue  # 无法判对错

        new_modes = await run_new(c["message"], c.get("history") or [])
        klass = CATEGORY_TO_CLASS.get(c["category"], c["category"])

        rows.append({
            "case_id": cid,
            "category": c["category"],
            "class": klass,
            "gold_capability": gold_cap,
            "gold_intents": g["gold_intents"],
            "new_modes": "|".join(new_modes),
        })

    # 旧路由从 sidecar 补
    side = {}
    for l in open(os.path.join(HERE, "routing_t4a_sidecar.jsonl"), encoding="utf-8"):
        l = l.strip()
        if not l:
            continue
        r = json.loads(l)
        side[r["case_id"]] = r

    # route → center 映射（旧 route 是 KIND 名，如 NORMAL_CHAT/EXERCISE/...）
    def route_to_center(route):
        return {
            "NORMAL_CHAT": "auto",
            "EXERCISE": "exercise",
            "RESOURCE": "resource",
            "PLAN": "plan",
            "VISUALIZATION": "visualization",
        }.get(route, route)

    def gold_target_centers(gold_cap, gold_intents):
        """gold 的目标 center 集合：优先 gold_intents 各意图，兜底 gold_capability。"""
        gi = gold_intents.split("|") if gold_intents else []
        centers = set()
        for i in gi:
            if i in INTENT_CENTER_MAP:
                centers.add(INTENT_CENTER_MAP[i])
        if not centers and gold_cap in (
            "NORMAL_CHAT", "EXERCISE", "RESOURCE", "PLAN", "VISUALIZATION"
        ):
            centers.add(route_to_center(gold_cap))
        return centers

    for r in rows:
        cid = r["case_id"]
        klass = r["class"]
        old = side[cid]["old"]
        old_center = route_to_center(old["route"])
        new_centers = set((r["new_modes"] or "").split("|")) if r["new_modes"] else set()
        gold_centers = gold_target_centers(r["gold_capability"], r["gold_intents"])

        old_hit = old_center in gold_centers
        new_hit = bool(new_centers & gold_centers)
        r["old_hit"] = old_hit
        r["new_hit"] = new_hit
        stats[klass]["old_hit" if old_hit else "old_miss"] += 1
        stats[klass]["new_hit" if new_hit else "new_miss"] += 1

    # 输出 CSV
    cols = ["case_id", "category", "class", "gold_capability", "gold_intents",
            "new_modes", "old_hit", "new_hit"]
    with open(OUT, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    print(f"rows(可判对错)={len(rows)} -> {OUT}\n")
    print(f"{'分类':<12} {'旧命中':>6} {'旧漏':>5} {'新命中':>6} {'新漏':>5}")
    total = Counter()
    for klass in sorted(stats):
        s = stats[klass]
        oh, om, nh, nm = s["old_hit"], s["old_miss"], s["new_hit"], s["new_miss"]
        total["oh"] += oh; total["om"] += om; total["nh"] += nh; total["nm"] += nm
        print(f"{klass:<12} {oh:>6} {om:>5} {nh:>6} {nm:>5}")
    print("-" * 44)
    print(f"{'合计':<12} {total['oh']:>6} {total['om']:>5} {total['nh']:>6} {total['nm']:>5}")


asyncio.run(main())
