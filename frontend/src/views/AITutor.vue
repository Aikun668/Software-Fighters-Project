<template>
  <div class="ai-tutor">
    <!-- 头部 -->
    <div class="chat-header">
      <div class="header-info">
        <div class="avatar">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
            <circle cx="12" cy="10" r="3" fill="white"/>
            <path d="M9 16h6" stroke="white" stroke-width="2" stroke-linecap="round" fill="none"/>
          </svg>
        </div>
        <div class="title">
          <h2>AI智能答疑</h2>
          <p>有什么问题随时问我</p>
        </div>
      </div>
      <div class="header-actions">
        <el-button size="small" @click="clearChat">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
            <polyline points="3 6 5 6 21 6"/>
            <path d="M19 6v14c0 1.1-.9 2-2 2H7c-1.1 0-2-.9-2-2V6m3 0v14M16 6v14"/>
          </svg>
          清空对话
        </el-button>
      </div>
    </div>

    <!-- 消息列表 -->
    <div 
      class="message-container" 
      ref="messageContainer"
      @scroll="handleScroll"
      @wheel="handleScrollStart"
      @touchstart="handleScrollStart"
      @touchend="handleScrollEnd"
    >
      <div
        v-for="msg in messages"
        :key="msg.id"
        :class="['message-wrapper', `message-${msg.role}`]"
      >
        <div class="message-avatar">
          <svg v-if="msg.role === 'user'" viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <circle cx="12" cy="8" r="4"/>
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
            <circle cx="12" cy="10" r="3"/>
            <path d="M9 16h6" stroke="white" stroke-width="2" stroke-linecap="round" fill="none"/>
          </svg>
        </div>
        <div class="message-content">
          <div class="message-header">
            <span class="sender">{{ msg.role === 'user' ? '我' : 'AI助教' }}</span>
            <span class="time">{{ formatTime(msg.timestamp) }}</span>
          </div>
          <div
            class="message-body"
            :class="{ 'streaming': msg.streaming }"
            v-html="msg.streaming ? renderMarkdown(streamContent) : renderMarkdown(msg.content)"
          ></div>
          <div v-if="msg.streaming" class="typing-indicator">
            <span class="dot"></span>
            <span class="dot"></span>
            <span class="dot"></span>
          </div>
        </div>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="input-container">
      <div class="input-wrapper">
        <el-input
          v-model="inputMessage"
          type="textarea"
          :rows="2"
          placeholder="输入你的问题，我来帮你解答..."
          @keyup.enter.exact="sendMessage"
          :disabled="isStreaming"
        />
        <div class="input-actions">
          <el-button size="small" @click="sendMessage" :disabled="!inputMessage.trim() || isStreaming">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
              <path d="M22 2L11 13l-4-4-4 18 11-9 11 9-4-14z"/>
            </svg>
          </el-button>
        </div>
      </div>
      <div class="quick-questions">
        <span class="label">快速提问：</span>
        <el-button
          v-for="question in quickQuestions"
          :key="question"
          size="small"
          text
          @click="quickAsk(question)"
        >
          {{ question }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { marked } from 'marked'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
  streaming?: boolean
}

const messages = ref<ChatMessage[]>([])
const inputMessage = ref('')
const isStreaming = ref(false)
const streamContent = ref('')
const messageContainer = ref<HTMLElement | null>(null)
const shouldAutoScroll = ref(true)
const isUserScrolling = ref(false)

const quickQuestions = [
  '什么是机器学习？',
  '深度学习和机器学习有什么区别？',
  '如何学习Python？',
  '推荐一些AI学习资源'
]

