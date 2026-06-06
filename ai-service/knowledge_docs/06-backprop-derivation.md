# 反向传播算法：完整数值推导

> 关联文档：03-deep-learning.md（神经网络基础）、09-gradient-descent-variants.md（梯度下降变体）

## 为什么需要反向传播

神经网络训练的本质是找到一组参数 $W$，使损失函数 $L$ 最小化。梯度下降需要计算 $\frac{\partial L}{\partial W}$，但神经网络是多层嵌套函数，参数分散在每一层。反向传播（Backpropagation）利用**链式法则（Chain Rule）**，高效计算每一层每个参数对最终损失的偏导数。

核心思想：从输出层往输入层方向，逐层传播"误差信号"，每层只需用上一层传来的梯度乘以本层的局部梯度，即可得到本层参数的梯度。

---

## 准备：一个最小网络

用一个具体的两层网络做完整数值推导，避免停留在抽象符号。

**网络结构：**
- 输入层：2个神经元，输入 $x_1 = 0.05,\ x_2 = 0.10$
- 隐藏层：2个神经元，激活函数 Sigmoid
- 输出层：2个神经元，激活函数 Sigmoid
- 真实标签：$y_1 = 0.01,\ y_2 = 0.99$
- 损失函数：均方误差（MSE）

**初始权重（人工设定，便于验证）：**

$$W^{(1)} = \begin{bmatrix} w_1=0.15 & w_2=0.20 \\ w_3=0.25 & w_4=0.30 \end{bmatrix}, \quad b^{(1)} = \begin{bmatrix} b_1=0.35 \\ b_2=0.35 \end{bmatrix}$$

$$W^{(2)} = \begin{bmatrix} w_5=0.40 & w_6=0.45 \\ w_7=0.50 & w_8=0.55 \end{bmatrix}, \quad b^{(2)} = \begin{bmatrix} b_3=0.60 \\ b_4=0.60 \end{bmatrix}$$

其中 $w_1$ 表示输入 $x_1$ 到隐藏神经元 $h_1$ 的权重，以此类推。

---

## 第一步：前向传播（Forward Pass）

### 隐藏层计算

神经元 $h_1$ 的净输入（加权求和）：
$$z_{h1} = w_1 \cdot x_1 + w_3 \cdot x_2 + b_1 = 0.15 \times 0.05 + 0.25 \times 0.10 + 0.35 = 0.3775$$

神经元 $h_2$ 的净输入：
$$z_{h2} = w_2 \cdot x_1 + w_4 \cdot x_2 + b_1 = 0.20 \times 0.05 + 0.30 \times 0.10 + 0.35 = 0.3925$$

经过 Sigmoid 激活函数 $\sigma(z) = \frac{1}{1+e^{-z}}$：
$$a_{h1} = \sigma(0.3775) = \frac{1}{1+e^{-0.3775}} \approx 0.5933$$

$$a_{h2} = \sigma(0.3925) \approx 0.5969$$

### 输出层计算

输出神经元 $o_1$ 的净输入：
$$z_{o1} = w_5 \cdot a_{h1} + w_7 \cdot a_{h2} + b_3 = 0.40 \times 0.5933 + 0.50 \times 0.5969 + 0.60 \approx 1.1059$$

输出神经元 $o_2$ 的净输入：
$$z_{o2} = w_6 \cdot a_{h1} + w_8 \cdot a_{h2} + b_3 = 0.45 \times 0.5933 + 0.55 \times 0.5969 + 0.60 \approx 1.2249$$

经过 Sigmoid 激活：
$$\hat{y}_1 = a_{o1} = \sigma(1.1059) \approx 0.7514$$

$$\hat{y}_2 = a_{o2} = \sigma(1.2249) \approx 0.7729$$

### 计算损失

$$L = \frac{1}{2}\left[(\hat{y}_1 - y_1)^2 + (\hat{y}_2 - y_2)^2\right]$$

$$L = \frac{1}{2}\left[(0.7514 - 0.01)^2 + (0.7729 - 0.99)^2\right]$$

$$L = \frac{1}{2}(0.5513 + 0.0471) \approx 0.2984$$

---

## 第二步：反向传播（Backward Pass）

目标：计算 $\frac{\partial L}{\partial w_5}$，即损失对权重 $w_5$ 的偏导数。

### 链式法则展开

$$\frac{\partial L}{\partial w_5} = \frac{\partial L}{\partial a_{o1}} \cdot \frac{\partial a_{o1}}{\partial z_{o1}} \cdot \frac{\partial z_{o1}}{\partial w_5}$$

**第一项：损失对输出激活值的偏导**

$$\frac{\partial L}{\partial a_{o1}} = \frac{\partial}{\partial a_{o1}} \frac{1}{2}(a_{o1} - y_1)^2 = a_{o1} - y_1 = 0.7514 - 0.01 = 0.7414$$

**第二项：Sigmoid 的导数**

Sigmoid 函数有一个极为优雅的性质：
$$\frac{d\sigma(z)}{dz} = \sigma(z)(1 - \sigma(z))$$

