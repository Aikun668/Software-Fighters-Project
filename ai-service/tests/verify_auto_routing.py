"""验证 auto 模式自动路由 — 10 个梯度用例，HTTP 轰炸，解析 SSE 流。

验收标准:
  1. auto 能自动路由到 plan/resource/exercise/visualization 四个 Center
  2. 路由模糊时 LLM 输出 inquiry 确认事件
  3. 手动 mode 跳过 LLM，直走对应 Center

输出: 10 行表格，包含输入→提取意图→路由 Center→判定结果
"""
import asyncio
import json
import sys
import os
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import httpx

BASE = "http://localhost:8100/internal"

# ═══════════════════════════════════════════════════════════════════
# 10 个测试用例（简单→复杂→模糊）
# ═══════════════════════════════════════════════════════════════════
TEST_CASES = [
    # ── 简单：单意图 ──
    {
        "id": 1, "level": "简单", "mode": "auto",
        "message": "什么是机器学习？",
        "expect_center": "auto",
        "expect_intent": "tutor_question",
    },
    {
        "id": 2, "level": "简单", "mode": "auto",
        "message": "帮我解这道题：求 f(x)=x²+3x 的导数",
        "expect_center": "auto",
        "expect_intent": "solve_problem",
    },
    {
        "id": 3, "level": "简单", "mode": "auto",
        "message": "给我出 5 道 Python 练习题",
        "expect_center": "exercise",
        "expect_intent": "exercise_gen",
    },
    {
        "id": 4, "level": "简单", "mode": "auto",
        "message": "画一张神经网络结构图",
        "expect_center": "visualization",
        "expect_intent": "visualize",
    },
    # ── 中等：明确需求 ──
    {
        "id": 5, "level": "中等", "mode": "auto",
        "message": "生成机器学习的学习资源，要包含代码示例",
        "expect_center": "resource",
        "expect_intent": "resource_gen",
    },
    {
        "id": 6, "level": "中等", "mode": "auto",
        "message": "帮我规划学习 Python 面向对象编程的路线",
        "expect_center": "plan",
        "expect_intent": "learning_path",
    },
    {
        "id": 7, "level": "中等", "mode": "auto",
        "message": "我想诊断一下我的算法基础怎么样",
        "expect_center": "auto",
        "expect_intent": "diagnose",
    },
    # ── 复杂：多意图混合 ──
    {
        "id": 8, "level": "复杂", "mode": "auto",
        "message": "什么是梯度下降？用图表示一下，再出两道题练手",
        "expect_center": "multi",
        "expect_intent": "multi(explain+visualize+exercise)",
    },
    {
        "id": 9, "level": "复杂", "mode": "auto",
        "message": "分析一下我的薄弱点，然后推荐学习资料，最后出几道题检验",
        "expect_center": "multi",
        "expect_intent": "multi(diagnose+resource+exercise)",
    },
    # ── 模糊：触发 ResourceCenter 的 inquiry 检查 ──
    {
        "id": 10, "level": "模糊", "mode": "auto",
        "message": "给我生成一些资料",
        "expect_center": "inquiry",
        "expect_intent": "inquiry(模糊触发确认)",
    },
]

# ═══════════════════════════════════════════════════════════════════
# 手动 mode 冒烟测试（不走 LLM，直走对应 Center）
# ═══════════════════════════════════════════════════════════════════
MANUAL_MODE_TESTS = [
    ("plan", "帮我规划学习路线"),
    ("resource", "生成神经网络学习资料"),
    ("exercise", "出 3 道算法题"),
    ("visualization", "画知识图谱"),
]


