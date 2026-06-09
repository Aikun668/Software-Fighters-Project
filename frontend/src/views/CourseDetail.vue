<template>
  <div class="course-detail">
    <!-- 顶部导航栏 -->
    <div class="course-header">
      <div class="header-left">
        <el-button @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <div class="course-info">
          <h1>{{ course.title }}</h1>
          <p class="course-meta">{{ course.author }} · {{ course.date }}</p>
        </div>
      </div>
      <div class="header-right">
        <el-button size="small" @click="toggleToc">
          <el-icon><List /></el-icon>
          {{ showToc ? '隐藏目录' : '显示目录' }}
        </el-button>
        <el-button size="small" @click="printCourse">
          <el-icon><Printer /></el-icon>
          打印
        </el-button>
      </div>
    </div>

    <div class="content-wrapper">
      <!-- 左侧大纲 -->
      <aside class="sidebar" :class="{ 'hidden': !showToc }">
        <div class="sidebar-header">
          <h3>文档大纲</h3>
        </div>
        <nav class="toc-nav">
          <ul class="toc-list">
            <li
              v-for="(item, index) in tocItems"
              :key="index"
              :class="['toc-item', `level-${item.level}`, { active: activeSection === item.id }]"
              @click="scrollToSection(item.id)"
            >
              <a href="#" class="toc-link">
                <span class="toc-number">{{ item.number }}</span>
                <span class="toc-text">{{ item.text }}</span>
              </a>
            </li>
          </ul>
        </nav>
      </aside>

      <!-- 右侧内容区 -->
      <main class="main-content">
        <article class="article-content" v-html="renderedContent"></article>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  ArrowLeft,
  List,
  Printer
} from '@element-plus/icons-vue'
import { marked } from 'marked'

interface TocItem {
  id: string
  text: string
  level: number
  number: string
}

const course = ref({
  title: '深度学习入门指南',
  author: 'AI学习平台',
  date: '2024年1月15日'
})

const showToc = ref(true)
const activeSection = ref('')