因此：
$$\frac{\partial a_{o1}}{\partial z_{o1}} = a_{o1}(1 - a_{o1}) = 0.7514 \times (1 - 0.7514) = 0.7514 \times 0.2486 \approx 0.1868$$

**第三项：净输入对权重的偏导**

$$\frac{\partial z_{o1}}{\partial w_5} = a_{h1} = 0.5933$$

**合并：**
$$\frac{\partial L}{\partial w_5} = 0.7414 \times 0.1868 \times 0.5933 \approx 0.0822$$

### 定义误差项 $\delta$（Error Term）

为了简化符号，定义输出层误差项：
$$\delta_{o1} = \frac{\partial L}{\partial a_{o1}} \cdot \frac{\partial a_{o1}}{\partial z_{o1}} = (a_{o1} - y_1) \cdot a_{o1}(1-a_{o1})$$

则任意输出层权重的梯度为：
$$\frac{\partial L}{\partial w_k} = \delta_{o} \cdot a_{h}$$

这是一个清晰的规律：**输出层权重的梯度 = 该层误差项 × 该权重的输入端激活值**。

同理计算 $\delta_{o2}$：
$$\delta_{o2} = (0.7729 - 0.99) \times 0.7729 \times (1-0.7729) = -0.2171 \times 0.1755 \approx -0.0381$$

---

## 第三步：误差向隐藏层传播

现在计算 $\frac{\partial L}{\partial w_1}$，即损失对第一层权重 $w_1$ 的偏导。

路径更长，涉及的链式法则：
$$\frac{\partial L}{\partial w_1} = \left(\frac{\partial L}{\partial a_{h1}}\right) \cdot \frac{\partial a_{h1}}{\partial z_{h1}} \cdot \frac{\partial z_{h1}}{\partial w_1}$$

### 计算隐藏层的误差信号

$a_{h1}$ 同时影响 $o_1$ 和 $o_2$，因此：
$$\frac{\partial L}{\partial a_{h1}} = \frac{\partial L}{\partial z_{o1}} \cdot \frac{\partial z_{o1}}{\partial a_{h1}} + \frac{\partial L}{\partial z_{o2}} \cdot \frac{\partial z_{o2}}{\partial a_{h1}}$$

$$= \delta_{o1} \cdot w_5 + \delta_{o2} \cdot w_6 = 0.1386 \times 0.40 + (-0.0381) \times 0.45$$

$$\approx 0.0554 - 0.0171 = 0.0383$$

其中 $\delta_{o1} = 0.7414 \times 0.1868 = 0.1386$（未乘 $a_{h1}$ 的版本）。

### 隐藏层误差项

$$\delta_{h1} = \frac{\partial L}{\partial a_{h1}} \cdot a_{h1}(1-a_{h1}) = 0.0383 \times 0.5933 \times (1-0.5933)$$

$$= 0.0383 \times 0.2412 \approx 0.00924$$

### 最终梯度

$$\frac{\partial L}{\partial w_1} = \delta_{h1} \cdot x_1 = 0.00924 \times 0.05 \approx 0.000462$$

---

## 第四步：权重更新

设学习率 $\alpha = 0.5$，则权重更新规则：
$$w \leftarrow w - \alpha \cdot \frac{\partial L}{\partial w}$$

$$w_1 \leftarrow 0.15 - 0.5 \times 0.000462 = 0.14977$$

$$w_5 \leftarrow 0.40 - 0.5 \times 0.0822 = 0.3589$$

经过一轮更新后，损失会从 0.2984 轻微下降。多次迭代后，网络输出将逐渐趋近目标值 $[0.01, 0.99]$。

---

## 梯度消失问题的数值理解

观察 Sigmoid 的导数：$\sigma'(z) = \sigma(z)(1-\sigma(z))$，其最大值在 $z=0$ 时为 $0.25$。

在深层网络中，每向前传播一层，梯度都要乘以一个 $\leq 0.25$ 的因子。若网络有10层，梯度经过10次相乘：

$$0.25^{10} \approx 9.5 \times 10^{-7}$$

接近于零，靠近输入层的参数几乎得不到任何更新信号，这就是**梯度消失（Vanishing Gradient）**问题的数值本质。

**ReLU 的解决思路：** $\text{ReLU}'(z) = 1$（当 $z > 0$），梯度不会因激活函数而衰减，从根本上缓解了梯度消失。

---

## 总结：反向传播的三个关键等式

| 位置 | 误差项 | 权重梯度 |
|---|---|---|
| 输出层 | $\delta^{out} = (a^{out} - y) \cdot \sigma'(z^{out})$ | $\frac{\partial L}{\partial w} = \delta^{out} \cdot a^{prev}$ |
| 隐藏层 | $\delta^{hidden} = (W^{next T} \delta^{next}) \cdot \sigma'(z^{hidden})$ | $\frac{\partial L}{\partial w} = \delta^{hidden} \cdot a^{prev}$ |
| 偏置 | 同上，但输入端为 1 | $\frac{\partial L}{\partial b} = \delta$ |

反向传播的精髓在于：每层的误差项 $\delta$ 由下一层的误差项"反向加权求和"得到，计算量与参数数量成线性关系，极为高效。
