"""30 全新梯度用例 — 打乱顺序，覆盖所有 Center/Agent + 多意图 + 边界"""
import asyncio
import random
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.centers.router_agent import RouterAgent

# ── 30 道全新用例（难度标签仅用于分组统计）──
CASES = [
    # ═══ 简单 (6): 一句话一个明确意图 ═══
    (1,  "简单", "L1和L2正则化的主要区别是什么？"),
    (2,  "简单", "帮我解这道题：求极限 lim(x→∞) (1+1/x)^x"),
    (3,  "简单", "我现在大二，学过C++和Python，想走AI方向但很迷茫"),
    (4,  "简单", "出5道微积分选择题，要带解析"),
    (5,  "简单", "画一张神经网络的3D结构图"),
    (6,  "简单", "帮我写个快速排序的代码，Python版"),

    # ═══ 中等 (10): 自然表达，部分模糊 ═══
    (7,  "中等", "推荐一些CV方向的经典学习资料"),
    (8,  "中等", "帮我规划学习强化学习的六个月路线"),
    (9,  "中等", "什么是梯度消失，为什么会发生？"),
    (10, "中等", "帮我诊断一下我的算法基础怎么样"),
    (11, "中等", "生成15个机器学习核心术语的闪卡"),
    (12, "中等", "写个用动态规划解背包问题的代码"),
    (13, "中等", "来几道关于决策树的习题"),
    (14, "中等", "画一下数据库索引的B+树结构图"),
    (15, "中等", "我数学基础不太好，想学ML但不知道怎么补"),
    (16, "中等", "我需要一篇CNN发展史的综述文档"),

    # ═══ 复杂 (9): 多意图 / 语境依赖 ═══
    (17, "复杂", "给我解释一下集成学习是什么，再给一段随机森林的代码实现"),
    (18, "复杂", "诊断一下我的线代基础，再规划一个月的补强学习路线"),
    (19, "复杂", "我要学CV，先给学习路径，再出几道图像分类的练习题"),
    (20, "复杂", "请解释一下Adam优化器的原理是什么，画一下它的更新过程，再给个PyTorch实现"),
    (21, "复杂", "帮我评估一下编程能力，推荐针对性的学习资料，再出几道算法题检验"),
    (22, "复杂", "请解释一下监督学习和无监督学习分别是什么有什么区别，再推荐几个练手项目"),
    (23, "复杂", "出几道动态规划题，还要帮我诊断算法代码水平"),
    (24, "复杂", "帮我规划四年的AI学习计划，配套每个阶段的学习资料和练习"),
    (25, "复杂", "画一下图神经网络的示意图，再讲讲消息传递机制是什么"),

    # ═══ 极限 (5): 边界压力 ═══
    (26, "极限", "你能帮我通过明天早八的考试吗"),
    (27, "极限", "AI"),
    (28, "极限", "我要学所有东西"),
    (29, "极限", "出题+画图+写代码+诊断+规划+给资源+做闪卡，一套全要"),
    (30, "极限", "..."),
]

# 固定种子打乱，保证可复现
random.seed(42)
SHUFFLED = list(CASES)
random.shuffle(SHUFFLED)

# 人工标注期望路由
EXPECTED = {
    1:  ["tutor_question"],
    2:  ["solve_problem"],
    3:  ["profile_building"],
    4:  ["exercise_gen"],
    5:  ["visualize"],
    6:  ["code_example"],
    7:  ["resource_gen"],
    8:  ["learning_path"],
    9:  ["tutor_question"],
    10: ["diagnose"],
    11: ["flashcard_gen"],
    12: ["code_example"],
    13: ["exercise_gen"],
    14: ["visualize"],
    15: ["profile_building"],
    16: ["resource_gen"],
    17: ["tutor_question", "code_example"],
    18: ["diagnose", "learning_path"],
    19: ["learning_path", "exercise_gen"],
    20: ["tutor_question", "visualize", "code_example"],
    21: ["diagnose", "resource_gen", "exercise_gen"],
    22: ["tutor_question", "resource_gen"],
    23: ["exercise_gen", "diagnose"],
    24: ["learning_path", "resource_gen", "exercise_gen"],
    25: ["visualize", "tutor_question"],
    26: ["tutor_question"],   # 作弊玩笑 → 兜底
    27: ["tutor_question"],   # 极简单关键词 → 兜底
    28: ["tutor_question"],   # 意图模糊 → 兜底
    29: ["exercise_gen", "visualize", "code_example", "diagnose", "learning_path", "resource_gen", "flashcard_gen"],
    30: ["tutor_question"],   # 放弃提问 → 兜底
}


def check(actual_intents: list[str], expected_intents: list[str]) -> tuple[bool, str]:
    """宽松匹配：实际意图与期望的交集判断"""
    if not actual_intents:
        return False, "无意图"
    primary = actual_intents[0]
    if primary in expected_intents:
        return True, "OK"
    if set(actual_intents) & set(expected_intents):
        return True, "OK(交集)"
    # 兜底 tutor_question 也算通过（无关键词命中场景）
    if primary == "tutor_question" and "tutor_question" in expected_intents:
        return True, "OK(tutor兜底)"
    return False, f"期望{expected_intents} 实际{actual_intents}"


async def main():
    router = RouterAgent()
    results = []

    print("=" * 105)
    print("  30 梯度用例（全新 · 打乱顺序）— 意图路由验证")
    print("=" * 105)

    for cid, difficulty, message in SHUFFLED:
        plan = await router.route(message, mode="auto")
        intents = [t.intent for t in plan.tasks]
        scores = [f"{t.confidence:.2f}" for t in plan.tasks]
        expected = EXPECTED.get(cid, ["?"])
        ok, note = check(intents, expected)
        confirm = " ⚡确认卡" if plan.needs_confirmation else ""

        results.append((cid, difficulty, message, intents, scores, expected, ok, note, plan.needs_confirmation))

        status = "✓" if ok else "✗"
        intent_str = "+".join(intents) if intents else "(none)"
        msg_short = message[:40] + "..." if len(message) > 40 else message
        print(f"  [#{cid:2d}] [{difficulty}] {msg_short:<45} → {intent_str:<40} {status}{confirm}")
        if not ok:
            print(f"         {note}  scores: {scores}")

    # ── 汇总 ──
    passed = sum(1 for r in results if r[6])
    failed = sum(1 for r in results if not r[6])

    print(f"\n{'=' * 105}")
    print(f"  通过: {passed}/{len(results)}  失败: {failed}/{len(results)}")

    for diff in ["简单", "中等", "复杂", "极限"]:
        group = [r for r in results if r[1] == diff]
        p = sum(1 for r in group if r[6])
        print(f"  {diff}: {p}/{len(group)}")

    if failed:
        print(f"\n  失败详情:")
        for r in results:
            if not r[6]:
                print(f"  #{r[0]} [{r[1]}] \"{r[2][:50]}\"")
                print(f"       期望: {r[5]}  实际: {r[3]}  scores: {r[4]}")

    # 确认卡触发统计
    confirmed = [r for r in results if r[8]]
    if confirmed:
        print(f"\n  触发确认卡 ({len(confirmed)} 条):")
        for r in confirmed:
            print(f"  #{r[0]} [{r[1]}] intents={r[3]} → ⚡需要确认")

    print("=" * 105)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
