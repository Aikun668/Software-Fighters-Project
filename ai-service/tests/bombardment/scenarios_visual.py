"""
可视化专项测试场景 — 10 个场景
覆盖: 流程图/结构图/对比图/曲线图/负例/边界

端点: /api/chat (mode=auto, 走 AutoCenter._maybe_visualize)
"""

API_BASE = "http://127.0.0.1:8001/internal"

DEFAULT_PROFILE = {
    "knowledge_base": 45,
    "cognitive_style": "visual",
    "learning_goal": "掌握深度学习",
    "weak_points": ["数学基础"],
    "learning_pace": "moderate",
}

# ═══════════════════════════════════════════════════════════════
# 裁判 rubric 模板
# {response} 会被实际回复替换
# {validation_note} 会被确定性校验结果替换
# ═══════════════════════════════════════════════════════════════

_VIS_RUBRIC_TEMPLATE = """你是AI可视化质量评审专家。请评审以下AI对可视化请求的响应。

评分维度 (每项 0.0-1.0):
1. trigger_accuracy: 是否正确识别了需要/不需要可视化？正确触发=1.0，该触发没触发=0.0，不该触发却触发了=0.0
2. type_appropriateness: 选择的渲染类型(mermaid/svg/chartjs/html)是否适合该内容？流程图用flowchart、结构图用graph、数据对比用chartjs都是合适的选择。如果没有生成可视化代码，且判断正确则给1.0
3. code_validity: 生成的可视化代码语法是否合法？没有代码时若判断正确则给1.0
4. content_fidelity: 可视化内容是否准确反映请求主题？文字回答是否覆盖核心知识点？

{extra_context}

输出严格 JSON (无 markdown):
{{"scores": {{"trigger_accuracy": 0.X, "type_appropriateness": 0.X, "code_validity": 0.X, "content_fidelity": 0.X}}, "total": 0.X, "verdict": "PASS或WARN或FAIL", "comment": "一句话总结"}}

待评审回复:
{response}"""


def _make_judge(description: str, extra_context: str = "", pass_threshold: float = 0.60) -> dict:
    return {
        "dimensions": ["trigger_accuracy", "type_appropriateness", "code_validity", "content_fidelity"],
        "rubric": _VIS_RUBRIC_TEMPLATE.replace("{extra_context}", extra_context),
        "pass_threshold": pass_threshold,
        "description_hint": description,
    }