const formatTime = (timestamp: number) => {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

const renderMarkdown = (content: string) => {
  return marked(content, {
    breaks: true,
    gfm: true
  })
}

const scrollToBottom = async (force = false) => {
  await nextTick()
  if (messageContainer.value && (shouldAutoScroll.value || force)) {
    messageContainer.value.scrollTop = messageContainer.value.scrollHeight
  }
}

const handleScroll = () => {
  if (!messageContainer.value) return
  
  const { scrollTop, scrollHeight, clientHeight } = messageContainer.value
  const isAtBottom = scrollHeight - scrollTop - clientHeight <= 50
  
  if (isUserScrolling.value) {
    if (isAtBottom) {
      shouldAutoScroll.value = true
    } else {
      shouldAutoScroll.value = false
    }
  }
}

const handleScrollStart = () => {
  isUserScrolling.value = true
}

const handleScrollEnd = () => {
  setTimeout(() => {
    isUserScrolling.value = false
    if (messageContainer.value) {
      const { scrollTop, scrollHeight, clientHeight } = messageContainer.value
      const isAtBottom = scrollHeight - scrollTop - clientHeight <= 50
      if (isAtBottom) {
        shouldAutoScroll.value = true
      }
    }
  }, 200)
}

const sendMessage = async () => {
  if (!inputMessage.value.trim() || isStreaming.value) return

  const userMessage: ChatMessage = {
    id: Date.now().toString(),
    role: 'user',
    content: inputMessage.value.trim(),
    timestamp: Date.now()
  }
  messages.value.push(userMessage)
  inputMessage.value = ''
  await scrollToBottom()

  isStreaming.value = true
  streamContent.value = ''
  
  const assistantMessage: ChatMessage = {
    id: (Date.now() + 1).toString(),
    role: 'assistant',
    content: '',
    timestamp: Date.now(),
    streaming: true
  }
  messages.value.push(assistantMessage)
  await scrollToBottom()

  simulateStreamResponse(userMessage.content)
}

const quickAsk = async (question: string) => {
  inputMessage.value = question
  await sendMessage()
}

const simulateStreamResponse = async (question: string) => {
  const responses: Record<string, string[]> = {
    '什么是机器学习？': [
      '机器学习是人工智能的一个分支，',
      '它使计算机能够从数据中学习并改进性能，',
      '而无需进行明确编程。\n\n',
      '**核心概念：**\n\n',
      '- **监督学习：** 从标记数据中学习\n',
      '- **无监督学习：** 从未标记数据中发现模式\n',
      '- **强化学习：** 通过试错学习最优策略\n\n',
      '**常见算法：**\n\n',
      '```python\n# 简单的线性回归示例\nfrom sklearn.linear_model import LinearRegression\n\nmodel = LinearRegression()\nmodel.fit(X_train, y_train)\npredictions = model.predict(X_test)\n```\n\n',
      '机器学习广泛应用于图像识别、自然语言处理、推荐系统等领域。'
    ],
    '深度学习和机器学习有什么区别？': [
      '深度学习是机器学习的一个子领域，',
      '使用多层神经网络来学习数据表示。\n\n',
      '**主要区别：**\n\n',
      '| 特性 | 机器学习 | 深度学习 |\n',
      '|------|----------|----------|\n',
      '| 数据需求 | 较少 | 大量 |\n',
      '| 特征工程 | 手动设计 | 自动学习 |\n',
      '| 计算资源 | 较低 | 较高（需要GPU） |\n',
      '| 适用场景 | 结构化数据 | 图像、语音、文本 |\n\n',
      '**深度学习架构：**\n\n',
      '- CNN（卷积神经网络）- 用于图像处理\n',
      '- RNN/LSTM - 用于序列数据\n',
      '- Transformer - 用于NLP任务'
    ],
    '如何学习Python？': [
      '学习Python是进入AI领域的第一步。\n\n',
      '**学习路径：**\n\n',
      '1. **基础语法**\n',
      '   - 变量、数据类型、运算符\n',
      '   - 条件语句、循环\n',
      '   - 函数、类和对象\n\n',
      '2. **常用库**\n',
      '   ```python\n   import numpy as np\n   import pandas as pd\n   import matplotlib.pyplot as plt\n   ```\n\n',
      '3. **实践项目**\n',
      '   - 数据处理和分析\n',
      '   - 简单的机器学习模型\n',
      '   - Web开发（可选）\n\n',
      '**推荐资源：**\n',
      '- Python官方文档\n',
      '- Coursera的Python课程\n',
      '- LeetCode练习'
    ],
    '推荐一些AI学习资源': [
      '好的，这里有一些优质的AI学习资源：\n\n',
      '**在线课程：**\n\n',
      '- [Coursera - 机器学习](https://www.coursera.org/learn/machine-learning)\n',
      '- [fast.ai](https://www.fast.ai/)\n',
      '- [DeepLearning.AI](https://www.deeplearning.ai/)\n\n',
      '**书籍：**\n\n',
      '- 《机器学习实战》\n',
      '- 《深度学习》（Goodfellow）\n',
      '- 《Python机器学习基础教程》\n\n',
      '**论文资源：**\n\n',
      '- [arXiv](https://arxiv.org/)\n',
      '- [Papers with Code](https://paperswithcode.com/)\n\n',
      '**实践平台：**\n\n',
      '- [Kaggle](https://www.kaggle.com/)\n',
      '- [Hugging Face](https://huggingface.co/)'
    ]
  }

  const defaultResponse = [
    '好的，我来帮你解答这个问题。\n\n',
    '根据我的知识，这个问题涉及到多个方面：\n\n',
    '**要点总结：**\n\n',
    '- 首先需要理解基本概念\n',
    '- 然后掌握相关技术\n',
    '- 最后通过实践巩固\n\n',
    '如果你有更具体的问题，欢迎继续提问！'
  ]

  const selectedResponse = responses[question] || defaultResponse

  let scrollInterval: ReturnType<typeof setInterval> | null = null
  
  scrollInterval = setInterval(() => {
    if (shouldAutoScroll.value) {
      scrollToBottom()
    }
  }, 200)

  for (const part of selectedResponse) {
    for (let i = 0; i < part.length; i++) {
      if (!isStreaming.value) break
      streamContent.value += part[i]
      messages.value[messages.value.length - 1].content = streamContent.value
      await new Promise(resolve => setTimeout(resolve, 20 + Math.random() * 40))
    }
  }

  if (scrollInterval) {
    clearInterval(scrollInterval)
  }
  
  await scrollToBottom()

  isStreaming.value = false
  messages.value[messages.value.length - 1].streaming = false
}

const clearChat = () => {
  messages.value = []
  const welcomeMessage: ChatMessage = {
    id: 'welcome',
    role: 'assistant',
    content: '你好！我是你的AI学习助手。有什么问题想了解吗？',
    timestamp: Date.now()
  }
  messages.value.push(welcomeMessage)
}

onMounted(() => {
  const welcomeMessage: ChatMessage = {
    id: 'welcome',
    role: 'assistant',
    content: '你好！我是你的AI学习助手。有什么问题想了解吗？',
    timestamp: Date.now()
  }
  messages.value.push(welcomeMessage)
})
</script>

<style scoped>
.ai-tutor {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: var(--bg-page);
}

.chat-header {
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-lg) var(--spacing-2xl);
  background: linear-gradient(135deg, var(--primary-color), var(--primary-dark));
}

