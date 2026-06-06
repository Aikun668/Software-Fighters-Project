\# Transformer与自注意力机制



\## 背景：RNN的瓶颈



在Transformer出现之前，自然语言处理（NLP）领域处理序列数据的主流架构是循环神经网络（RNN）及其变体LSTM、GRU。这类架构存在两个核心问题：



1\. \*\*串行计算\*\*：RNN必须按时间步依次计算，无法并行，训练大规模数据时效率极低。

2\. \*\*长距离依赖弱\*\*：即使LSTM有所改善，序列很长时，早期信息仍会随传播层数增加而衰减。



2017年，Google团队在论文《Attention is All You Need》中提出了Transformer模型，彻底抛弃了循环结构，完全基于注意力机制（Attention Mechanism），一举解决了上述两个问题，并成为此后GPT、BERT等大语言模型的基础架构。



\## 注意力机制（Attention Mechanism）



注意力机制的核心思想是：在处理序列中的某个位置时，模型不应对所有其他位置一视同仁，而应根据相关性动态分配"注意力权重"，重点关注最相关的位置。



以机器翻译为例，翻译"我爱北京"中的"北京"时，模型应将更多注意力放在原句中"北京"对应的位置，而非均匀分散。



\## Self-Attention（自注意力机制）



Self-Attention是Transformer的核心创新，允许序列中每个位置与序列中所有其他位置直接交互，计算相互之间的关联强度。



\*\*计算步骤：\*\*



对于输入序列中的每个词向量（Token Embedding），通过三个可训练的线性变换矩阵生成三个向量：

\- \*\*Query（Q，查询向量）\*\*：代表当前位置"想要查询什么"

\- \*\*Key（K，键向量）\*\*：代表每个位置"能提供什么信息"

\- \*\*Value（V，值向量）\*\*：代表每个位置实际携带的内容



注意力权重计算（Scaled Dot-Product Attention，缩放点积注意力）：



$$\\text{Attention}(Q, K, V) = \\text{Softmax}\\left(\\frac{QK^T}{\\sqrt{d\_k}}\\right)V$$



\- $QK^T$ 计算查询与每个键的点积（相似度）

\- 除以 $\\sqrt{d\_k}$（键向量维度的平方根）是为了防止点积值过大导致Softmax梯度消失

\- Softmax归一化后得到权重分布，与V加权求和，得到该位置的输出



\*\*直觉理解\*\*：Query是"问题"，Key是"索引"，Value是"答案"。计算Query与所有Key的匹配程度，按匹配程度加权组合所有Value，就得到了当前位置综合了全局信息的新表示。



\## Multi-Head Attention（多头注意力）



单个注意力头只能从一个"角度"关注序列关系（如语法关系），而多头注意力（Multi-Head Attention）将Q、K、V分别投影到多个子空间，并行运行多个注意力头，每个头关注不同类型的依赖关系，最后拼接所有头的输出并进行线性变换。



$$\\text{MultiHead}(Q,K,V) = \\text{Concat}(\\text{head}\_1, ..., \\text{head}\_h)W^O$$



多头注意力使模型能够同时捕捉词语之间的语义、句法、共指等多种关系。



\## 位置编码（Positional Encoding）



Self-Attention本身对序列顺序是无感知的——"我爱你"和"你爱我"会得到相同的注意力分布。因此Transformer在输入词向量中加入位置编码（Positional Encoding），将序列中每个位置的绝对或相对位置信息注入模型。



原始论文使用正弦/余弦函数编码位置，后续模型（如BERT）改用可学习的位置嵌入（Learnable Positional Embedding）。



\## Transformer整体架构



Transformer由编码器（Encoder）和解码器（Decoder）两部分组成，各由N层相同结构堆叠而成（原始论文N=6）。



\*\*编码器（Encoder）每层包含：\*\*

1\. Multi-Head Self-Attention：序列内所有位置互相关注

2\. 前馈神经网络（Feed-Forward Network，FFN）：对每个位置独立进行非线性变换

3\. 残差连接（Residual Connection）+ 层归一化（Layer Normalization）



\*\*解码器（Decoder）每层包含：\*\*

1\. Masked Multi-Head Self-Attention：解码器自注意力，通过掩码（Mask）防止当前位置"看到"未来位置（避免信息泄露）

2\. Cross-Attention（交叉注意力）：Query来自解码器，Key和Value来自编码器输出，实现编解码器信息交互

3\. 前馈神经网络 + 残差连接 + 层归一化



\## 为什么Transformer优于RNN



| 对比维度 | RNN/LSTM | Transformer |

|---|---|---|

| 并行计算 | 无法并行（时序依赖） | 完全并行（训练速度快） |

| 长距离依赖 | 随距离增加而衰减 | 任意两位置直接交互 |

| 计算复杂度 | O(n)（序列长度） | O(n²)（注意力矩阵） |

| 可扩展性 | 扩展困难 | 易于扩展到大规模参数 |



Transformer的O(n²)复杂度在序列极长时（如长文档）是一个挑战，研究界提出了Longformer、FlashAttention等改进方案。



\## Transformer的影响与延伸



Transformer发布后迅速成为NLP领域的主流架构，并延伸到计算机视觉（Vision Transformer，ViT）、语音处理、多模态学习等几乎所有AI子领域。



\- \*\*BERT（2018）\*\*：仅使用Encoder，双向注意力，通过掩码语言模型预训练，在多项NLP任务上刷新SOTA。

\- \*\*GPT系列（2018-至今）\*\*：仅使用Decoder，单向注意力，通过自回归生成预训练，GPT-4已具备强大的通用推理能力。

\- \*\*T5、LLaMA、DeepSeek\*\*等：各类在Transformer基础上的大语言模型持续涌现。



\## 总结



Transformer通过Self-Attention机制实现了序列中任意位置的直接全局交互，彻底解决了RNN的串行计算和长距离依赖问题。多头注意力、位置编码和残差连接共同构成了现代大语言模型的基础架构。理解Transformer是理解GPT、BERT等当代AI技术的必要前提。