async def run_one(client: httpx.AsyncClient, tc: dict) -> dict:
    """发送一个 unified chat 请求，解析 SSE 流，提取路由信息。"""
    result = {
        "id": tc["id"],
        "level": tc["level"],
        "message": tc["message"],
        "mode": tc["mode"],
        "expect_center": tc["expect_center"],
        "expect_intent": tc["expect_intent"],
        "actual_centers": [],
        "actual_intents": [],
        "has_inquiry": False,
        "has_done": False,
        "error": None,
    }
    try:
        async with client.stream(
            "POST",
            f"{BASE}/api/chat",
            json={
                "message": tc["message"],
                "mode": tc["mode"],
                "user_id": 1,
                "messages": [],
                "student_profile": {},
            },
            timeout=120.0,
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type", "")
                    stage = event.get("stage", "")
                    intent = event.get("data", {}).get("intent", "") if isinstance(event.get("data"), dict) else ""

                    # 中心开始事件
                    if event_type == "center_start":
                        result["actual_centers"].append(stage)

                    # 从 content 事件提取 intent_meta
                    if isinstance(event.get("data"), dict):
                        meta = event["data"].get("intent_meta", {})
                        if meta.get("intents"):
                            result["actual_intents"] = meta["intents"]

                    # inquiry 事件（模糊触发）
                    if event_type == "inquiry":
                        result["has_inquiry"] = True

                    # results 中也可能包含 intent
                    if isinstance(event.get("data"), dict):
                        results = event["data"].get("results", [])
                        for r in results:
                            if r.get("intent"):
                                result["actual_intents"].append(r["intent"])

                    if event_type == "done":
                        result["has_done"] = True
                        break
    except Exception as e:
        result["error"] = str(e)[:120]

    return result


async def run_manual_mode(client: httpx.AsyncClient, mode: str, message: str) -> dict:
    """手动 mode — 应该跳过 LLM 提取，直走对应 Center。"""
    result = {"mode": mode, "message": message, "centers": [], "has_inquiry": False, "error": None}
    try:
        async with client.stream(
            "POST",
            f"{BASE}/api/chat",
            json={
                "message": message,
                "mode": mode,
                "user_id": 1,
                "messages": [],
                "student_profile": {},
            },
            timeout=120.0,
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "center_start":
                        result["centers"].append(event.get("stage", ""))
                    if event.get("type") == "inquiry":
                        result["has_inquiry"] = True
                    if event.get("type") == "done":
                        break
    except Exception as e:
        result["error"] = str(e)[:120]
    return result


def check_pass(r: dict) -> bool:
    """判定路由是否正确。"""
    if r["error"]:
        return False

    actual = set(r["actual_centers"])
    expected = r["expect_center"]

    # inquiry 类
    if expected == "inquiry":
        return r["has_inquiry"]

    # multi 类：至少有 2 个 center 被触发
    if expected == "multi":
        return len(actual) >= 2

    # 单 intent 类
    return expected in actual


async def main():
    print("=" * 90)
    print("  Auto 模式自动路由验证 — 10 梯度用例")
    print("=" * 90)

    results = []
    async with httpx.AsyncClient(trust_env=False) as client:
        for tc in TEST_CASES:
            marker = f"[{tc['id']:2d}]"
            sys.stdout.write(f"  {marker} {tc['level']:4s} | {tc['message'][:50]}... ")
            sys.stdout.flush()
            r = await run_one(client, tc)
            passed = check_pass(r)
            r["passed"] = passed
            results.append(r)
            print("[PASS]" if passed else "[FAIL]")

    # ── 打印路由结果表格 ──
    print("\n" + "=" * 110)
    print("  Auto 模式路由结果总表")
    print("=" * 110)
    header = f"  {'#':<3} {'难度':<5} {'输入':<40} {'期望路由':<18} {'实际路由(stage)':<22} {'实际意图':<25} {'结果':<6}"
    print(header)
    print("  " + "-" * 108)
    for r in results:
        actual_centers = ", ".join(r["actual_centers"]) if r["actual_centers"] else "(none)"
        actual_intents = ", ".join(r["actual_intents"]) if r["actual_intents"] else "(LLM未返回)"
        # Truncate for display
        actual_centers = actual_centers[:20] + "..." if len(actual_centers) > 22 else actual_centers
        actual_intents = actual_intents[:22] + "..." if len(actual_intents) > 25 else actual_intents
        msg = r["message"][:37] + "..." if len(r["message"]) > 38 else r["message"]
        status = "[PASS]" if r["passed"] else "[FAIL]"

        row = f"  {r['id']:<3} {r['level']:<5} {msg:<40} {r['expect_center']:<18} {actual_centers:<22} {actual_intents:<25} {status:<6}"
        print(row)

        # 失败时打印详情
        if not r["passed"] and r["error"]:
            print(f"    └─ ERROR: {r['error']}")
        if not r["passed"] and not r["error"] and not r["has_done"]:
            print(f"    └─ 未收到 DONE 事件")
        if r["has_inquiry"] and r["expect_center"] != "inquiry":
            print(f"    └─ ⚠ 触发了 inquiry（可能路由模糊）")

    # ── 打印 LLM 提取详情 ──
    print("\n" + "=" * 110)
    print("  LLM 意图提取详情（每个用例的 intent + confidence + params）")
    print("=" * 110)
    for r in results:
        print(f"  [{r['id']:2d}] \"{r['message']}\"")
        if r["actual_intents"]:
            for intent in r["actual_intents"]:
                print(f"       意图: {intent}")
        else:
            print(f"       意图: (未从SSE中解析到，可能是 inquiry 或 single task)")
        if r["has_inquiry"]:
            print(f"       触发 inquiry: 是（路由模糊，LLM 要求确认）")
        print(f"       路由到 Center: {r['actual_centers'] or '(none)'}")
        if r["error"]:
            print(f"       错误: {r['error']}")
        print()

    # ── 手动 mode 冒烟 ──
    print("=" * 90)
    print("  手动 Mode 冒烟（跳过 LLM，直走对应 Center）")
    print("=" * 90)
    async with httpx.AsyncClient(trust_env=False) as client:
        for mode, msg in MANUAL_MODE_TESTS:
            sys.stdout.write(f"  mode={mode:15s} | {msg[:50]}... ")
            sys.stdout.flush()
            r = await run_manual_mode(client, mode, msg)
            expected = {"plan": "plan", "resource": "resource", "exercise": "exercise", "visualization": "visualization"}
            center_pass = expected.get(mode, "") in r["centers"]
            print(f"center={r['centers']} {'[PASS]' if center_pass else '[FAIL]'}")

    # ── 总结 ──
    print("\n" + "=" * 90)
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    print(f"  Auto 路由: {passed}/{len(results)} 通过, {failed}/{len(results)} 失败")
    print("=" * 90)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
