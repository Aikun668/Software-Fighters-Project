"""两层路由验证 — 20 个梯度用例，HTTP SSE 流解析。

第一层（AutoCenter 子 Agent 路由）：10 用例，验证 auto 模式下正确 dispatch 到
  TutorAgent / SolveAgent / DiagnoseAgent / ProfileAgent。

第二层（ResourceCenter Director 路由）：10 用例，验证 resource 模式下 Director 正确
  路由到 content / code / mindmap / flashcard / project / interactive_diagram 及 inquiry。

验收标准:
  1. AutoCenter 子 Agent 名与预期一致
  2. ResourceCenter Director 选中的内部 agent 名与预期一致
  3. 模糊输入触发 inquiry 事件

输出: 20 行表格，输入→预期 agent→实际 agent→判定
"""
import asyncio
import json
import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import httpx

BASE = "http://localhost:8100/internal"

# ═══════════════════════════════════════════════════════════════════
# 第一层: AutoCenter 子 Agent 路由 — 10 用例（难度均匀分布）
# ═══════════════════════════════════════════════════════════════════
AUTO_AGENT_TESTS = [
    # ── 简单: 明确单意图 ──
    {
        "id": 1, "level": "简单",
        "message": "什么是梯度下降？",
        "mode": "auto",
        "expect_agent": "TutorAgent",
    },
    {
        "id": 2, "level": "简单",
        "message": "求 f(x)=sin(x)cos(x) 的导数，给出完整步骤",
        "mode": "auto",
        "expect_agent": "SolveAgent",
    },
    {
        "id": 3, "level": "简单",
        "message": "我是编程小白，完全零基础，想入行AI",
        "mode": "auto",
        "expect_agent": "ProfileAgent",
    },
    {
        "id": 4, "level": "简单",
        "message": "帮我诊断一下我的 Python 水平，看看薄弱点在哪",
        "mode": "auto",
        "expect_agent": "DiagnoseAgent",
    },
    # ── 中等: 有明确关键词但表达较自然 ──
    {
        "id": 5, "level": "中等",
        "message": "解释一下 Transformer 多头注意力的工作原理",
        "mode": "auto",
        "expect_agent": "TutorAgent",
    },
    {
        "id": 6, "level": "中等",
        "message": "解这个方程: x³ - 6x² + 11x - 6 = 0，分步展示",
        "mode": "auto",
        "expect_agent": "SolveAgent",
    },
    {
        "id": 7, "level": "中等",
        "message": "帮我诊断一下我的数据结构和编程功底怎么样，想知道薄弱环节",
        "mode": "auto",
        "expect_agent": "DiagnoseAgent",
    },
    {
        "id": 8, "level": "中等",
        "message": "我刚学完 Python 基础，接下来该怎么进阶？",
        "mode": "auto",
        "expect_agent": "TutorAgent",
    },
    # ── 复杂: 多意图混合，依赖 LLM 判断 ──
    {
        "id": 9, "level": "复杂",
        "message": "我第一次接触机器学习，帮我规划一下入门需要掌握哪些数学知识",
        "mode": "auto",
        "expect_agent": "ProfileAgent",  # 先建立画像
    },
    {
        "id": 10, "level": "复杂",
        "message": "什么是过拟合？怎么解决？然后诊断一下我的模型训练问题",
        "mode": "auto",
        "expect_agent": "TutorAgent",  # mutex: diagnose vs tutor_question → tutor wins (higher keyword confidence)
    },
]

# ═══════════════════════════════════════════════════════════════════
# 第二层: ResourceCenter Director 路由 — 10 用例（难度均匀分布）
# ═══════════════════════════════════════════════════════════════════
RESOURCE_DIRECTOR_TESTS = [
    # ── 简单: 明确的资源类型 ──
    {
        "id": 11, "level": "简单",
        "message": "生成一套 Python 入门学习教程文档",
        "mode": "resource",
        "expect_agent": "content",
    },
    {
        "id": 12, "level": "简单",
        "message": "写一个快速排序的完整代码实现",
        "mode": "resource",
        "expect_agent": "code",
    },
    {
        "id": 13, "level": "简单",
        "message": "画一张机器学习算法分类的思维导图",
        "mode": "resource",
        "expect_agent": "mindmap",
    },
    {
        "id": 14, "level": "简单",
        "message": "生成50个深度学习核心术语的记忆闪卡",
        "mode": "resource",
        "expect_agent": "flashcard",
    },
    # ── 中等: 需要 Director 做 rule/LLM 判断 ──
    {
        "id": 15, "level": "中等",
        "message": "给我一个 MNIST 手写数字识别的练手小项目",
        "mode": "resource",
        "expect_agent": "project",
    },
    {
        "id": 16, "level": "中等",
        "message": "做一个神经网络前向传播过程的可视化演示",
        "mode": "resource",
        "expect_agent": "interactive_diagram",
    },
    {
        "id": 17, "level": "中等",
        "message": "全面对比 CNN 和 Transformer 的优缺点和适用场景",
        "mode": "resource",
        "expect_agent": "content",  # comparison sub_type
    },
    {
        "id": 18, "level": "中等",
        "message": "模型训练时梯度爆炸了，帮我排查修复",
        "mode": "resource",
        "expect_agent": "code",  # diagnosis sub_type
    },
    # ── 复杂 + 模糊 ──
    {
        "id": 19, "level": "复杂",
        "message": "我要系统入门强化学习，从基础概念到代码示例，整理一套完整的学习文档",
        "mode": "resource",
        "expect_agent": "content",  # 模糊 → 兜底 content
    },
    {
        "id": 20, "level": "模糊",
        "message": "给我生成一些资料",
        "mode": "resource",
        "expect_agent": "inquiry",  # 太模糊 → inquiry
    },
]


