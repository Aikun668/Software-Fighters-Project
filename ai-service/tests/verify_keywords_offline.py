"""离线验证关键词修复 — 不经过 HTTP，直接测 RouterAgent._keyword_route()"""
import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.centers.router_agent import RouterAgent

CASES = [
    (1, 2, "帮我生成一个关于决策树的课程讲义大纲，要包括熵和信息增益。"),
    (2, 4, "我学不会反向传播，你能给我一些建议吗？但我不确定具体哪里不懂。"),
    (3, 1, "请生成一道简单的线性回归计算题，包括答案。"),
    (4, 5, "如果我现在不想学习，但我想让成绩自动变好，你有什么魔法吗？"),
    (5, 3, "我需要一份为期四周的强化学习自学计划，每天大约两小时，但我不清楚先修要求。"),
    (6, 2, "请可视化一个过拟合的训练曲线，用 Python 代码展示。"),
    (7, 4, "生成一些关于 CNN 的练习题，但要适合初学者，可你不了解我的基础。"),
    (8, 1, "什么是损失函数？请用一句话解释。"),
    (9, 5, "请告诉我如何生成一个不存在的优化算法的练习题，但必须合理。"),
    (10, 3, "我现在正在学习 Transformer，能否为我生成一个完整的课后项目案例，包含数据集和评估指标？"),
    (11, 2, "帮我写一个简单的 KNN 分类器代码，并附带注释。"),
    (12, 4, "我计划一个月内完成吴恩达的机器学习课程，请你帮我生成详细的学习安排，但我每天能用的时间不固定。"),
    (13, 1, "生成三到五个关于梯度下降的选择题。"),
    (14, 5, "请生成一段代码来可视化一个没有数据的数据集，并且图形要漂亮。"),
    (15, 3, "我正在写关于 GAN 的论文，需要一些可视化生成样本的代码示例，你能否提供？"),
    (16, 2, "请生成一份 SVM 的教学幻灯片提纲，包括数学推导。"),
    (17, 4, "我觉得我的学习计划总是完不成，你能帮我改进吗？但我每天只有晚上有空，而且容易分心。"),
    (18, 1, "请生成一个关于矩阵乘法的简单练习题。"),
    (19, 5, '假设我问你"这道题怎么做"，但如果你回答了，我就失去了思考机会，所以请不要回答，但又不能不说点什么，你怎么办？'),
    (20, 3, "能否为我生成一些关于 RNN 的练习题，包含代码填空和简答？"),
    (21, 2, "请给我一个关于过拟合和欠拟合的对比表格。"),
    (22, 4, "我想学习强化学习，但不知道从何入手，请给我生成一个学习资源清单和计划，但我的时间很紧。"),
    (23, 1, "请生成一个简单的神经网络结构图（文字描述即可）。"),
    (24, 5, "请帮我生成一份学习计划，但不要具体时间，也不要太笼统，要适合我，但我不告诉你任何个人信息。"),
    (25, 3, "请生成一个包含交叉验证的模型选择步骤的可视化流程图。"),
]

# 期望路由 (基于人工判断)
EXPECTED = {
    1: "resource",       # 生成大纲 → ResourceCenter
    2: "auto/tutor",     # 学习困惑 → TutorAgent
    3: "exercise",       # 生成计算题 → ExerciseCenter
    4: "auto/tutor",     # 闲聊魔法 → TutorAgent
    5: "plan",           # 自学计划 → PlanCenter
    6: "visualization",  # 可视化训练曲线 → VisualizationCenter (or resource+diagram)
    7: "exercise",       # 生成练习题 → ExerciseCenter
    8: "auto/tutor",     # 什么是... → TutorAgent
    9: "exercise",       # 生成练习题 → ExerciseCenter
    10: "resource",       # 课后项目案例 → ResourceCenter
    11: "resource",       # 写代码 → ResourceCenter (code)
    12: "plan",           # 学习安排 → PlanCenter
    13: "exercise",       # 选择题 → ExerciseCenter
    14: "resource",       # 代码可视化 → ambiguous: code or visualization? → resource likely
    15: "resource",       # 代码示例 → ResourceCenter
    16: "resource",       # 幻灯片提纲 → ResourceCenter
    17: "auto/tutor",     # 学习计划完不成 → TutorAgent (personal advice)
    18: "exercise",       # 生成练习题 → ExerciseCenter
    19: "auto/tutor",     # 哲学玩笑 → TutorAgent
    20: "exercise",       # 练习题 → ExerciseCenter
    21: "resource",       # 对比表格 → ResourceCenter (content/comparison)
    22: "plan",           # 学习资源清单+计划 → plan or resource? ambiguous. "计划" + "资源清单"
    23: "visualization",  # 结构图 → VisualizationCenter
    24: "plan",           # 学习计划 → PlanCenter
    25: "visualization",  # 可视化流程图 → VisualizationCenter
}


async def main():
    router = RouterAgent()
    print("=" * 100)
    print("  离线关键词路由验证（不经过 HTTP，直接测新代码）")
    print("=" * 100)

    for cid, difficulty, message in CASES:
        plan = await router.route(message, mode="auto")
        tasks = plan.tasks
        center = tasks[0].mode if tasks else "?"
        intent = tasks[0].intent if tasks else "?"
        confidence = tasks[0].confidence if tasks else 0.0
        expected = EXPECTED.get(cid, "?")
        intents = [(t.intent, f"{t.confidence:.3f}") for t in tasks]

        expected_center = expected.split("/")[0]
        ok = center == expected_center or expected_center in center

        marker = "PASS" if ok else "MISMATCH"
        msg_short = message[:45] + "..." if len(message) > 45 else message
        print(f"  [{cid:2d}] [难度{difficulty}] {msg_short:<48} → {center}:{intent}({confidence:.3f}) | expect={expected} | {marker}")

        if not ok:
            print(f"       ALL: {intents}")

    print("=" * 100)


if __name__ == "__main__":
    asyncio.run(main())
