"""Stage 0.2 · 任务A 只读探针（修订版）：核查 11 条注册意图的可达性。

[只读] 仅调用**真实路由入口** `ChatCenter.route()`，不触发任何生成任务、
不写库、不改代码。可反复运行。

修订原因：初版只调 CapabilityGate.decide + RouterAgent.route，会把
`NORMAL_CHAT` 一律记为 intents=[]。但真实入口 `ChatCenter.route()` 在
NORMAL_CHAT 分支会**直接构造 tutor_question 单任务计划**（chat_center.py:170-195）。
故必须走真实入口，否则 tutor_question 会被误判为不可达。

运行：
    cd ai-service && PYTHONUTF8=1 python ../docs/agent-engineering/routing-baseline/probe_intent_reachability.py
"""
import sys
import os
import asyncio
import io

# Windows 控制台默认 GBK，强制 UTF-8 输出，避免中文乱码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
AI_SERVICE = os.path.abspath(os.path.join(HERE, "..", "..", "..", "ai-service"))
sys.path.insert(0, AI_SERVICE)

from app.centers.chat_center import ChatCenter  # noqa: E402
from app.services.intent_extractor import INTENT_REGISTRY, INTENT_CENTER_MAP  # noqa: E402

REGISTERED = [d.intent for d in INTENT_REGISTRY]

CANDIDATES = {
    "exercise_gen": ["出5道题", "帮我生成练习题", "生成六级填词的题目", "来几道英语选择题"],
    "resource_gen": ["帮我找几个学习资源", "生成一份讲义", "推荐一些学习资料"],
    # code_example 无独立能力规则 → 单靠它必被 gate 判 NORMAL_CHAT。
    # 需叠加一个能触发 RESOURCE 的产物词（教程/文档/讲义/资料）进入二级。
    "code_example": [
        "给我一个代码示例", "写一个Python的例子", "快速排序怎么实现",  # 预期被 gate 拦
        "推荐一些代码示例的教程", "帮我生成代码示例文档", "给我一份代码示例的讲义",
        "整理一下快速排序的代码资料",
    ],
    "tutor_question": ["什么是进程", "TCP为什么需要三次握手", "解释一下什么是过拟合"],
    "learning_path": ["帮我制定一个学习计划", "规划一下我的学习路径", "给我安排一个复习路线"],
    # solve_problem center=auto；且与 exercise_gen 互斥（不可共存）。需走非 EXERCISE 的
    # 能力词（RESOURCE/PLAN）进入二级，并保证该中心也在二级结果里，才不被 gate 兜底覆盖。
    "solve_problem": [
        "帮我解这道题", "求解这个方程", "推导一下这个公式",  # 预期被 gate 拦
        "帮我解这道计算题，另外生成一份讲义",
        "帮我解这道题并制定一个复习计划",
        "求解这个方程，整理成一份文档",
    ],
    "flashcard_gen": ["帮我生成闪卡", "做几张记忆卡背诵"],
    "visualize": ["画一张TCP三次握手流程图", "帮我做个思维导图", "绘制一个架构图"],
    "knowledge_graph": ["帮我生成知识图谱", "看看我的知识图谱", "展示一下知识图谱"],
    # diagnose center=auto；需 gate 触发 EXERCISE + 二级里 exercise_gen 也在场。
    "diagnose": [
        "帮我做个诊断", "测试一下我的掌握情况", "测一下我哪里薄弱",  # 预期被 gate 拦
        "出几道题测试一下我的掌握",
        "生成几道练习题测试一下我的掌握情况",
        "来一套题检查一下我的水平",
    ],
    # profile_building center=auto；需 gate 触发 PLAN/RESOURCE + 二级里对应中心在场。
    "profile_building": [
        "我是零基础新手", "我的基础比较差，想学AI", "我刚开始学，有点迷茫",  # 预期被 gate 拦
        "我是零基础，帮我制定一个学习计划",
        "我是新手，推荐一些入门资料",
        "我的基础比较差，帮我规划学习路线",
    ],
}

# 显式 mode 候选（≥10 条显式模式样本会在任务B构建，这里只验证门）
MODE_CANDIDATES = {
    "plan": "随便安排点东西",
    "resource": "给我一些材料",
    "exercise": "来一题",
    "visualization": "做个图",
}

center_route = ChatCenter()  # route() 只构造 gate + router，无 LLM/IO


async def probe(message, mode="auto"):
    plan = await center_route.route(message=message, mode=mode)
    meta = plan.intent_meta or {}
    return {
        "strategy": meta.get("strategy"),
        "route": meta.get("route"),
        "route_reason": meta.get("route_reason"),
        "intents": [t.intent for t in plan.tasks],
        "modes": [t.mode for t in plan.tasks],
    }


async def main():
    report = {}
    for intent in REGISTERED:
        rows = []
        for msg in CANDIDATES.get(intent, []):
            r = await probe(msg)
            r["message"] = msg
            r["reaches"] = intent in r["intents"]
            rows.append(r)
        report[intent] = rows

    for intent, rows in report.items():
        hit = any(r["reaches"] for r in rows)
        print(f"\n=== {intent}  [{'REACHABLE' if hit else 'NOT REACHED'}]  center={INTENT_CENTER_MAP.get(intent)}")
        for r in rows:
            mark = "OK " if r["reaches"] else "   "
            print(f"  {mark} {r['message']!r} -> strategy={r['strategy']} "
                  f"route={r['route']} intents={r['intents']} modes={r['modes']}")

    print("\n\n===== SUMMARY (11 注册意图) =====")
    reachable = []
    unreachable = []
    for intent in REGISTERED:
        hit = any(r["reaches"] for r in report[intent])
        (reachable if hit else unreachable).append(intent)
        print(f"{'REACHABLE  ' if hit else 'UNREACHABLE'} {intent}")

    print(f"\nREACHABLE   ({len(reachable)}): {reachable}")
    print(f"UNREACHABLE ({len(unreachable)}): {unreachable}")

    print("\n=== 显式 mode 门验证 ===")
    for mode, msg in MODE_CANDIDATES.items():
        r = await probe(msg, mode=mode)
        print(f"  mode={mode:14} {msg!r} -> strategy={r['strategy']} route={r['route']} "
              f"intents={r['intents']}")

    print("\n=== 未到达目标意图的候选（gate 拦截 / 误路由）===")
    for intent in REGISTERED:
        for r in report[intent]:
            if not r["reaches"]:
                print(f"  target={intent:18} msg={r['message']!r} -> "
                      f"strategy={r['strategy']} intents={r['intents']} ({r['route_reason']})")


asyncio.run(main())
