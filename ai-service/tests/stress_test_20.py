"""
Resource Workshop - 20-case stress test: hard -> easy -> ambiguous -> distorted
Tests Director routing only (no LLM dependency).
"""
import asyncio, sys
sys.path.insert(0, ".")
from app.orchestration.director import Director

CASES = [
    # === HARD (5 cases): multi-intent, technical, long ===
    ("H1", "我想从零开始用PyTorch搭建一个完整的图像分类项目，包括数据预处理、模型设计、训练循环和评估，最后部署成API"),
    ("H2", "请给我一个完整的对比分析：CNN vs ViT在中小规模图像分类任务上的性能差异、计算复杂度和适用场景"),
    ("H3", "我的Transformer模型训练时encoder输出全是NaN，decoder的attention权重全为0，梯度爆炸了，怎么排查和修复"),
    ("H4", "从数学原理到代码实现，详细讲解反向传播算法中的链式法则、梯度消失问题和各种优化器的对比"),
    ("H5", "用D3.js做一个交互式的神经网络训练过程可视化，要能实时看到损失曲线下降、权重分布变化和决策边界演变"),

    # === EASY (5 cases): clear intent ===
    ("E1", "什么是过拟合"),
    ("E2", "写一个Python冒泡排序"),
    ("E3", "帮我总结一下深度学习的知识点"),
    ("E4", "为什么CNN适合图像识别"),
    ("E5", "做一个图片分类的小项目练手"),

    # === AMBIGUOUS (5 cases): vague, borderline ===
    ("A1", "学习一下"),
    ("A2", "神经网络"),
    ("A3", "那个什么算法来着"),
    ("A4", "不知道从哪里开始"),
    ("A5", "有没有什么好的推荐"),

    # === DISTORTED (5 cases): typos, mixed lang, broken ===
    ("D1", "pyhton 机器学习 咋写"),
    ("D2", "what is backprop 反向传播 explain in simple terms"),
    ("D3", "ml dl ai 区别 对比 vs"),
    ("D4", "帮我写个。就那个。分类的。代码"),
    ("D5", "loss不下降 lr调了也没用 咋整 急"),
]


async def main():
    d = Director(use_mock=True)
    results = []

    for tag, topic in CASES:
        r = await d.route(topic)
        results.append((tag, topic, r))

    # Print table
    sep = "=" * 110
    print(f"\n{sep}")
    print("  Resource Workshop - 20-Case Stress Test: HARD -> EASY -> AMBIGUOUS -> DISTORTED")
    print(sep)

    sections = [("HARD", "H"), ("EASY", "E"), ("AMBIGUOUS", "A"), ("DISTORTED", "D")]
    for section_name, prefix in sections:
        print(f"\n  --- {section_name} ({sum(1 for t,_,_ in results if t[0]==prefix)} cases) ---")
        print(f"  {'#':<5} {'Input':<68} {'Agent':<22} {'Strategy':<12}")
        print(f"  {'-'*5} {'-'*68} {'-'*22} {'-'*12}")
        for tag, topic, r in results:
            if tag[0] == prefix:
                display = topic[:66] + ".." if len(topic) > 68 else topic
                print(f"  {tag:<5} {display:<68} {r.agent_name:<22} {r.strategy:<12}")

    # Summary
    print(f"\n{sep}")
    print("  QUANTITATIVE SUMMARY")
    print(sep)
    agents = {}
    strategies = {}
    for _, _, r in results:
        agents[r.agent_name] = agents.get(r.agent_name, 0) + 1
        strategies[r.strategy] = strategies.get(r.strategy, 0) + 1

    for cat, prefix in [("HARD","H"), ("EASY","E"), ("AMBIGUOUS","A"), ("DISTORTED","D")]:
        cats = [r for t,_,r in results if t[0]==prefix]
        cat_agents = {}
        for r in cats:
            cat_agents[r.agent_name] = cat_agents.get(r.agent_name, 0) + 1
        print(f"  {cat:<12}: {dict(cat_agents)}")

    print(f"\n  Overall agent distribution: {agents}")
    print(f"  Strategy distribution: {strategies}")

    # Edge case analysis
    print(f"\n  Edge cases found:")
    ambiguous_content = [r for t,_,r in results if t[0]=='A']
    print(f"    Ambiguous->content (safe fallback): {sum(1 for r in ambiguous_content if r.agent_name=='content')}/{len(ambiguous_content)}")
    distorted_correct = [r for t,_,r in results if t[0]=='D']
    print(f"    Distorted still routable: {sum(1 for r in distorted_correct if r.strategy=='rule')}/{len(distorted_correct)} via keyword matching")

    # Recommendations
    print(f"\n  RECOMMENDATIONS:")
    if any(r.agent_name == 'content' and r.strategy == 'llm' for _,_,r in results):
        print("    - Add more keyword patterns to capture code-writing intent (see H4, D4)")
    print("    - Consider adding 'learning_advice' sub-type for A1/A4/A5 type queries")
    print(f"\n{sep}\n")

asyncio.run(main())
