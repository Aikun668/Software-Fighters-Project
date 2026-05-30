# Self-Attention 完整计算流程

> 关联文档：04-transformer.md（Transformer整体架构）、05-nlp-llm.md（NLP演进）

## 为什么需要 Self-Attention

处理序列数据时，我们需要一种机制，让序列中的每个位置都能"看到"其他位置的信息，并按相关性动态加权整合。

传统 RNN 只能按时间步串行传递信息，长距离依赖容易丢失。Self-Attention（自注意力）允许序列中任意两个位置**直接交互**，计算量固定，且天然支持并行。

---

## 从一个句子开始：完整数值示例

以输入序列 `["学习", "人工", "智能"]` 为例，设嵌入维度 $d_{model} = 4$（实际中常用512或768，这里简化便于计算）。

### 步骤0：输入表示

每个 Token 经过 Embedding 层和位置编码后，得到对应向量。设：

$$X = \begin{bmatrix} 1 & 0 & 1 & 0 \\ 0 & 1 & 0 & 1 \\ 1 & 1 & 0 & 0 \end{bmatrix} \quad \text{（3个Token，每个4维）}$$

---

### 步骤1：生成 Q、K、V 矩阵

通过三个可训练的线性变换矩阵 $W^Q, W^K, W^V$（维度均为 $d_{model} \times d_k$，设 $d_k = 3$），将输入投影到查询、键、值三个空间：

$$Q = X W^Q, \quad K = X W^K, \quad V = X W^V$$

设（简化权重矩阵）：

$$W^Q = \begin{bmatrix} 1 & 0 & 1 \\ 1 & 0 & 0 \\ 0 & 0 & 1 \\ 0 & 1 & 1 \end{bmatrix}, \quad W^K = W^Q, \quad W^V = \begin{bmatrix} 0 & 2 & 0 \\ 0 & 3 & 0 \\ 1 & 0 & 3 \\ 1 & 1 & 0 \end{bmatrix}$$

计算 Q：

$$Q = X W^Q = \begin{bmatrix} 1 & 0 & 2 \\ 1 & 1 & 2 \\ 2 & 1 & 1 \end{bmatrix}$$

K 与 Q 相同（本例 $W^K = W^Q$），V：

$$V = X W^V = \begin{bmatrix} 1 & 2 & 3 \\ 1 & 4 & 0 \\ 0 & 5 & 3 \end{bmatrix}$$

**直觉解释：**
- **Q（Query，查询）**：当前位置想要"寻找"什么类型的信息
- **K（Key，键）**：每个位置"对外宣称"自己携带什么信息
- **V（Value，值）**：每个位置实际贡献的内容

---

### 步骤2：计算注意力分数（Attention Score）

用每个位置的 Q 与所有位置的 K 做点积，得到原始注意力分数矩阵：

$$\text{Score} = Q K^T = \begin{bmatrix} 1 & 0 & 2 \\ 1 & 1 & 2 \\ 2 & 1 & 1 \end{bmatrix} \begin{bmatrix} 1 & 1 & 2 \\ 0 & 1 & 1 \\ 2 & 2 & 1 \end{bmatrix}$$

$$= \begin{bmatrix} 1\cdot1+0\cdot0+2\cdot2 & 1\cdot1+0\cdot1+2\cdot2 & 1\cdot2+0\cdot1+2\cdot1 \\ 1\cdot1+1\cdot0+2\cdot2 & 1\cdot1+1\cdot1+2\cdot2 & 1\cdot2+1\cdot1+2\cdot1 \\ 2\cdot1+1\cdot0+1\cdot2 & 2\cdot1+1\cdot1+1\cdot2 & 2\cdot2+1\cdot1+1\cdot1 \end{bmatrix} = \begin{bmatrix} 5 & 5 & 4 \\ 5 & 6 & 5 \\ 4 & 5 & 6 \end{bmatrix}$$

矩阵的第 $i$ 行第 $j$ 列的值，表示**第 $i$ 个 Token 对第 $j$ 个 Token 的原始关注程度**。

---

### 步骤3：缩放（Scaling）

将分数除以 $\sqrt{d_k} = \sqrt{3} \approx 1.732$：

$$\text{Score}_{scaled} = \frac{QK^T}{\sqrt{d_k}} = \begin{bmatrix} 2.89 & 2.89 & 2.31 \\ 2.89 & 3.46 & 2.89 \\ 2.31 & 2.89 & 3.46 \end{bmatrix}$$

**为什么要缩放？**

当 $d_k$ 较大时，点积结果的数值会很大（量级约为 $d_k$），导致 Softmax 的输入进入饱和区（梯度极小），训练困难。除以 $\sqrt{d_k}$ 可将方差稳定在1左右，确保 Softmax 工作在有效区间。

---

### 步骤4：Softmax 归一化

对缩放后的分数矩阵，对**每一行**独立做 Softmax，得到注意力权重（每行之和为1）：

$$\text{Softmax}(z_i) = \frac{e^{z_i}}{\sum_j e^{z_j}}$$

对第一行 $[2.89, 2.89, 2.31]$：

$$e^{2.89} \approx 17.99, \quad e^{2.89} \approx 17.99, \quad e^{2.31} \approx 10.07$$

$$\text{sum} = 17.99 + 17.99 + 10.07 = 46.05$$

$$\text{Attention}[0] = [0.391, 0.391, 0.219]$$

对所有行计算后：

$$A = \text{Softmax}\left(\frac{QK^T}{\sqrt{d_k}}\right) \approx \begin{bmatrix} 0.391 & 0.391 & 0.219 \\ 0.298 & 0.404 & 0.298 \\ 0.219 & 0.391 & 0.391 \end{bmatrix}$$

