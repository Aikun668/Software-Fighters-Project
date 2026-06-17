"""高压 25 用例 — 打印每条消息的路由结果，供人工量化对比。"""
import asyncio
import json
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import httpx

BASE = "http://localhost:8100/internal"

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
    (19, 5, '假设我问你“这道题怎么做”，但如果你回答了，我就失去了思考机会，所以请不要回答，但又不能不说点什么，你怎么办？'),
    (20, 3, "能否为我生成一些关于 RNN 的练习题，包含代码填空和简答？"),
    (21, 2, "请给我一个关于过拟合和欠拟合的对比表格。"),
    (22, 4, "我想学习强化学习，但不知道从何入手，请给我生成一个学习资源清单和计划，但我的时间很紧。"),
    (23, 1, "请生成一个简单的神经网络结构图（文字描述即可）。"),
    (24, 5, "请帮我生成一份学习计划，但不要具体时间，也不要太笼统，要适合我，但我不告诉你任何个人信息。"),
    (25, 3, "请生成一个包含交叉验证的模型选择步骤的可视化流程图。"),
]


async def run_one(client: httpx.AsyncClient, cid: int, difficulty: int, message: str) -> dict:
    result = {
        "id": cid,
        "difficulty": difficulty,
        "message": message,
        "center": "?",
        "agent": "?",
        "intent": "?",
        "has_inquiry": False,
        "error": None,
    }
    try:
        async with client.stream(
            "POST",
            f"{BASE}/api/chat",
            json={
                "message": message,
                "mode": "auto",
                "user_id": 1,
                "messages": [],
                "student_profile": {},
            },
            timeout=180.0,
        ) as response:
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue

                etype = event.get("type", "")

                if etype == "inquiry":
                    result["has_inquiry"] = True

                if etype == "center_start":
                    result["center"] = event.get("data", {}).get("mode", "?")
                    result["intent"] = event.get("data", {}).get("intent", "?")

                if etype == "center_end":
                    data = event.get("data", {})
                    result["agent"] = data.get("agent", "?")

                if etype == "done":
                    data = event.get("data", {})
                    for r in (data.get("results") or []):
                        a = r.get("agent", "")
                        if a:
                            result["agent"] = a
                            result["center"] = r.get("mode", result["center"])
                            result["intent"] = r.get("intent", result["intent"])
                    break
    except Exception as e:
        result["error"] = str(e)[:100]

    return result


async def main():
    print("=" * 110)
    print("  高压 25 用例路由验证 — 逐条输出路由结果")
    print("=" * 110)

    results = []
    async with httpx.AsyncClient(trust_env=False) as client:
        for cid, difficulty, message in CASES:
            marker = f"[{cid:2d}]"
            sys.stdout.write(f"  {marker} [难度{difficulty}] {message[:55]}... ")
            sys.stdout.flush()
            r = await run_one(client, cid, difficulty, message)
            results.append(r)
            if r["error"]:
                print(f"ERR: {r['error']}")
            else:
                inquiry_flag = " [INQUIRY]" if r["has_inquiry"] else ""
                print(f"→ center={r['center']} | intent={r['intent']} | agent={r['agent']}{inquiry_flag}")

    # 汇总表
    print("\n" + "=" * 110)
    print(f"  {'#':<3} {'难度':<4} {'输入':<50} {'Center':<14} {'Intent':<20} {'Agent':<30}")
    print("  " + "-" * 108)
    for r in results:
        msg = r["message"][:47] + "..." if len(r["message"]) > 48 else r["message"]
        inquiry = " +inquiry" if r["has_inquiry"] else ""
        print(f"  {r['id']:<3} {r['difficulty']:<4} {msg:<50} {r['center']:<14} {r['intent']:<20} {r['agent']:<30}{inquiry}")

    print("=" * 110)
    print(f"  共 {len(results)} 条，供人工量化对比")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