SCENARIOS = [
    # ═══════════════════ 正向: 应触发可视化 ═══════════════════
    {
        "id": "vis_transformer_arch",
        "category": "可视化-结构图",
        "endpoint": "/api/chat",
        "description": "Transformer架构图 — 编码器-解码器结构",
        "expected_trigger": True,
        "expected_types": ["mermaid"],
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "请画出Transformer模型的完整架构图，包括编码器和解码器的各个子层。",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": _make_judge(
            "Transformer架构图",
            extra_context="附加信息: 这是一个请求绘制Transformer架构图的场景。Transformer包含编码器(自注意力+前馈网络)和解码器(带掩码的自注意力+交叉注意力+前馈网络)。合理的可视化应该是mermaid graph或flowchart，展示层之间的数据流。",
            pass_threshold=0.60,
        ),
    },
    {
        "id": "vis_optimizer_compare",
        "category": "可视化-对比图",
        "endpoint": "/api/chat",
        "description": "优化器对比 — SGD vs Adam vs RMSprop",
        "expected_trigger": True,
        "expected_types": ["chartjs", "mermaid"],
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "画一张对比图比较SGD、Adam和RMSprop三种优化器的特点和适用场景。",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": _make_judge(
            "优化器对比图",
            extra_context="附加信息: 这是一个请求对比三种优化器的场景。对比类内容最适合用chartjs柱状图或对比表格(mermaid不支持表格但可用graph+标签模拟)。SGD: 基础、慢但稳定; Adam: 自适应学习率、收敛快; RMSprop: 处理非平稳目标。",
            pass_threshold=0.60,
        ),
    },
    {
        "id": "vis_cnn_flow",
        "category": "可视化-流程图",
        "endpoint": "/api/chat",
        "description": "CNN数据处理流程 — 卷积→池化→全连接",
        "expected_trigger": True,
        "expected_types": ["mermaid"],
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "画一张卷积神经网络处理图片的完整流程图，从输入图片到输出分类结果。",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": _make_judge(
            "CNN处理流程",
            extra_context="附加信息: CNN流程: 输入图片→卷积层(提取特征)→ReLU激活→池化层(降采样)→...→全连接层→Softmax输出。这是典型的流程/步骤类内容，最适合mermaid flowchart。",
            pass_threshold=0.60,
        ),
    },
    {
        "id": "vis_gradient_descent",
        "category": "可视化-流程图",
        "endpoint": "/api/chat",
        "description": "梯度下降算法流程 — 迭代优化步骤",
        "expected_trigger": True,
        "expected_types": ["mermaid"],
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "画一个梯度下降算法的流程图，展示从初始化参数到收敛的完整迭代过程。",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": _make_judge(
            "梯度下降算法流程",
            extra_context="附加信息: 梯度下降流程: 初始化参数→计算损失函数梯度→更新参数(沿负梯度方向)→检查收敛条件→未收敛则继续迭代。这是典型的算法流程，适合mermaid flowchart。",
            pass_threshold=0.60,
        ),
    },
    {
        "id": "vis_nn_layers",
        "category": "可视化-结构图",
        "endpoint": "/api/chat",
        "description": "神经网络层次结构 — 输入/隐藏/输出层",
        "expected_trigger": True,
        "expected_types": ["mermaid"],
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "画一张包含输入层、三个隐藏层(分别有128、64、32个神经元)和输出层的神经网络结构图。",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": _make_judge(
            "神经网络层次结构",
            extra_context="附加信息: 神经网络层次结构: 输入层→隐藏层1(128神经元)→隐藏层2(64神经元)→隐藏层3(32神经元)→输出层。层级关系明确，适合mermaid graph LR展示从左到右的数据流向。",
            pass_threshold=0.60,
        ),
    },
    {
        "id": "vis_activation_curves",
        "category": "可视化-曲线图",
        "endpoint": "/api/chat",
        "description": "激活函数曲线对比 — ReLU/Sigmoid/Tanh",
        "expected_trigger": True,
        "expected_types": ["chartjs", "svg"],
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "把ReLU、Sigmoid和Tanh这三种激活函数的曲线画在同一张图上进行对比。",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": _make_judge(
            "激活函数曲线对比",
            extra_context="附加信息: 三个激活函数的数学特性: ReLU(x)=max(0,x)在x<0时为0; Sigmoid(x)=1/(1+e^(-x))输出(0,1); Tanh(x)=2*sigmoid(2x)-1输出(-1,1)。曲线对比最合适chartjs line chart或SVG。",
            pass_threshold=0.60,
        ),
    },
    {
        "id": "vis_backprop_flow",
        "category": "可视化-流程图",
        "endpoint": "/api/chat",
        "description": "反向传播算法流程 — 链式法则计算梯度",
        "expected_trigger": True,
        "expected_types": ["mermaid"],
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "画一下反向传播算法的计算流程图，展示误差如何从输出层逐层传回输入层。",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": _make_judge(
            "反向传播算法流程",
            extra_context="附加信息: 反向传播流程: 前向传播计算输出→计算损失→输出层梯度→链式法则逐层回传→更新各层权重。这是算法步骤，适合mermaid flowchart。",
            pass_threshold=0.60,
        ),
    },
    # ═══════════════════ 负向: 不应触发可视化 ═══════════════════
    {
        "id": "vis_neg_definition",
        "category": "可视化-负例",
        "endpoint": "/api/chat",
        "description": "纯概念定义 — 什么是学习率(不应触发可视化)",
        "expected_trigger": False,
        "expected_types": [],
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "什么是学习率？它在训练中起什么作用？",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": _make_judge(
            "什么是学习率(不应可视化)",
            extra_context="附加信息: 这是一个纯概念定义问题，不需要可视化。如果系统正确判断不需要可视化(不返回blocks)，trigger_accuracy=1.0。如果错误地生成了可视化图表，trigger_accuracy=0.0。type_appropriateness和code_validity在无代码时若判断正确则给1.0。重点是content_fidelity: 文字回答是否准确解释了学习率的概念和作用。",
            pass_threshold=0.60,
        ),
    },
    {
        "id": "vis_neg_api_install",
        "category": "可视化-负例",
        "endpoint": "/api/chat",
        "description": "操作指南 — PyTorch安装(不应触发可视化)",
        "expected_trigger": False,
        "expected_types": [],
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "PyTorch怎么安装？需要什么环境配置？",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": _make_judge(
            "PyTorch安装(不应可视化)",
            extra_context="附加信息: 这是一个操作指南/安装教程类问题，不适合也不需要可视化。如果系统正确判断不需要可视化(不返回blocks)，trigger_accuracy=1.0。如果错误地生成了可视化(none sensical)，trigger_accuracy=0.0。重点是content_fidelity: 文字回答是否提供了准确的安装步骤和环境配置指南。",
            pass_threshold=0.60,
        ),
    },
    # ═══════════════════ 边界: 模糊请求 ═══════════════════
    {
        "id": "vis_edge_overfit_underfit",
        "category": "可视化-边界",
        "endpoint": "/api/chat",
        "description": "模糊请求 — 过拟合vs欠拟合，有图最好",
        "expected_trigger": True,  # "有图最好"暗示了可视化需求
        "expected_types": ["chartjs", "mermaid", "svg"],
        "request": {
            "url": f"{API_BASE}/api/chat",
            "body": {
                "message": "讲一下过拟合和欠拟合的区别，最好能画个图对比一下。",
                "user_id": 1,
                "mode": "auto",
                "student_profile": DEFAULT_PROFILE,
            },
        },
        "judge": _make_judge(
            "过拟合vs欠拟合(有图最好)",
            extra_context="附加信息: 用户说'最好能画个图'，这是弱可视化请求。过拟合vs欠拟合的经典可视化是: 训练/验证误差随模型复杂度变化的U型曲线(chartjs line)或三张子图(欠拟合-刚好-过拟合)的概念对比。如果系统触发了可视化且内容正确，trigger_accuracy=1.0。如果未触发但有好的文字解释，trigger_accuracy=0.7(模糊请求，不触发也可接受)。",
            pass_threshold=0.55,
        ),
    },
]