const markdownContent = `# 深度学习入门指南

欢迎来到深度学习的世界！本指南将帮助你从零开始学习深度学习的基础知识。

## 1. 什么是深度学习？

深度学习是机器学习的一个子领域，它使用多层神经网络来学习数据的表示。

### 1.1 深度学习的特点

深度学习具有以下特点：

- **自动特征学习**：无需手动设计特征
- **处理复杂数据**：能够处理图像、语音、文本等非结构化数据
- **需要大量数据**：通常需要大规模数据集进行训练
- **需要强大计算资源**：通常需要GPU加速

### 1.2 深度学习的应用领域

深度学习在许多领域都有广泛应用：

1. **计算机视觉**：图像识别、目标检测、图像生成
2. **自然语言处理**：机器翻译、文本生成、情感分析
3. **语音识别**：语音转文字、语音合成
4. **推荐系统**：个性化推荐、广告投放

## 2. 神经网络基础

神经网络是深度学习的核心组件。

### 2.1 神经元模型

一个简单的神经元模型包括输入、权重、激活函数和输出：

\`\`\`python
import numpy as np

def sigmoid(x):
    return 1 / (1 + np.exp(-x))

class Neuron:
    def __init__(self, weights, bias):
        self.weights = weights
        self.bias = bias
    
    def forward(self, inputs):
        z = np.dot(inputs, self.weights) + self.bias
        return sigmoid(z)
\`\`\`

### 2.2 前向传播

前向传播是信息从输入层流向输出层的过程：

\`\`\`python
def forward_propagation(X, W1, b1, W2, b2):
    # 第一层隐藏层
    Z1 = np.dot(X, W1) + b1
    A1 = sigmoid(Z1)
    
    # 输出层
    Z2 = np.dot(A1, W2) + b2
    A2 = sigmoid(Z2)
    
    return A2
\`\`\`

## 3. 训练神经网络

训练神经网络需要定义损失函数和优化算法。

### 3.1 损失函数

常用的损失函数包括均方误差和交叉熵：

| 损失函数 | 公式 | 适用场景 |
|---------|------|----------|
| 均方误差 | MSE = (1/n) * Σ(y_pred - y_true)² | 回归问题 |
| 交叉熵 | CE = -Σ(y_true * log(y_pred)) | 分类问题 |

### 3.2 反向传播

反向传播是计算梯度并更新权重的过程：

\`\`\`python
def backward_propagation(X, Y, A1, A2, W2):
    m = X.shape[0]
    
    # 输出层误差
    dZ2 = A2 - Y
    dW2 = (1/m) * np.dot(A1.T, dZ2)
    db2 = (1/m) * np.sum(dZ2, axis=0, keepdims=True)
    
    # 隐藏层误差
    dZ1 = np.dot(dZ2, W2.T) * A1 * (1 - A1)
    dW1 = (1/m) * np.dot(X.T, dZ1)
    db1 = (1/m) * np.sum(dZ1, axis=0, keepdims=True)
    
    return dW1, db1, dW2, db2
\`\`\`

## 4. 常用深度学习框架

现在有许多优秀的深度学习框架可供选择：

### 4.1 PyTorch

PyTorch是Facebook开发的深度学习框架，以其动态计算图和Pythonic风格而闻名。

### 4.2 TensorFlow

TensorFlow是Google开发的深度学习框架，具有强大的部署能力。

### 4.3 Keras

Keras是一个高层神经网络API，可以运行在TensorFlow、CNTK或Theano之上。

## 5. 实践建议

学习深度学习需要理论和实践相结合：

### 5.1 学习路径

1. **数学基础**：线性代数、微积分、概率统计
2. **编程技能**：Python、NumPy、Pandas
3. **机器学习基础**：监督学习、无监督学习
4. **深度学习**：神经网络、CNN、RNN、Transformer

### 5.2 项目实践

建议从简单的项目开始：

- MNIST手写数字识别
- CIFAR-10图像分类
- 文本情感分析
- 简单的生成对抗网络

## 结语

深度学习是一个快速发展的领域，保持好奇心和持续学习是成功的关键！

> "深度学习不是魔法，而是数学和工程的结合。"

祝你学习愉快！
`

const tocItems = ref<TocItem[]>([])

const renderedContent = computed(() => {
  return marked(markdownContent, {
    breaks: true,
    gfm: true
  })
})

const parseToc = () => {
  const lines = markdownContent.split('\n')
  const items: TocItem[] = []
  const sectionNumbers: number[] = [0, 0, 0]

  for (const line of lines) {
    if (line.startsWith('# ')) {
      sectionNumbers[0]++
      sectionNumbers[1] = 0
      sectionNumbers[2] = 0
      items.push({
        id: line.slice(2).trim().toLowerCase().replace(/\s+/g, '-'),
        text: line.slice(2).trim(),
        level: 1,
        number: sectionNumbers[0].toString()
      })
    } else if (line.startsWith('## ')) {
      sectionNumbers[1]++
      sectionNumbers[2] = 0
      items.push({
        id: line.slice(3).trim().toLowerCase().replace(/\s+/g, '-'),
        text: line.slice(3).trim(),
        level: 2,
        number: `${sectionNumbers[0]}.${sectionNumbers[1]}`
      })
    } else if (line.startsWith('### ')) {
      sectionNumbers[2]++
      items.push({
        id: line.slice(4).trim().toLowerCase().replace(/\s+/g, '-'),
        text: line.slice(4).trim(),
        level: 3,
        number: `${sectionNumbers[0]}.${sectionNumbers[1]}.${sectionNumbers[2]}`
      })
    }
  }

  tocItems.value = items
}