.header-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 20px;
}

.title h2 {
  margin: 0 0 var(--spacing-xs) 0;
  font-size: var(--font-size-lg);
  color: white;
  font-weight: var(--font-weight-semibold);
}

.title p {
  margin: 0;
  font-size: var(--font-size-xs);
  color: rgba(255, 255, 255, 0.8);
}

.header-actions :deep(.el-button) {
  background: rgba(255, 255, 255, 0.2);
  border: none;
  color: white;
  border-radius: var(--radius-sm);
  
  &:hover {
    background: rgba(255, 255, 255, 0.3);
  }
}

.message-container {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-2xl);
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
}

.message-wrapper {
  display: flex;
  margin-bottom: var(--spacing-xl);
}

.message-user {
  flex-direction: row-reverse;
}

.message-user .message-content {
  align-items: flex-end;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin: 0 var(--spacing-md);
}

.message-user .message-avatar {
  background-color: var(--primary-color);
  color: white;
}

.message-wrapper:not(.message-user) .message-avatar {
  background-color: var(--success-color);
  color: white;
}

.message-content {
  max-width: 70%;
  display: flex;
  flex-direction: column;
}

.message-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-xs);
}

.sender {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.time {
  font-size: var(--font-size-xs);
  color: var(--text-placeholder);
}

.message-body {
  background-color: var(--bg-card);
  padding: var(--spacing-md) var(--spacing-lg);
  border-radius: var(--radius-md);
  line-height: var(--line-height-base);
  color: var(--text-secondary);
  box-shadow: var(--shadow-md);
}

.message-user .message-body {
  background-color: var(--primary-bg);
  color: var(--primary-color);
}

.message-body :deep(pre) {
  background-color: #1E293B;
  padding: 12px 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 12px 0;
}

.message-body :deep(code) {
  background-color: rgba(0, 0, 0, 0.05);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 14px;
}

.message-user .message-body :deep(code) {
  background-color: rgba(59, 130, 246, 0.2);
}

.message-body :deep(pre code) {
  background-color: transparent;
  padding: 0;
  color: #E2E8F0;
}

.message-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  border-radius: 8px;
  overflow: hidden;
}

