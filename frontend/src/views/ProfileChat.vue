<template>
  <div class="profile-chat-container">
    <!-- 左侧对话区域 -->
    <div class="chat-section">
      <!-- 消息列表 -->
      <div
        class="message-list"
        ref="messageList"
        @scroll="handleScroll"
        @wheel="handleScrollStart"
        @touchstart="handleScrollStart"
        @touchend="handleScrollEnd"
      >
        <div
          v-for="msg in messages"
          :key="msg.id"
          :class="['message-item', `message-${msg.role}`]"
        >
          <div class="avatar">
            <svg v-if="msg.role === 'user'" class="user-avatar" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
            <svg v-else class="assistant-avatar" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2L2 7l10 5 10-5-10-5z"/>
              <path d="M2 17l10 5 10-5"/>
              <path d="M2 12l10 5 10-5"/>
            </svg>
          </div>
          <div class="message-content">
            <div class="message-header">
              <span>{{ msg.role === 'user' ? '我' : 'AI助手' }}</span>
              <span class="time">{{ formatTime(msg.timestamp) }}</span>
            </div>
            <div
              class="message-body"
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

      <!-- 输入框 -->
      <div class="input-area">
        <el-input
          v-model="inputMessage"
          type="textarea"
          :rows="2"
          placeholder="输入你的问题..."
          @keyup.enter.exact="sendMessage"
          resize="none"
        />
        <button
          type="button"
          :class="['send-btn', { 'abort-btn': isStreaming }]"
          :disabled="!inputMessage.trim() && !isStreaming"
          @click="isStreaming ? abortStreaming() : sendMessage()"
        >
          <svg v-if="!isStreaming" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="22" y1="2" x2="11" y2="13"/>
            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
          </svg>
          <span>{{ isStreaming ? '中止' : '发送' }}</span>
        </button>
      </div>
    </div>

    <!-- 右侧画像面板 -->
    <div class="profile-panel">
      <div class="panel-header">
        <div class="header-title">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
          </svg>
          <h3>学生画像</h3>
        </div>
        <button class="refresh-btn" @click="refreshProfile" title="刷新画像">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="23 4 23 10 17 10"/>
            <polyline points="1 20 1 14 7 14"/>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
          </svg>
        </button>
      </div>

      <!-- 知识基础 -->
      <div class="profile-item">
        <div class="item-header">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
          </svg>
          <h4>知识基础</h4>
        </div>
        <div class="progress-container">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: profile.knowledgeBase + '%' }"></div>
          </div>
          <span class="progress-text">{{ profile.knowledgeBase }}%</span>
        </div>
      </div>

      <!-- 认知风格 -->
      <div class="profile-item">
        <div class="item-header">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>
          </svg>
          <h4>认知风格</h4>
        </div>
        <div class="tag-list">
          <span v-for="tag in profile.cognitiveStyle" :key="tag" class="tag">{{ tag }}</span>
        </div>
      </div>

      <!-- 学习目标 -->
      <div class="profile-item">
        <div class="item-header">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
          </svg>
          <h4>学习目标</h4>
        </div>
        <p class="goal-text">{{ profile.learningGoals }}</p>
      </div>

      <!-- 易错点 -->
      <div class="profile-item">
        <div class="item-header">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <h4>易错点</h4>
        </div>
        <ul class="error-list">
          <li
            v-for="(item, index) in profile.entries.weak_points"
            :key="index"
            :class="['error-item', item.status]"
          >
            <span class="error-text">{{ item.text }}</span>
            <span class="error-confidence">{{ item.confidence }}/10</span>
          </li>
        </ul>
      </div>

      <!-- 学习节奏 -->
      <div class="profile-item">
        <div class="item-header">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <polyline points="12 6 12 12 16 14"/>
          </svg>
          <h4>学习节奏</h4>
        </div>
        <div class="rhythm-info">
          <span class="rhythm-label">每日学习时长</span>
          <span class="rhythm-value">{{ profile.learningRhythm.dailyHours }}小时</span>
        </div>
        <div class="rhythm-info">
          <span class="rhythm-label">学习频率</span>
          <span class="rhythm-value">{{ profile.learningRhythm.frequency }}</span>
        </div>
      </div>

      <!-- 兴趣方向 -->
      <div class="profile-item">
        <div class="item-header">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
          </svg>
          <h4>兴趣方向</h4>
        </div>
        <div class="interest-tags">
          <span
            v-for="(item, index) in profile.entries.interest_direction"
            :key="index"
            :class="['interest-tag', item.status]"
          >
            {{ item.text }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, nextTick, onMounted } from 'vue'
import { marked } from 'marked'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
  streaming?: boolean
}