const scrollToSection = (id: string) => {
  activeSection.value = id
  const element = document.getElementById(id)
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

const toggleToc = () => {
  showToc.value = !showToc.value
}

const goBack = () => {
  console.log('返回')
}

const printCourse = () => {
  window.print()
}

onMounted(() => {
  parseToc()
  
  document.addEventListener('scroll', () => {
    const headings = document.querySelectorAll('h1, h2, h3')
    headings.forEach((heading) => {
      const id = heading.getAttribute('id')
      if (id) {
        const rect = heading.getBoundingClientRect()
        if (rect.top <= 100) {
          activeSection.value = id
        }
      }
    })
  })
})
</script>

<style scoped>
.course-detail {
  min-height: 100vh;
  background-color: var(--bg-color);
}

.course-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background-color: var(--primary-color);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.course-info h1 {
  margin: 0 0 4px 0;
  font-size: 18px;
  color: var(--bg-color);
}

.course-meta {
  margin: 0;
  font-size: 13px;
  color: var(--bg-dark);
}

.content-wrapper {
  display: flex;
}

.sidebar {
  width: 280px;
  background-color: var(--card-bg);
  border-right: 1px solid var(--border-light);
  height: calc(100vh - 65px);
  overflow-y: auto;
  position: sticky;
  top: 65px;
}

.sidebar.hidden {
  display: none;
}

.sidebar-header {
  padding: 16px 20px;
  border-bottom: 1px solid #e4e7ed;
}

.sidebar-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}

.toc-nav {
  padding: 12px 0;
}

.toc-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.toc-item {
  padding: 8px 20px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.toc-item:hover {
  background-color: #f5f7fa;
}

.toc-item.active {
  background-color: #e8f4fd;
}

.toc-item.active .toc-link {
  color: #409eff;
}

.toc-item.level-2 {
  padding-left: 40px;
}

.toc-item.level-3 {
  padding-left: 60px;
}

.toc-link {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  color: #606266;
  font-size: 13px;
}

.toc-number {
  font-size: 12px;
  color: #909399;
  min-width: 24px;
}

.toc-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.main-content {
  flex: 1;
  padding: 24px 48px;
}

.article-content {
  max-width: 900px;
  margin: 0 auto;
  background-color: white;
  padding: 32px;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.article-content :deep(h1) {
  font-size: 24px;
  font-weight: 600;
  margin: 0 0 20px 0;
  padding-bottom: 12px;
  border-bottom: 2px solid #409eff;
}

.article-content :deep(h2) {
  font-size: 20px;
  font-weight: 600;
  margin: 28px 0 16px 0;
  color: #303133;
}

.article-content :deep(h3) {
  font-size: 16px;
  font-weight: 600;
  margin: 24px 0 12px 0;
  color: #404040;
}

.article-content :deep(p) {
  margin: 12px 0;
  line-height: 1.8;
  color: #606266;
}

.article-content :deep(ul),
.article-content :deep(ol) {
  margin: 12px 0;
  padding-left: 28px;
}

.article-content :deep(li) {
  margin: 8px 0;
  line-height: 1.6;
}

.article-content :deep(pre) {
  background-color: #2d2d2d;
  padding: 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 16px 0;
}

.article-content :deep(code) {
  background-color: #f5f7fa;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 14px;
  font-family: 'Monaco', 'Menlo', monospace;
}

.article-content :deep(pre code) {
  background-color: transparent;
  padding: 0;
  color: #e0e0e0;
  font-size: 13px;
}

.article-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 16px 0;
}

.article-content :deep(th),
.article-content :deep(td) {
  border: 1px solid #e4e7ed;
  padding: 10px 14px;
  text-align: left;
}

.article-content :deep(th) {
  background-color: #f5f7fa;
  font-weight: 600;
}

.article-content :deep(blockquote) {
  border-left: 4px solid #409eff;
  padding: 12px 16px;
  background-color: #fafafa;
  margin: 16px 0;
  color: #606266;
}

.article-content :deep(a) {
  color: #409eff;
  text-decoration: none;
}

.article-content :deep(a:hover) {
  text-decoration: underline;
}

@media print {
  .course-header,
  .sidebar {
    display: none;
  }
  
  .main-content {
    padding: 0;
  }
  
  .article-content {
    box-shadow: none;
    border: 1px solid #e4e7ed;
  }
}
</style>
