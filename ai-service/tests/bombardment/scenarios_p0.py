"""
P0 核心用户链路测试场景
端点: /api/chat (6场景) + /tutor/chat (4场景)
"""

API_BASE = "http://127.0.0.1:8001/internal"

DEFAULT_PROFILE = {
    "knowledge_base": 45,
    "cognitive_style": "visual",
    "learning_goal": "掌握深度学习",
    "weak_points": ["数学基础"],
    "learning_pace": "moderate",
}

NEWBIE_PROFILE = {
    "knowledge_base": 15,
    "cognitive_style": "textual",
    "learning_goal": "入门AI",
    "weak_points": ["编程基础", "数学基础"],
    "learning_pace": "slow",
}

SCENARIOS = [
    # ═══════════════════ /api/chat ═══════════════════
    {
        "id": "chat_knowledge",
        "category": "统一问答",
        "endpoint": "/api/chat",
        "description": "概念解释 — 卷积神经网络",
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "请解释什么是卷积神经网络",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": {
            "dimensions": ["概念准确性", "解释清晰度", "示例恰当性", "教学价值"],
            "rubric": """你是AI教育质量评审专家。请评审以下AI助教对"卷积神经网络"概念的解释。

评分维度 (每项 0.0-1.0):
1. 概念准确性: 定义是否正确？卷积/池化/全连接三阶段描述是否准确？
2. 解释清晰度: 新手能否理解？是否解释了"为什么用卷积"而不只"什么是卷积"？
3. 示例恰当性: 是否有具体例子或类比帮助理解？
4. 教学价值: 是否点出CNN核心insight（局部感知、权重共享）？

输出严格 JSON (无 markdown):
{"scores": {"概念准确性": 0.X, "解释清晰度": 0.X, "示例恰当性": 0.X, "教学价值": 0.X}, "total": 0.X, "verdict": "PASS或WARN或FAIL", "comment": "一句话总结"}

待评审回复:
{response}""",
            "pass_threshold": 0.65,
        },
    },
    {
        "id": "chat_compare",
        "category": "统一问答",
        "endpoint": "/api/chat",
        "description": "对比分析 — 监督学习 vs 无监督学习",
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "监督学习和无监督学习有什么区别？各自适合什么场景？",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": {
            "dimensions": ["对比完整性", "场景判断准确性", "结构质量", "解释清晰度"],
            "rubric": """你是AI教育质量评审专家。请评审以下AI对监督学习与无监督学习对比的回答。

评分维度 (每项 0.0-1.0):
1. 对比完整性: 是否覆盖核心区别（数据标注、目标、评估方式）？
2. 场景判断准确性: 各自适用场景的描述是否正确？
3. 结构质量: 对比是否结构化？维度是否清晰？
4. 解释清晰度: 新手能否区分两者？

输出严格 JSON (无 markdown):
{"scores": {"对比完整性": 0.X, "场景判断准确性": 0.X, "结构质量": 0.X, "解释清晰度": 0.X}, "total": 0.X, "verdict": "PASS或WARN或FAIL", "comment": "一句话总结"}

待评审回复:
{response}""",
            "pass_threshold": 0.65,
        },
    },
    {
        "id": "chat_practice",
        "category": "统一问答",
        "endpoint": "/api/chat",
        "description": "练习请求 — 损失函数题目",
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "给我出几道关于损失函数的练习题，要有答案解析。",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": {
            "dimensions": ["题目相关性", "难度梯度", "解析质量", "实用性"],
            "rubric": """你是AI教育质量评审专家。请评审以下AI生成的损失函数练习题。

评分维度 (每项 0.0-1.0):
1. 题目相关性: 题目是否紧扣损失函数主题？
2. 难度梯度: 是否有从易到难的层次？
3. 解析质量: 答案解析是否清晰完整？
4. 实用性: 是否有助于检验和加深理解？

输出严格 JSON (无 markdown):
{"scores": {"题目相关性": 0.X, "难度梯度": 0.X, "解析质量": 0.X, "实用性": 0.X}, "total": 0.X, "verdict": "PASS或WARN或FAIL", "comment": "一句话总结"}

待评审回复:
{response}""",
            "pass_threshold": 0.60,
        },
    },
    {
        "id": "chat_visual",
        "category": "统一问答",
        "endpoint": "/api/chat",
        "description": "可视化触发 — 神经网络架构图",
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "画一张神经网络的架构图，展示输入层、隐藏层和输出层的结构。",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": {
            "dimensions": ["可视化触发", "代码有效性", "内容准确性", "可读性"],
            "rubric": """你是AI可视化质量评审专家。请评审以下AI对"画神经网络架构图"请求的响应。

评分维度 (每项 0.0-1.0):
1. 可视化触发: 是否正确识别了可视化需求？是否返回了可渲染代码(SVG/Mermaid)？
2. 代码有效性: 生成代码格式是否正确？语法是否合法？
3. 内容准确性: 架构图是否正确表现了神经网络层次结构？
4. 可读性: 图表是否清晰？标注是否易懂？

输出严格 JSON (无 markdown):
{"scores": {"可视化触发": 0.X, "代码有效性": 0.X, "内容准确性": 0.X, "可读性": 0.X}, "total": 0.X, "verdict": "PASS或WARN或FAIL", "comment": "一句话总结"}

待评审回复:
{response}""",
            "pass_threshold": 0.60,
        },
    },
    {
        "id": "chat_edge_vague",
        "category": "统一问答",
        "endpoint": "/api/chat",
        "description": "边角情况 — 极短模糊输入",
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "过拟合",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": {
            "dimensions": ["意图理解", "回复相关性", "主动性", "体验"],
            "rubric": """你是AI交互质量评审专家。用户只输入了"过拟合"两个字。

评分维度 (每项 0.0-1.0):
1. 意图理解: 是否合理推断用户意图（解释概念？解决方法？）？
2. 回复相关性: 回复是否紧扣"过拟合"？
3. 主动性: 是否主动展开有价值的解释而非敷衍？
4. 体验: 面对模糊输入，交互体验是否好？

输出严格 JSON (无 markdown):
{"scores": {"意图理解": 0.X, "回复相关性": 0.X, "主动性": 0.X, "体验": 0.X}, "total": 0.X, "verdict": "PASS或WARN或FAIL", "comment": "一句话总结"}

待评审回复:
{response}""",
            "pass_threshold": 0.55,
        },
    },
    {
        "id": "chat_profile_newbie",
        "category": "统一问答",
        "endpoint": "/api/chat",
        "description": "画像感知 — 零基础学生问深度学习",
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "什么是深度学习？",
                "user_id": 1,
                "mode": "auto",
                "student_profile": NEWBIE_PROFILE,
            },
        },
        "judge": {
            "dimensions": ["难度自适应", "语言适配", "内容深度", "个性化程度"],
            "rubric": """你是AI教育质量评审专家。一个零基础学生（基础分15，弱项：编程+数学）问"什么是深度学习"。

评分维度 (每项 0.0-1.0):
1. 难度自适应: 回复难度是否匹配零基础水平？是否避免了过深的技术术语？
2. 语言适配: 语言是否通俗易懂？是否用了类比帮助理解？
3. 内容深度: 在保持简单的同时是否传达了核心概念？
4. 个性化程度: 是否体现了对零基础学习者的针对性引导？

输出严格 JSON (无 markdown):
{"scores": {"难度自适应": 0.X, "语言适配": 0.X, "内容深度": 0.X, "个性化程度": 0.X}, "total": 0.X, "verdict": "PASS或WARN或FAIL", "comment": "一句话总结"}

待评审回复:
{response}""",
            "pass_threshold": 0.60,
        },
    },
    # ═══════════════════ /tutor/chat ═══════════════════
    {
        "id": "tutor_explain",
        "category": "导师辅导",
        "endpoint": "/tutor/chat",
        "description": "概念讲解 — 梯度下降数学原理",
        "request": {
            "url": f"{API_BASE}/tutor/chat",
            "body": {
                "user_id": 1,
                "messages": [
                    {"role": "user", "content": "帮我理解一下梯度下降的数学原理"}
                ],
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": {
            "dimensions": ["数学准确性", "教学递进", "可理解性", "教学价值"],
            "rubric": """你是AI导师质量评审专家。学生请求"理解梯度下降的数学原理"，学生基础中等偏弱。

评分维度 (每项 0.0-1.0):
1. 数学准确性: 梯度、学习率、参数更新公式是否正确？
2. 教学递进: 是否从直观理解过渡到数学表达？
3. 可理解性: 数学弱项的学生能否跟上？
4. 教学价值: 是否帮助建立了对优化本质的理解？

输出严格 JSON (无 markdown):
{"scores": {"数学准确性": 0.X, "教学递进": 0.X, "可理解性": 0.X, "教学价值": 0.X}, "total": 0.X, "verdict": "PASS或WARN或FAIL", "comment": "一句话总结"}

待评审回复:
{response}""",
            "pass_threshold": 0.60,
        },
    },
    {
        "id": "tutor_debug",
        "category": "导师辅导",
        "endpoint": "/tutor/chat",
        "description": "调试求助 — loss不收敛",
        "request": {
            "url": f"{API_BASE}/tutor/chat",
            "body": {
                "user_id": 1,
                "messages": [
                    {"role": "user", "content": "训练时loss一直不收敛，震荡很厉害，怎么办？"}
                ],
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": {
            "dimensions": ["诊断准确性", "建议可操作性", "教学价值", "深度"],
            "rubric": """你是AI导师质量评审专家。学生报告训练loss震荡不收敛，请求帮助。

评分维度 (每项 0.0-1.0):
1. 诊断准确性: 是否准确指出了可能原因（学习率、数据、初始化等）？
2. 建议可操作性: 给出的排查步骤是否具体可执行？
3. 教学价值: 是否帮助理解"为什么"会出现震荡？
4. 深度: 是否给出多层次建议（从简单排查到深入调参）？

输出严格 JSON (无 markdown):
{"scores": {"诊断准确性": 0.X, "建议可操作性": 0.X, "教学价值": 0.X, "深度": 0.X}, "total": 0.X, "verdict": "PASS或WARN或FAIL", "comment": "一句话总结"}

待评审回复:
{response}""",
            "pass_threshold": 0.60,
        },
    },
    {
        "id": "tutor_multiturn",
        "category": "导师辅导",
        "endpoint": "/tutor/chat",
        "description": "多轮对话 — 激活函数连续追问",
        "request": {
            "url": f"{API_BASE}/tutor/chat",
            "body": {
                "user_id": 1,
                "messages": [
                    {"role": "user", "content": "激活函数在神经网络里有什么用？"},
                    {"role": "user", "content": "那ReLU为什么比sigmoid更常用？"},
                    {"role": "user", "content": "具体说说ReLU的优缺点，还有哪些变体可以替代它？"},
                ],
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": {
            "dimensions": ["上下文连贯性", "指代理解", "知识递进", "交互自然度"],
            "rubric": """你是AI导师质量评审专家。学生连续追问了3条关于激活函数的消息：先问作用→再问ReLU vs sigmoid→最后问ReLU变体。请评审AI对最后一问的回答。

评分维度 (每项 0.0-1.0):
1. 上下文连贯性: 回答是否承接了前两问的讨论脉络？
2. 指代理解: 是否正确理解了"ReLU"指代之前讨论的函数？
3. 知识递进: 回答深度是否随追问自然递进？
4. 交互自然度: 多轮对话体验是否流畅自然？

输出严格 JSON (无 markdown):
{"scores": {"上下文连贯性": 0.X, "指代理解": 0.X, "知识递进": 0.X, "交互自然度": 0.X}, "total": 0.X, "verdict": "PASS或WARN或FAIL", "comment": "一句话总结"}

待评审回复:
{response}""",
            "pass_threshold": 0.60,
        },
    },
    {
        "id": "tutor_newbie",
        "category": "导师辅导",
        "endpoint": "/tutor/chat",
        "description": "零基础入门 — 什么是机器学习",
        "request": {
            "url": f"{API_BASE}/tutor/chat",
            "body": {
                "user_id": 1,
                "messages": [
                    {"role": "user", "content": "什么是机器学习？我完全没基础，请用最简单的话讲"}
                ],
                "student_profile": NEWBIE_PROFILE,
            },
        },
        "judge": {
            "dimensions": ["语言通俗度", "类比使用", "概念准确性", "入门引导"],
            "rubric": """你是AI导师质量评审专家。零基础学生（基础分15）问"什么是机器学习"，明确要求"用最简单的话讲"。

评分维度 (每项 0.0-1.0):
1. 语言通俗度: 是否避免了术语轰炸？语言是否像人在对话而非教科书？
2. 类比使用: 是否用了生活化类比帮助零基础理解？
3. 概念准确性: 通俗解释的同时是否保持了核心概念的准确性？
4. 入门引导: 是否给了继续学习的明确方向或下一步建议？

输出严格 JSON (无 markdown):
{"scores": {"语言通俗度": 0.X, "类比使用": 0.X, "概念准确性": 0.X, "入门引导": 0.X}, "total": 0.X, "verdict": "PASS或WARN或FAIL", "comment": "一句话总结"}

待评审回复:
{response}""",
            "pass_threshold": 0.60,
        },
    },
]