interface ProfileEntry {
  text: string
  confidence: number
  status: 'active' | 'tentative' | 'stale'
}

interface ProfileData {
  knowledgeBase: number
  cognitiveStyle: string[]
  learningGoals: string
  易错点: string[]
  learningRhythm: {
    dailyHours: number
    frequency: string
  }
  interests: string[]
  entries: {
    weak_points: ProfileEntry[]
    interest_direction: ProfileEntry[]
  }
}

const messages = ref<ChatMessage[]>([])
const inputMessage = ref('')
const isStreaming = ref(false)
const streamContent = ref('')
const messageList = ref<HTMLElement | null>(null)
const shouldAutoScroll = ref(true)
const isUserScrolling = ref(false)

const profile = reactive<ProfileData>({
  knowledgeBase: 65,
  cognitiveStyle: ['视觉型', '反思型', '理论型'],
  learningGoals: '掌握人工智能基础理论，能够独立完成简单AI项目开发',
  易错点: ['梯度消失问题', '过拟合处理', '正则化参数选择'],
  learningRhythm: {
    dailyHours: 2.5,
    frequency: '每周5-6次'
  },
  interests: ['机器学习', '深度学习', 'NLP', '计算机视觉'],
  entries: {
    weak_points: [
      { text: '梯度消失问题', confidence: 8, status: 'active' },
      { text: '过拟合处理', confidence: 7, status: 'active' },
      { text: '正则化参数选择', confidence: 5, status: 'tentative' },
      { text: 'CNN池化层作用', confidence: 3, status: 'tentative' }
    ],
    interest_direction: [
      { text: '机器学习', confidence: 9, status: 'active' },
      { text: '深度学习', confidence: 8, status: 'active' },
      { text: 'NLP', confidence: 7, status: 'active' },
      { text: '计算机视觉', confidence: 6, status: 'tentative' },
      { text: '强化学习', confidence: 4, status: 'tentative' }
    ]
  }
})

const formatTime = (timestamp: number) => {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

const renderMarkdown = (content: string) => {
  return marked(content)
}

const scrollToBottom = async (force = false) => {
  await nextTick()
  if (messageList.value && (shouldAutoScroll.value || force)) {
    messageList.value.scrollTop = messageList.value.scrollHeight
  }
}

const handleScroll = () => {
  if (!messageList.value) return

  const { scrollTop, scrollHeight, clientHeight } = messageList.value
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
    if (messageList.value) {
      const { scrollTop, scrollHeight, clientHeight } = messageList.value
      const isAtBottom = scrollHeight - scrollTop - clientHeight <= 50
      if (isAtBottom) {
        shouldAutoScroll.value = true
      }
    }
  }, 200)
}

const abortStreaming = () => {
  isStreaming.value = false
  streamContent.value = ''
  const lastMessage = messages.value[messages.value.length - 1]
  if (lastMessage && lastMessage.streaming) {
    lastMessage.streaming = false
  }
}

const sendMessage = async () => {
  if (!inputMessage.value.trim()) return

  if (isStreaming.value) {
    abortStreaming()
    await nextTick()
  }

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

  simulateSSE()
}

const simulateSSE = async () => {
  const responses = [
    '好的，我来帮你分析一下当前的学习情况。',
    '根据我们的对话，我发现你对机器学习很感兴趣，',
    '特别是深度学习方向。',
    '\n\n**你的优势：**\n- 理论基础扎实\n- 编程能力较强\n\n**建议：**\n- 多做实战项目\n- 关注最新论文'
  ]

  let scrollInterval: ReturnType<typeof setInterval> | null = null

  scrollInterval = setInterval(() => {
    if (shouldAutoScroll.value) {
      scrollToBottom()
    }
  }, 200)

  for (const part of responses) {
    for (let i = 0; i < part.length; i++) {
      if (!isStreaming.value) break
      streamContent.value += part[i]
      const lastMessage = messages.value[messages.value.length - 1]
      if (lastMessage) {
        lastMessage.content = streamContent.value
      }
      await new Promise(resolve => setTimeout(resolve, 30 + Math.random() * 50))
    }
  }

  if (scrollInterval) {
    clearInterval(scrollInterval)
  }

  await scrollToBottom()

  isStreaming.value = false
  const lastMessage = messages.value[messages.value.length - 1]
  if (lastMessage) {
    lastMessage.streaming = false
  }

  updateProfile()
}

const updateProfile = () => {
  profile.knowledgeBase = Math.min(100, profile.knowledgeBase + 2)
  profile.learningGoals = '深入学习深度学习，完成至少3个实战项目'
  if (!profile.cognitiveStyle.includes('实践型')) {
    profile.cognitiveStyle.push('实践型')
  }
}