async def run_one(client: httpx.AsyncClient, tc: dict) -> dict:
    """发送 unified chat，解析 SSE 流，提取 agent 信息。"""
    result = {
        "id": tc["id"],
        "level": tc["level"],
        "message": tc["message"],
        "mode": tc["mode"],
        "expect_agent": tc["expect_agent"],
        "actual_agents": [],
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
            timeout=180.0,
        ) as response:
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type", "")

                if event_type == "inquiry":
                    result["has_inquiry"] = True

                if event_type == "done":
                    result["has_done"] = True
                    data = event.get("data", {})
                    # 从 results[] 提取 agent 名
                    for r in (data.get("results") or []):
                        agent = r.get("agent", "")
                        if agent:
                            result["actual_agents"].append(agent)
                    break
    except Exception as e:
        result["error"] = str(e)[:120]

    return result


def check_pass(r: dict) -> bool:
    """判定路由结果。"""
    if r["error"]:
        return False

    expected = r["expect_agent"]
    actual_agents = r["actual_agents"]

    # inquiry 类
    if expected == "inquiry":
        return r["has_inquiry"]

    # 提取 ResourceCenter 内部 agent 名
    if expected in ("content", "code", "mindmap", "flashcard",
                    "project", "interactive_diagram"):
        for a in actual_agents:
            inner = a.split("/")[-1] if "/" in a else ""
            if inner == expected:
                return True
        return False

    # AutoCenter: 直接匹配 agent 名
    return any(expected in a for a in actual_agents)


async def main():
    print("=" * 100)
    print("  两层子 Agent 路由验证 — 20 梯度用例（AutoCenter 10 + ResourceCenter 10）")
    print("=" * 100)

    results: list[dict] = []
    async with httpx.AsyncClient(trust_env=False) as client:
        for tc in AUTO_AGENT_TESTS + RESOURCE_DIRECTOR_TESTS:
            marker = f"[{tc['id']:2d}]"
            section = "Auto" if tc["id"] <= 10 else "Res"
            sys.stdout.write(
                f"  {marker} [{section}] {tc['level']:4s} | {tc['message'][:50]}... "
            )
            sys.stdout.flush()
            r = await run_one(client, tc)
            passed = check_pass(r)
            r["passed"] = passed
            results.append(r)
            print("[PASS]" if passed else "[FAIL]")

    # ── 结果表格 ──
    print("\n" + "=" * 120)
    print("  路由结果总表")
    print("=" * 120)
    header = (
        f"  {'#':<3} {'层':<5} {'难度':<5} {'输入':<40} "
        f"{'预期 Agent':<28} {'实际 Agent':<28} {'结果':<6}"
    )
    print(header)
    print("  " + "-" * 118)
    for r in results:
        section = "Auto" if r["id"] <= 10 else "Res"
        actual_str = ", ".join(r["actual_agents"]) if r["actual_agents"] else "(none)"
        actual_str = actual_str[:26] + ".." if len(actual_str) > 28 else actual_str
        msg = r["message"][:37] + "..." if len(r["message"]) > 38 else r["message"]
        status = "[PASS]" if r["passed"] else "[FAIL]"

        expect = r["expect_agent"]
        if r["id"] > 10:
            expect = f"ResourceGenWorkflow/{expect}"

        row = (
            f"  {r['id']:<3} {section:<5} {r['level']:<5} {msg:<40} "
            f"{expect:<28} {actual_str:<28} {status:<6}"
        )
        print(row)

        if not r["passed"]:
            if r["error"]:
                print(f"    └─ ERROR: {r['error']}")
            elif r["has_inquiry"] and r["expect_agent"] != "inquiry":
                print(f"    └─ 意外触发了 inquiry（路由模糊）")
            elif not r["has_done"]:
                print(f"    └─ 未收到 DONE 事件")
            else:
                print(f"    └─ Agent 不匹配: 预期 {r['expect_agent']}, 实际 {r['actual_agents']}")

    # ── 按层统计 ──
    auto_results = [r for r in results if r["id"] <= 10]
    res_results = [r for r in results if r["id"] > 10]

    print("\n" + "=" * 100)
    print("  统计")
    print("=" * 100)

    def stat(label: str, items: list[dict]):
        passed = sum(1 for r in items if r["passed"])
        failed = sum(1 for r in items if not r["passed"])
        print(f"  {label}: {passed}/{len(items)} 通过, {failed}/{len(items)} 失败")
        for r in items:
            if not r["passed"]:
                print(f"    失败 #{r['id']}: \"{r['message'][:60]}\"")
                if r["actual_agents"]:
                    print(f"      实际路由: {r['actual_agents']}")
                if r["error"]:
                    print(f"      错误: {r['error']}")

    stat("AutoCenter 子 Agent", auto_results)
    stat("ResourceCenter Director", res_results)

    total_passed = sum(1 for r in results if r["passed"])
    total_failed = sum(1 for r in results if not r["passed"])
    print(f"\n  总计: {total_passed}/{len(results)} 通过, {total_failed}/{len(results)} 失败")

    print("=" * 100)
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
