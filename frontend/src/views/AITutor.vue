<template>
  <div class="ai-tutor">
    <!-- 头部 -->
    <div class="chat-header">
      <div class="header-info">
        <div class="avatar">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
        </div>
        <div class="title">
          <h2>AI 智能答疑</h2>
          <p>DeepTutor · 随时为你解答问题</p>
        </div>
      </div>
      <div class="header-actions">
        <button class="action-btn" @click="clearChat" title="清空对话">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="3 6 5 6 21 6"/>
            <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6m3 0V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>
          </svg>
          <span>清空</span>
        </button>
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
      <div class="messages-wrapper">
        <div
          v-for="msg in messages"
          :key="msg.id"
          :class="['message-wrapper', `message-${msg.role}`]"
        >
          <div class="message-avatar">
            <svg v-if="msg.role === 'user'" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
            <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2L2 7l10 5 10-5-10-5z"/>
              <path d="M2 17l10 5 10-5"/>
              <path d="M2 12l10 5 10-5"/>
            </svg>
          </div>
          <div class="message-content">
            <div class="message-header">
              <span class="sender">{{ msg.role === 'user' ? '我' : 'AI 助教' }}</span>
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
    </div>

    <!-- 输入区域 -->
    <div class="input-container">
      <div class="input-wrapper">
        <el-input
          v-model="inputMessage"
          type="textarea"
          :rows="2"
          placeholder="输入你的问题，AI 助教随时为你解答..."
          @keyup.enter.exact="sendMessage"
          :disabled="isStreaming"
          resize="none"
        />
        <button
          class="send-btn"
          @click="sendMessage"
          :disabled="!inputMessage.trim() || isStreaming"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="22" y1="2" x2="11" y2="13"/>
            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
      </div>
      <div class="quick-questions">
        <span class="label">快速提问：</span>
        <button
          v-for="question in quickQuestions"
          :key="question"
          class="quick-btn"
          @click="quickAsk(question)"
        >
          {{ question }}
        </button>
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
  '如何学习 Python？',
  '推荐一些 AI 学习资源'
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
      '```python\nfrom sklearn.linear_model import LinearRegression\n\nmodel = LinearRegression()\nmodel.fit(X_train, y_train)\npredictions = model.predict(X_test)\n```\n\n',
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
      '- Transformer - 用于 NLP 任务'
    ],
    '如何学习 Python？': [
      '学习 Python 是进入 AI 领域的第一步。\n\n',
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
      '   - Web 开发（可选）\n\n',
      '**推荐资源：**\n',
      '- Python 官方文档\n',
      '- Coursera 的 Python 课程\n',
      '- LeetCode 练习'
    ],
    '推荐一些 AI 学习资源': [
      '好的，这里有一些优质的 AI 学习资源：\n\n',
      '**在线课程：**\n\n',
      '- [Coursera - 机器学习](https://www.coursera.org/learn/machine-learning)\n',
      '- [fast.ai](https://www.fast.ai/)\n',
      '- [DeepLearning.AI](https://www.deeplearning.ai/)\n\n',
      '**书籍：**\n\n',
      '- 《机器学习实战》\n',
      '- 《深度学习》（Goodfellow）\n',
      '- 《Python 机器学习基础教程》\n\n',
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
    content: '你好！我是你的 AI 学习助手。有什么问题想了解吗？',
    timestamp: Date.now()
  }
  messages.value.push(welcomeMessage)
}

onMounted(() => {
  const welcomeMessage: ChatMessage = {
    id: 'welcome',
    role: 'assistant',
    content: '你好！我是你的 AI 学习助手。有什么问题想了解吗？',
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
  border-radius: 16px;
  overflow: hidden;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border-color);
}

.header-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.avatar {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: var(--gradient-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}

.title h2 {
  margin: 0 0 4px 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.title p {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.header-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-radius: 8px;
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-btn:hover {
  background: var(--primary-bg);
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.message-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.messages-wrapper {
  max-width: 800px;
  margin: 0 auto;
}

.message-wrapper {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
}

.message-user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.message-user .message-avatar {
  background: var(--gradient-primary);
  color: white;
}

.message-wrapper:not(.message-user) .message-avatar {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  color: var(--primary-color);
}

.message-content {
  max-width: 75%;
  display: flex;
  flex-direction: column;
}

.message-user .message-content {
  align-items: flex-end;
}

.message-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.message-user .message-header {
  flex-direction: row-reverse;
}

.sender {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
}

.time {
  font-size: 11px;
  color: var(--text-placeholder);
}

.message-body {
  background: var(--card-bg);
  padding: 14px 18px;
  border-radius: 12px;
  border: 1px solid var(--border-color);
  line-height: 1.6;
  color: var(--text-primary);
  font-size: 14px;
}

.message-user .message-body {
  background: var(--gradient-primary);
  border: none;
  color: white;
}

/* Markdown 样式 */
.message-body :deep(pre) {
  background-color: #0F172A;
  padding: 12px 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 12px 0;
}

.message-body :deep(code) {
  background-color: rgba(255, 255, 255, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'Fira Code', monospace;
}

.message-user .message-body :deep(code) {
  background-color: rgba(255, 255, 255, 0.2);
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
  border: 1px solid var(--border-color);
}

.message-body :deep(th),
.message-body :deep(td) {
  border: 1px solid var(--border-color);
  padding: 10px 14px;
  text-align: left;
}

.message-body :deep(th) {
  background-color: rgba(34, 197, 94, 0.1);
  font-weight: 600;
}

.message-body :deep(a) {
  color: var(--primary-color);
}

.message-user .message-body :deep(a) {
  color: white;
  text-decoration: underline;
}

.message-body :deep(blockquote) {
  border-left: 3px solid var(--primary-color);
  padding-left: 12px;
  color: var(--text-secondary);
  margin: 12px 0;
}

.message-body :deep(h1),
.message-body :deep(h2),
.message-body :deep(h3) {
  margin: 16px 0 8px;
  font-weight: 600;
  color: var(--text-primary);
}

.message-body :deep(h1) { font-size: 18px; }
.message-body :deep(h2) { font-size: 16px; }
.message-body :deep(h3) { font-size: 14px; }

.message-body :deep(ul),
.message-body :deep(ol) {
  padding-left: 20px;
  margin: 8px 0;
}

.message-body :deep(li) {
  margin: 4px 0;
}

.typing-indicator {
  display: flex;
  align-items: center;
  padding: 8px 0;
  gap: 4px;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: var(--primary-color);
  animation: typing 1.4s infinite ease-in-out;
}

.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 80%, 100% { opacity: 0.2; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1); }
}

.input-container {
  padding: 16px 24px 20px;
  background: var(--bg-card);
  border-top: 1px solid var(--border-color);
}

.input-wrapper {
  display: flex;
  gap: 12px;
  align-items: flex-end;
}

.input-wrapper :deep(.el-textarea) {
  flex: 1;
}

.input-wrapper :deep(.el-textarea__inner) {
  border-radius: 12px;
  padding: 12px 16px;
  font-size: 14px;
}

.send-btn {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: var(--gradient-primary);
  border: none;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(34, 197, 94, 0.35);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.quick-questions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-color);
  flex-wrap: wrap;
}

.label {
  font-size: 12px;
  color: var(--text-placeholder);
}

.quick-btn {
  padding: 6px 12px;
  border-radius: 16px;
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.quick-btn:hover {
  background: var(--primary-bg);
  border-color: var(--primary-color);
  color: var(--primary-color);
}
</style>