const refreshProfile = () => {
  profile.knowledgeBase = Math.min(100, profile.knowledgeBase + 1)
}

onMounted(() => {
  const welcomeMessage: ChatMessage = {
    id: 'welcome',
    role: 'assistant',
    content: '你好！我是你的AI学习助手。让我来帮助你构建个性化的学习画像。请问你目前学习AI多久了？',
    timestamp: Date.now()
  }
  messages.value.push(welcomeMessage)
})
</script>

<style scoped>
.profile-chat-container {
  display: flex;
  width: 100%;
  height: 100%;
  background-color: var(--bg-page);
  overflow: hidden;
  gap: 20px;
}

.chat-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 0;
}

.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background-color: var(--bg-card);
  border-radius: 16px;
  border: 1px solid var(--border-color);
}

.message-item {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.message-user {
  flex-direction: row-reverse;
}

.message-user .message-content {
  align-items: flex-end;
}

.avatar {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.user-avatar {
  background: var(--gradient-primary);
  color: white;
}

.assistant-avatar {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  color: var(--primary-color);
}

.message-content {
  max-width: 70%;
  display: flex;
  flex-direction: column;
}

.message-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  gap: 12px;
}

.message-header span:first-child {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
}

.time {
  font-size: 11px;
  color: var(--text-placeholder);
}

.message-body {
  background-color: var(--card-bg);
  padding: 12px 16px;
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

.message-body :deep(blockquote) {
  border-left: 3px solid var(--primary-color);
  padding-left: 12px;
  color: var(--text-secondary);
  margin: 8px 0;
}

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

.input-area {
  padding: 16px;
  background-color: var(--bg-card);
  border-radius: 16px;
  margin-top: 16px;
  display: flex;
  gap: 12px;
  border: 1px solid var(--border-color);
}

.input-area :deep(.el-textarea) {
  flex: 1;
}

.input-area :deep(.el-textarea__inner) {
  border-radius: 10px;
  padding: 12px 16px;
  font-size: 14px;
}

.send-btn {
  align-self: flex-end;
  padding: 0 16px;
  background: var(--gradient-primary);
  color: white;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all 0.2s ease;
  height: 44px;
  font-weight: 600;
  font-size: 14px;
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(34, 197, 94, 0.35);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.send-btn.abort-btn {
  background: linear-gradient(135deg, #EF4444, #DC2626);
}

.send-btn.abort-btn:hover:not(:disabled) {
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.35);
}

.profile-panel {
  width: 320px;
  flex-shrink: 0;
  padding: 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 16px;
  overflow-y: auto;
  height: 100%;
  box-sizing: border-box;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-color);
}

.header-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-title svg {
  color: var(--primary-color);
}

.panel-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.refresh-btn {
  width: 36px;
  height: 36px;
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  cursor: pointer;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.refresh-btn:hover {
  background: var(--primary-bg);
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.profile-item {
  margin-bottom: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border-color);
}

.profile-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}

.item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.item-header svg {
  color: var(--primary-color);
}

.item-header h4 {
  margin: 0;
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 600;
}

.progress-container {
  display: flex;
  align-items: center;
  gap: 12px;
}

.progress-bar {
  flex: 1;
  height: 8px;
  background: var(--border-color);
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--gradient-primary);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.progress-text {
  font-weight: 700;
  font-size: 14px;
  color: var(--primary-color);
  min-width: 40px;
  text-align: right;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag {
  padding: 6px 12px;
  background: var(--primary-bg);
  color: var(--primary-color);
  border-radius: 16px;
  font-size: 12px;
  font-weight: 500;
}

.goal-text {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.error-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.error-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--danger-light);
  border-radius: 8px;
  font-size: 13px;
}

.error-item.tentative {
  background: rgba(245, 158, 11, 0.1);
}

.error-text {
  color: var(--danger-color);
}

.error-item.tentative .error-text {
  color: var(--warning-color);
}

.error-confidence {
  font-size: 11px;
  color: var(--text-placeholder);
  font-weight: 600;
}

.rhythm-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
}

.rhythm-label {
  color: var(--text-secondary);
  font-size: 13px;
}

.rhythm-value {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
}

.interest-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.interest-tag {
  padding: 6px 12px;
  background: var(--success-light);
  color: var(--success-color);
  border-radius: 16px;
  font-size: 12px;
  font-weight: 500;
}

.interest-tag.tentative {
  background: rgba(245, 158, 11, 0.1);
  color: var(--warning-color);
}

@media (max-width: 900px) {
  .profile-chat-container {
    flex-direction: column;
  }

  .profile-panel {
    width: 100%;
    max-height: 300px;
  }
}
</style>
