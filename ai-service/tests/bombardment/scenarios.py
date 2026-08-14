"""
测试场景定义。每个场景包含:
  - 输入（发往 AI 服务的请求）
  - 裁判提示词（LLM 用量化标准评审回复质量）
  - 通过阈值

新增场景只需追加到 SCENARIOS 列表即可。
"""

API_BASE = "http://127.0.0.1:8001/internal"
DEFAULT_PROFILE = {
    "knowledge_base": 45,
    "cognitive_style": "visual",
    "learning_goal": "掌握深度学习",
    "weak_points": ["数学基础"],
    "learning_pace": "moderate",
}

SCENARIOS = [
    # ═══════════════════════ chat / 基础问答 ═══════════════════════
    {
        "id": "chat_definition",
        "category": "基础问答",
        "description": "概念定义 — 反向传播",
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "什么是反向传播算法？",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": {
            "dimensions": ["概念准确性", "解释清晰度", "示例恰当性", "教学价值"],
            "rubric": """你是AI教育质量评审专家。请评审以下AI助教对"反向传播"概念的解释。

评分维度 (每项 0.0-1.0):
1. 概念准确性: 定义是否正确？是否混淆了梯度下降和反向传播？
2. 解释清晰度: 新手能否理解？逻辑链条是否完整？
3. 示例恰当性: 是否有具体例子或类比帮助理解？
4. 教学价值: 是否有助于建立知识体系？是否点出关键insight？

输出严格 JSON (无 markdown):
{"scores": {"概念准确性": 0.X, "解释清晰度": 0.X, "示例恰当性": 0.X, "教学价值": 0.X}, "total": 0.X, "verdict": "PASS|WARN|FAIL", "comment": "一句话总结"}

待评审回复:
{response}""",
            "pass_threshold": 0.65,
        },
    },
    {
        "id": "chat_comparison",
        "category": "基础问答",
        "description": "对比分析 — CNN vs RNN",
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "CNN和RNN有什么区别？各自的适用场景是什么？",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": {
            "dimensions": ["对比完整性", "场景判断准确性", "解释清晰度", "结构质量"],
            "rubric": """你是AI教育质量评审专家。请评审以下AI助教对CNN与RNN对比的回答。

评分维度 (每项 0.0-1.0):
1. 对比完整性: 是否覆盖了核心区别（结构、信息流、适用数据）？
2. 场景判断准确性: 各自适用场景的描述是否正确？
3. 解释清晰度: 对比是否结构化？新手能否区分？
4. 结构质量: 是否有对比维度？逻辑是否清楚？

输出严格 JSON (无 markdown):
{"scores": {"对比完整性": 0.X, "场景判断准确性": 0.X, "解释清晰度": 0.X, "结构质量": 0.X}, "total": 0.X, "verdict": "PASS|WARN|FAIL", "comment": "一句话总结"}

待评审回复:
{response}""",
            "pass_threshold": 0.65,
        },
    },
    {
        "id": "chat_exercise",
        "category": "基础问答",
        "description": "练习请求 — 过拟合题目",
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "给我出几道关于过拟合和正则化的练习题，要有答案解析。",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": {
            "dimensions": ["题目相关性", "难度梯度", "答案解析质量", "实用性"],
            "rubric": """你是AI教育质量评审专家。请评审以下AI助教生成的练习题。

评分维度 (每项 0.0-1.0):
1. 题目相关性: 题目是否紧扣过拟合与正则化主题？
2. 难度梯度: 是否有从易到难的层次？
3. 答案解析质量: 解析是否清晰完整？
4. 实用性: 是否有助于检验和加深理解？

输出严格 JSON (无 markdown):
{"scores": {"题目相关性": 0.X, "难度梯度": 0.X, "答案解析质量": 0.X, "实用性": 0.X}, "total": 0.X, "verdict": "PASS|WARN|FAIL", "comment": "一句话总结"}

待评审回复:
{response}""",
            "pass_threshold": 0.60,
        },
    },
    # ═══════════════════════ 可视化 ═══════════════════════
    {
        "id": "vis_flowchart",
        "category": "可视化",
        "description": "流程图 — Transformer架构",
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "请画一张Transformer架构的流程图，展示Encoder和Decoder的数据流向。",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": {
            "dimensions": ["可视化触发(是否正确生成)", "代码有效性", "内容准确性", "可读性"],
            "rubric": """你是AI可视化质量评审专家。请评审以下AI助教对可视化请求的响应。

评分维度 (每项 0.0-1.0):
1. 可视化触发: 是否正确识别了需要生成可视化？是否返回了可渲染代码(SVG/Mermaid等)？
2. 代码有效性: 生成的代码格式是否正确？（Mermaid语法、SVG结构、XML合法性）
3. 内容准确性: 架构图是否正确表现了Transformer的组件和数据流？
4. 可读性: 图表是否清晰？布局和标注是否易懂？

输出严格 JSON (无 markdown):
{"scores": {"可视化触发": 0.X, "代码有效性": 0.X, "内容准确性": 0.X, "可读性": 0.X}, "total": 0.X, "verdict": "PASS|WARN|FAIL", "comment": "一句话总结"}

待评审回复:
{response}""",
            "pass_threshold": 0.60,
        },
    },
    {
        "id": "vis_comparison_chart",
        "category": "可视化",
        "description": "对比图表 — 梯度下降变体",
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "对比SGD、Momentum、Adam三种优化器，画一个对比表格或图表展示它们的区别和特点。",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": {
            "dimensions": ["可视化触发", "代码有效性", "内容准确性", "可读性"],
            "rubric": """你是AI可视化质量评审专家。请评审以下AI对"优化器对比"可视化请求的响应。

评分维度 (每项 0.0-1.0):
1. 可视化触发: 是否识别到对比需求并生成了可视化代码？
2. 代码有效性: 生成的代码语法是否合法？
3. 内容准确性: 三种优化器的特点和区别是否描述正确？
4. 可读性: 对比是否清晰？信息组织是否合理？

输出严格 JSON (无 markdown):
{"scores": {"可视化触发": 0.X, "代码有效性": 0.X, "内容准确性": 0.X, "可读性": 0.X}, "total": 0.X, "verdict": "PASS|WARN|FAIL", "comment": "一句话总结"}

待评审回复:
{response}""",
            "pass_threshold": 0.60,
        },
    },
    # ═══════════════════════ 资源生成 ═══════════════════════
    {
        "id": "resource_learning",
        "category": "资源生成",
        "description": "生成学习资料 — 自注意力机制",
        "request": {
            "url": f"{API_BASE}/resources/generate",
            "body": {
                "topic": "自注意力机制详解",
                "user_id": 1,
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": {
            "dimensions": ["内容准确性", "结构完整性", "教育价值", "实用性"],
            "rubric": """你是AI教育资源质量评审专家。请评审以下AI生成的关于"自注意力机制"的学习资源。

评分维度 (每项 0.0-1.0):
1. 内容准确性: 技术解释是否正确？公式和概念是否准确？
2. 结构完整性: 资源是否组织有序？从基础到深入的层次是否清晰？
3. 教育价值: 是否提供了透彻的insight？是否帮助学习者真正理解？
4. 实用性: 是否包含代码/图示/类比等促进理解的元素？

输出严格 JSON (无 markdown):
{"scores": {"内容准确性": 0.X, "结构完整性": 0.X, "教育价值": 0.X, "实用性": 0.X}, "total": 0.X, "verdict": "PASS|WARN|FAIL", "comment": "一句话总结"}

待评审回复:
{response}""",
            "pass_threshold": 0.60,
        },
    },
    # ═══════════════════════ 导师答疑 ═══════════════════════
    {
        "id": "tutor_debug",
        "category": "导师答疑",
        "description": "调试求助 — loss不收敛",
        "request": {
            "url": f"{API_BASE}/tutor/chat",
            "body": {
                "user_id": 1,
                "messages": [
                    {"role": "user", "content": "我训练神经网络时loss一直不收敛，震荡很厉害，怎么办？"}
                ],
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": {
            "dimensions": ["诊断准确性", "建议实用性", "教学价值", "深度"],
            "rubric": """你是AI导师质量评审专家。请评审以下AI导师对"训练不收敛"问题的回答。

评分维度 (每项 0.0-1.0):
1. 诊断准确性: 是否准确识别了可能的原因（学习率、数据、网络结构等）？
2. 建议实用性: 给出的排查步骤是否具体可操作？
3. 教学价值: 是否帮助学习者理解为什么会出现这个问题？
4. 深度: 是否给出了多层次建议（从简单到深入）？

输出严格 JSON (无 markdown):
{"scores": {"诊断准确性": 0.X, "建议实用性": 0.X, "教学价值": 0.X, "深度": 0.X}, "total": 0.X, "verdict": "PASS|WARN|FAIL", "comment": "一句话总结"}

待评审回复:
{response}""",
            "pass_threshold": 0.60,
        },
    },
    # ═══════════════════════ 边角情况 ═══════════════════════
    {
        "id": "edge_short",
        "category": "边角情况",
        "description": "极短输入",
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "梯度下降",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": {
            "dimensions": ["意图理解", "回复相关性", "主动性", "体验"],
            "rubric": """你是AI交互质量评审专家。用户只输入了"梯度下降"两个词。

评分维度 (每项 0.0-1.0):
1. 意图理解: 是否合理推断用户意图（是要求解释?对比?还是例子?）？
2. 回复相关性: 回复是否紧扣"梯度下降"？
3. 主动性: 是否给出了有价值的解释而非敷衍？
4. 体验: 面对模糊输入，交互体验是否好？

输出严格 JSON (无 markdown):
{"scores": {"意图理解": 0.X, "回复相关性": 0.X, "主动性": 0.X, "体验": 0.X}, "total": 0.X, "verdict": "PASS|WARN|FAIL", "comment": "一句话总结"}

待评审回复:
{response}""",
            "pass_threshold": 0.55,
        },
    },
]