.message-body :deep(th),
.message-body :deep(td) {
  border: 1px solid #E2E8F0;
  padding: 8px 12px;
  text-align: left;
}

.message-body :deep(th) {
  background-color: #F1F5F9;
  font-weight: 600;
}

.message-user .message-body :deep(th) {
  background-color: rgba(59, 130, 246, 0.1);
}

.message-body :deep(a) {
  color: #3B82F6;
}

.message-user .message-body :deep(a) {
  color: #2563EB;
}

.message-body :deep(blockquote) {
  border-left: 4px solid #3B82F6;
  padding-left: 12px;
  color: #64748B;
  margin: 12px 0;
}

.message-body :deep(h1),
.message-body :deep(h2),
.message-body :deep(h3) {
  margin: 16px 0 8px;
  font-weight: 600;
}

.message-body :deep(h1) {
  font-size: 18px;
}

.message-body :deep(h2) {
  font-size: 16px;
}

.message-body :deep(h3) {
  font-size: 14px;
}

.message-body :deep(ul),
.message-body :deep(ol) {
  padding-left: 24px;
  margin: 8px 0;
}

.message-body :deep(li) {
  margin: 4px 0;
}

.typing-indicator {
  display: flex;
  align-items: center;
  padding: 8px 0;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #94A3B8;
  margin-right: 4px;
  animation: typing 1.4s infinite ease-in-out;
}

.dot:nth-child(2) {
  animation-delay: 0.2s;
}

.dot:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typing {
  0%, 80%, 100% {
    opacity: 0.2;
  }
  40% {
    opacity: 1;
  }
}

.input-container {
  position: sticky;
  bottom: 0;
  z-index: 100;
  padding: var(--spacing-lg) var(--spacing-2xl);
  background-color: var(--bg-card);
  border-top: 1px solid var(--border-color);
}

.input-wrapper {
  display: flex;
  gap: var(--spacing-md);
}

.input-wrapper :deep(.el-textarea) {
  flex: 1;
}

.input-wrapper :deep(.el-input__wrapper) {
  border-radius: var(--radius-md);
  padding: var(--spacing-md) var(--spacing-lg);
  
  &:focus-within {
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
    border-color: var(--primary-color);
  }
}

.input-actions {
  display: flex;
  align-items: flex-end;
}

.input-actions :deep(.el-button) {
  height: 40px;
  width: 40px;
  border-radius: var(--radius-sm);
  background: linear-gradient(135deg, var(--primary-color), var(--primary-dark));
  border: none;
  color: white;
  
  &:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
  }
  
  &:disabled {
    background: var(--text-placeholder);
  }
}

.quick-questions {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  margin-top: var(--spacing-md);
  padding-top: var(--spacing-md);
  border-top: 1px solid #F1F5F9;
}

.label {
  font-size: var(--font-size-xs);
  color: var(--text-placeholder);
}

.quick-questions :deep(.el-button) {
  padding: var(--spacing-xs) var(--spacing-md);
  background-color: #F1F5F9;
  border-color: var(--border-color);
  color: var(--text-secondary);
  border-radius: var(--radius-full);
  
  &:hover {
    background-color: var(--primary-bg);
    border-color: var(--primary-color);
    color: var(--primary-color);
  }
}
</style>