**解读：** 第一行 $[0.391, 0.391, 0.219]$ 表示"学习"这个Token，以39.1%的注意力关注自身，以39.1%的注意力关注"人工"，以21.9%的注意力关注"智能"。

---

### 步骤5：加权求和得到输出

将注意力权重矩阵 $A$ 与 V 矩阵相乘：

$$\text{Output} = A \cdot V = \begin{bmatrix} 0.391 & 0.391 & 0.219 \\ 0.298 & 0.404 & 0.298 \\ 0.219 & 0.391 & 0.391 \end{bmatrix} \begin{bmatrix} 1 & 2 & 3 \\ 1 & 4 & 0 \\ 0 & 5 & 3 \end{bmatrix}$$

计算第一行（"学习"的新表示）：
$$\text{Out}[0] = 0.391 \times [1,2,3] + 0.391 \times [1,4,0] + 0.219 \times [0,5,3]$$
$$= [0.391, 0.782, 1.173] + [0.391, 1.564, 0] + [0, 1.095, 0.657]$$
$$\approx [0.782, 3.441, 1.830]$$

输出矩阵中每个 Token 的向量，已经融合了整个序列的上下文信息，而不再是孤立的词向量。

---

## 完整公式总结

$$\text{Attention}(Q, K, V) = \text{Softmax}\left(\frac{QK^T}{\sqrt{d_k}}\right) V$$

五个步骤的映射：

| 步骤 | 操作 | 作用 |
|---|---|---|
| 1 | $Q=XW^Q,\ K=XW^K,\ V=XW^V$ | 投影到查询/键/值空间 |
| 2 | $QK^T$ | 计算两两相关性（原始分数） |
| 3 | $\div \sqrt{d_k}$ | 防止梯度消失，稳定训练 |
| 4 | $\text{Softmax}(\cdot)$ | 归一化为概率分布（注意力权重） |
| 5 | $(\cdot) V$ | 按权重聚合信息，输出上下文感知表示 |

---

## Multi-Head Attention：多角度关注

单头注意力只能从一个角度捕捉关系。多头注意力（Multi-Head Attention）将 Q、K、V 分别投影到 $h$ 个子空间，并行计算 $h$ 个注意力头：

$$\text{head}_i = \text{Attention}(QW_i^Q, KW_i^K, VW_i^V)$$

$$\text{MultiHead}(Q,K,V) = \text{Concat}(\text{head}_1, ..., \text{head}_h) W^O$$

其中 $W^O$ 是输出投影矩阵。

**为什么有效？** 不同的头可以专注于不同类型的依赖关系。例如一个头可能学到主谓关系，另一个头学到修饰关系，另一个头学到指代关系。可视化研究表明，不同注意力头确实关注了不同的语言现象。

**维度关系：** 每个头的维度 $d_k = d_{model} / h$，总计算量与单头基本相同。原始 Transformer 使用 $h=8$ 个头，$d_{model}=512$，每头 $d_k=64$。

---

## Masked Attention：解码器中的因果掩码

在 Transformer 解码器生成文本时，第 $t$ 步不能"看到"第 $t+1$ 步及以后的内容（否则等于作弊）。

实现方式：在计算 $\text{Softmax}$ 前，将上三角区域的分数设为 $-\infty$：

$$\text{Score}_{masked} = \begin{bmatrix} 5 & -\infty & -\infty \\ 5 & 6 & -\infty \\ 4 & 5 & 6 \end{bmatrix}$$

经过 Softmax 后，$-\infty$ 对应的权重趋近于0，即每个位置只能关注自身及之前的位置。这是 GPT 等自回归生成模型的核心机制。

---

## GPT vs BERT 架构对比

| 维度 | BERT | GPT |
|---|---|---|
| 架构 | 仅 Encoder | 仅 Decoder |
| 注意力类型 | 双向 Self-Attention（全序列互看） | 因果 Masked Self-Attention（只看前文） |
| 预训练目标 | 掩码语言模型（MLM）：预测被遮住的词 | 自回归语言模型（CLM）：预测下一个词 |
| 输入处理方式 | 一次处理完整句子 | 从左到右逐步生成 |
| 擅长任务 | 理解类：分类、问答、NER | 生成类：对话、写作、代码生成 |
| 代表模型 | BERT、RoBERTa、ALBERT | GPT-2/3/4、LLaMA、DeepSeek |

**关键差异的本质：**
- BERT 的双向注意力让每个词能同时参考前后文，理解更深，但无法自然地做序列生成（不能"从无到有"逐步输出）。
- GPT 的因果掩码让模型只看前文，天然适配"根据已有内容生成下一个词"的自回归范式。

---

## 计算复杂度

Self-Attention 的时间和空间复杂度均为 $O(n^2 d)$，其中 $n$ 是序列长度，$d$ 是维度。

当序列很长时（如长文档处理），$n^2$ 项会成为瓶颈。研究界提出多种改进：
- **Longformer**：局部窗口注意力 + 全局特殊 Token，复杂度降至 $O(n)$
- **FlashAttention**：通过分块计算和 IO 优化，在不改变数学等价性的前提下大幅提升速度和显存效率
- **稀疏注意力（Sparse Attention）**：只计算最重要的 Token 对，跳过不相关组合

---

## 总结

Self-Attention 通过 Q、K、V 三元组机制，实现了序列内任意位置的直接信息交互。五步计算流程（投影→点积→缩放→Softmax→加权求和）是现代大语言模型的计算核心。理解这一机制，是理解 BERT、GPT 及后续所有 Transformer 变体的基础。
