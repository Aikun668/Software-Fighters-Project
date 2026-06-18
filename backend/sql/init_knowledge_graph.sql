-- =============================================
-- 知识图谱：建表 + 种子数据
-- =============================================

CREATE TABLE IF NOT EXISTS knowledge_graph_nodes (
    id VARCHAR(50) PRIMARY KEY COMMENT '节点ID（来自知识图谱设计）',
    name VARCHAR(100) NOT NULL COMMENT '节点名称',
    description TEXT COMMENT '节点描述',
    difficulty INT DEFAULT 3 COMMENT '难度 1-5',
    category VARCHAR(50) COMMENT '分类：基础/ML/DL/NLP/LLM',
    course_id VARCHAR(50) DEFAULT 'ai_intro' COMMENT '课程ID',
    sub_concepts JSON COMMENT '子概念列表 [{name, mastery, tag}]',
    INDEX idx_course_id (course_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识图谱节点';

CREATE TABLE IF NOT EXISTS knowledge_graph_edges (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
    source VARCHAR(50) NOT NULL COMMENT '源节点ID',
    target VARCHAR(50) NOT NULL COMMENT '目标节点ID',
    relation VARCHAR(20) NOT NULL COMMENT '关系：depends_on / extends / parallel',
    rationale VARCHAR(200) COMMENT '关系说明',
    course_id VARCHAR(50) DEFAULT 'ai_intro' COMMENT '课程ID',
    INDEX idx_source (source),
    INDEX idx_target (target),
    INDEX idx_course_id (course_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识图谱边';

-- =============================================
-- AI入门 种子数据（从 knowledge_graph_skeleton.json 迁移）
-- =============================================

INSERT INTO knowledge_graph_nodes (id, name, description, difficulty, category, course_id, sub_concepts) VALUES
('ai_overview', 'AI 概述', '人工智能的定义、发展历程、核心分支（ML/DL/NLP/CV）及典型应用场景', 1, '基础', 'ai_intro',
  '[{"name":"AI 定义与图灵测试","mastery":0,"tag":"未学"},{"name":"AI 发展三阶段","mastery":0,"tag":"未学"},{"name":"ML/DL/NLP/CV 分支","mastery":0,"tag":"未学"}]'),

('ml_basics', '机器学习基础', '监督学习、无监督学习、强化学习的基本范式，训练/验证/测试集划分，偏差-方差权衡', 2, 'ML', 'ai_intro',
  '[{"name":"监督/无监督/强化学习","mastery":0,"tag":"未学"},{"name":"训练集/验证集/测试集","mastery":0,"tag":"未学"},{"name":"偏差-方差权衡","mastery":0,"tag":"未学"},{"name":"特征工程基础","mastery":0,"tag":"未学"}]'),

('dl_basics', '深度学习基础', '神经网络的基本结构、激活函数、前向传播、损失函数、优化器与训练流程', 3, 'DL', 'ai_intro',
  '[{"name":"神经元与前向传播","mastery":0,"tag":"未学"},{"name":"激活函数（ReLU/Sigmoid/Tanh）","mastery":0,"tag":"未学"},{"name":"损失函数与优化器","mastery":0,"tag":"未学"},{"name":"反向传播直觉理解","mastery":0,"tag":"未学"}]'),

('transformer', 'Transformer 架构', 'Encoder-Decoder 结构、多头注意力、位置编码、LayerNorm、残差连接', 4, 'LLM', 'ai_intro',
  '[{"name":"Encoder-Decoder 结构","mastery":0,"tag":"未学"},{"name":"多头注意力机制","mastery":0,"tag":"未学"},{"name":"位置编码原理","mastery":0,"tag":"未学"},{"name":"残差连接与 LayerNorm","mastery":0,"tag":"未学"},{"name":"训练与推理流程","mastery":0,"tag":"未学"}]'),

('nlp_llm', 'NLP 与 LLM', '语言模型演进（RNN→LSTM→Transformer→GPT）、预训练+微调范式、Prompt Engineering', 3, 'NLP', 'ai_intro',
  '[{"name":"语言模型演进史","mastery":0,"tag":"未学"},{"name":"预训练+微调范式","mastery":0,"tag":"未学"},{"name":"Prompt Engineering","mastery":0,"tag":"未学"},{"name":"LLM 能力与局限","mastery":0,"tag":"未学"}]'),

('backprop', '反向传播推导', '链式法则的矩阵形式推导、梯度在计算图中的反向流动、常见激活函数的梯度', 5, 'DL', 'ai_intro',
  '[{"name":"链式法则矩阵形式","mastery":0,"tag":"未学"},{"name":"常见激活函数梯度","mastery":0,"tag":"未学"},{"name":"梯度消失/爆炸","mastery":0,"tag":"未学"},{"name":"数值稳定性技巧","mastery":0,"tag":"未学"}]'),

('overfitting', '过拟合与正则化', '过拟合/欠拟合的诊断方法、L1/L2正则化、Dropout、Early Stopping、数据增强', 3, 'ML', 'ai_intro',
  '[{"name":"过拟合诊断方法","mastery":0,"tag":"未学"},{"name":"L1/L2 正则化","mastery":0,"tag":"未学"},{"name":"Dropout 与 Early Stopping","mastery":0,"tag":"未学"},{"name":"数据增强技术","mastery":0,"tag":"未学"}]'),

('self_attention', 'Self-Attention 详解', 'Q/K/V 线性变换、缩放点积注意力、多头并行、注意力权重可视化', 5, 'LLM', 'ai_intro',
  '[{"name":"Q/K/V 线性变换","mastery":0,"tag":"未学"},{"name":"缩放点积注意力","mastery":0,"tag":"未学"},{"name":"多头并行机制","mastery":0,"tag":"未学"},{"name":"注意力权重可视化","mastery":0,"tag":"未学"}]'),

('gradient_variants', '梯度下降变体', 'BGD/SGD/Mini-batch 的区别与权衡、Momentum、Adam、RMSprop 的更新公式与适应场景', 4, 'ML', 'ai_intro',
  '[{"name":"BGD/SGD/Mini-batch 区别","mastery":0,"tag":"未学"},{"name":"Momentum 加速","mastery":0,"tag":"未学"},{"name":"Adam 自适应学习率","mastery":0,"tag":"未学"},{"name":"学习率调度策略","mastery":0,"tag":"未学"}]'),

('cnn', 'CNN 卷积神经网络', '卷积层/池化层/全连接层的结构、感受野、经典架构（LeNet/AlexNet/ResNet）', 4, 'DL', 'ai_intro',
  '[{"name":"卷积层与感受野","mastery":0,"tag":"未学"},{"name":"池化层与全连接层","mastery":0,"tag":"未学"},{"name":"LeNet/AlexNet/ResNet","mastery":0,"tag":"未学"},{"name":"CNN 训练技巧","mastery":0,"tag":"未学"}]');

INSERT INTO knowledge_graph_edges (source, target, relation, rationale, course_id) VALUES
('ai_overview',       'ml_basics',         'depends_on', 'ML 是 AI 的核心方法', 'ai_intro'),
('ml_basics',         'dl_basics',         'depends_on', '深度学习是 ML 的子领域', 'ai_intro'),
('ml_basics',         'overfitting',       'depends_on', '过拟合是 ML 中的核心问题', 'ai_intro'),
('ml_basics',         'gradient_variants', 'depends_on', '梯度下降是 ML 的核心优化方法', 'ai_intro'),
('dl_basics',         'cnn',               'depends_on', 'CNN 是深度学习的经典架构', 'ai_intro'),
('dl_basics',         'backprop',          'depends_on', '反向传播是深度学习训练的核心', 'ai_intro'),
('dl_basics',         'transformer',       'extends',    'Transformer 是深度学习在序列建模的延伸', 'ai_intro'),
('gradient_variants', 'backprop',          'depends_on', '反向传播基于梯度下降', 'ai_intro'),
('overfitting',       'backprop',          'parallel',   '训练深度网络的两大挑战', 'ai_intro'),
('backprop',          'cnn',               'depends_on', 'CNN 训练依赖反向传播', 'ai_intro'),
('transformer',       'self_attention',    'depends_on', 'Self-Attention 是 Transformer 的核心机制', 'ai_intro'),
('transformer',       'nlp_llm',           'depends_on', 'LLM 基于 Transformer 架构', 'ai_intro'),
('self_attention',    'nlp_llm',           'depends_on', '注意力机制是 LLM 的关键技术', 'ai_intro'),
('cnn',               'transformer',       'extends',    '从 CNN 到 Transformer：序列建模的演进', 'ai_intro'),
('dl_basics',         'nlp_llm',           'extends',    'LLM 训练需要深度学习基础', 'ai_intro');
