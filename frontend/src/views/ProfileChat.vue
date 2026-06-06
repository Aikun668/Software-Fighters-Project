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
            <svg v-if="msg.role === 'user'" class="user-avatar" viewBox="0 0 24 24" width="24" height="24">
              <circle cx="12" cy="8" r="4" fill="currentColor"/>
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" fill="currentColor"/>
            </svg>
            <svg v-else class="assistant-avatar" viewBox="0 0 24 24" width="24" height="24">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" fill="currentColor"/>
              <circle cx="12" cy="10" r="3" fill="white"/>
              <path d="M9 16h6" stroke="white" stroke-width="2" stroke-linecap="round" fill="none"/>
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
        />
        <button
          type="button"
          :class="['send-btn', { 'abort-btn': isStreaming }]"
          :disabled="!inputMessage.trim() && !isStreaming"
          @click="isStreaming ? abortStreaming() : sendMessage()"
        >
          <svg v-if="!isStreaming" viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M22 2L11 13l-4-4-4 18 11-9 11 9-4-14z"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
          </svg>
          <span>{{ isStreaming ? '中止输出' : '发送' }}</span>
        </button>
      </div>
    </div>

    <!-- 右侧画像面板 -->
    <div class="profile-panel">
      <div class="panel-header">
        <div class="header-title">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
          </svg>
          <h3>学生画像</h3>
        </div>
        <button class="refresh-btn" @click="refreshProfile">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <polyline points="23 4 23 10 17 10"/>
            <polyline points="1 20 1 14 7 14"/>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
          </svg>
        </button>
      </div>

      <!-- 知识基础 -->
      <div class="profile-item">
        <div class="item-header">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
          </svg>
          <h4>知识基础</h4>
        </div>
        <div class="progress-container">
          <svg class="progress-svg" viewBox="0 0 200 12">
            <rect width="200" height="12" rx="6" fill="#E2E8F0"/>
            <rect 
              :width="profile.knowledgeBase * 2" 
              height="12" 
              rx="6" 
              fill="url(#progressGradient)"
              class="progress-fill"
            />
            <defs>
              <linearGradient id="progressGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="#3B82F6"/>
                <stop offset="100%" stop-color="#2563EB"/>
              </linearGradient>
            </defs>
          </svg>
          <span class="progress-text">{{ profile.knowledgeBase }}%</span>
        </div>
      </div>

      <!-- 认知风格 -->
      <div class="profile-item">
        <div class="item-header">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>
          </svg>
          <h4>认知风格</h4>
        </div>
        <div class="tag-list">
          <span
            v-for="tag in profile.cognitiveStyle"
            :key="tag"
            class="custom-tag"
          >
            {{ tag }}
          </span>
        </div>
      </div>

      <!-- 学习目标 -->
      <div class="profile-item">
        <div class="item-header">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
          </svg>
          <h4>学习目标</h4>
        </div>
        <p class="goal-text">{{ profile.learningGoals }}</p>
      </div>

      <!-- 易错点 -->
      <div class="profile-item">
        <div class="item-header">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 8v4M12 16h.01"/>
          </svg>
          <h4>易错点</h4>
        </div>
        <ul class="error-list">
          <li 
            v-for="(item, index) in profile.entries.weak_points" 
            :key="index"
            :class="['entry-item', item.status]"
          >
            <svg class="error-icon" viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/>
            </svg>
            <span class="entry-text">{{ item.text }}</span>
            <span class="entry-confidence">{{ item.confidence }}/10</span>
            <svg v-if="item.status === 'tentative'" class="status-icon" viewBox="0 0 24 24" width="12" height="12" fill="currentColor">
              <circle cx="12" cy="12" r="10"/>
              <path d="M9.4 16.6L14.8 12l-5.4-4.6L8 9.2l4 4 4-4L20 12l-6.6 6.6-4-4z"/>
            </svg>
          </li>
        </ul>
      </div>

      <!-- 学习节奏 -->
      <div class="profile-item">
        <div class="item-header">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <circle cx="12" cy="12" r="10"/>
            <polyline points="12 6 12 12 16 14"/>
          </svg>
          <h4>学习节奏</h4>
        </div>
        <div class="rhythm-info">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
            <line x1="3" y1="9" x2="21" y2="9" stroke="currentColor" stroke-width="2"/>
            <line x1="3" y1="15" x2="18" y2="15" stroke="currentColor" stroke-width="2"/>
          </svg>
          <span class="rhythm-label">每日学习时长：</span>
          <span class="rhythm-value">{{ profile.learningRhythm.dailyHours }}小时</span>
        </div>
        <div class="rhythm-info">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 6v6l4 2"/>
          </svg>
          <span class="rhythm-label">学习频率：</span>
          <span class="rhythm-value">{{ profile.learningRhythm.frequency }}</span>
        </div>
      </div>

      <!-- 兴趣方向 -->
      <div class="profile-item">
        <div class="item-header">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
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
            <svg v-if="item.status === 'tentative'" class="status-icon" viewBox="0 0 24 24" width="10" height="10" fill="currentColor">
              <circle cx="12" cy="12" r="10"/>
              <path d="M9.4 16.6L14.8 12l-5.4-4.6L8 9.2l4 4 4-4L20 12l-6.6 6.6-4-4z"/>
            </svg>
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
  max-width: 100vw;
  max-height: 100vh;
  background-color: var(--bg-page);
  overflow: hidden;
  margin: 0;
  padding: 0;
}

.chat-section {
  flex: 0 0 70%;
  display: flex;
  flex-direction: column;
  height: 100%;
  box-sizing: border-box;
  padding: var(--spacing-xl);
}

.message-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-xl);
  background-color: var(--bg-card);
  border-radius: var(--radius-xl);
  box-sizing: border-box;
  box-shadow: var(--shadow-md);
}

.message-item {
  display: flex;
  margin-bottom: var(--spacing-xl);
}

.message-user {
  flex-direction: row-reverse;
}

.message-user .message-content {
  align-items: flex-end;
}

.avatar {
  flex: 0 0 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 var(--spacing-md);
}

.user-avatar {
  background-color: var(--primary-color);
  color: white;
}

.assistant-avatar {
  background-color: var(--success-color);
  color: white;
}

.message-content {
  max-width: 70%;
}

.message-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-xs);
}

.message-header span:first-child {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.time {
  font-size: var(--font-size-xs);
  color: var(--text-placeholder);
}

.message-body {
  background-color: #F1F5F9;
  padding: var(--spacing-md) var(--spacing-lg);
  border-radius: var(--radius-lg);
  border-bottom-left-radius: 4px;
  line-height: var(--line-height-base);
  color: var(--text-secondary);
}

.message-user .message-body {
  background-color: rgba(59, 130, 246, 0.1);
  color: var(--primary-color);
  border-radius: var(--radius-lg);
  border-bottom-right-radius: 4px;
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

.message-body :deep(blockquote) {
  border-left: 4px solid #3B82F6;
  padding-left: 12px;
  color: #64748B;
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

.input-area {
  padding: var(--spacing-lg);
  background-color: var(--bg-card);
  border-radius: var(--radius-xl);
  margin-top: var(--spacing-xl);
  display: flex;
  gap: var(--spacing-md);
  box-shadow: var(--shadow-md);
}

.input-area :deep(.el-textarea) {
  flex: 1;
}

.input-area :deep(.el-input__wrapper) {
  border-radius: var(--radius-md);
  padding: var(--spacing-md) var(--spacing-lg);
  border: 1px solid var(--border-color);
}

.input-area :deep(.el-input__wrapper:focus-within) {
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
  border-color: var(--primary-color);
}

.send-btn {
  align-self: flex-end;
  padding: 0 var(--spacing-xl);
  background: linear-gradient(135deg, var(--primary-color), var(--primary-dark));
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--transition-normal);
  height: 40px;
  font-weight: var(--font-weight-medium);
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.send-btn:disabled {
  background: var(--text-placeholder);
  cursor: not-allowed;
}

.send-btn.abort-btn {
  background: linear-gradient(135deg, var(--danger-color), #DC2626);
}

.send-btn.abort-btn:hover {
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3);
}

.send-btn span {
  margin-left: var(--spacing-xs);
  font-size: var(--font-size-sm);
}

.profile-panel {
  flex: 0 0 30%;
  padding: var(--spacing-xl);
  background: var(--glass-bg);
  backdrop-filter: blur(10px);
  border: 1px solid var(--glass-border);
  overflow-y: auto;
  height: 100%;
  box-sizing: border-box;
  border-radius: var(--radius-xl);
  margin: var(--spacing-lg);
  box-shadow: var(--glass-shadow);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2xl);
}

.header-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.header-title svg {
  color: var(--primary-color);
}

.panel-header h3 {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--primary-color);
}

.refresh-btn {
  padding: var(--spacing-xs);
  background-color: #F1F5F9;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: #64748B;
  transition: var(--transition-normal);
}

.refresh-btn:hover {
  background-color: var(--border-color);
  color: var(--primary-color);
}

.profile-item {
  margin-bottom: var(--spacing-2xl);
  padding-bottom: var(--spacing-2xl);
  border-bottom: 1px solid var(--border-color);
}

.profile-item:last-child {
  border-bottom: none;
}

.item-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
}

.item-header svg {
  color: var(--primary-color);
}

.item-header h4 {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  font-weight: var(--font-weight-semibold);
}

.progress-container {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.progress-svg {
  flex: 1;
  height: 6px;
}

.progress-fill {
  transition: width var(--transition-slow);
}

.progress-text {
  font-weight: var(--font-weight-semibold);
  color: var(--primary-color);
  min-width: 40px;
  text-align: right;
}

.tag-list, .interest-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
}

.custom-tag {
  padding: var(--spacing-xs) var(--spacing-md);
  background-color: var(--primary-bg);
  color: var(--primary-color);
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
}

.goal-text {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: var(--line-height-base);
}

.error-list {
  margin: 0;
  padding-left: 0;
  list-style: none;
}

.error-list li {
  display: flex;
  align-items: center;
  padding: var(--spacing-xs) 0;
  font-size: 13px;
  color: var(--danger-color);
  gap: var(--spacing-sm);
}

.error-icon {
  color: var(--danger-color);
}

.rhythm-info {
  display: flex;
  padding: var(--spacing-xs) 0;
  align-items: center;
  gap: var(--spacing-sm);
}

.rhythm-info svg {
  color: var(--primary-color);
}

.rhythm-label {
  color: var(--text-placeholder);
  font-size: 13px;
}

.rhythm-value {
  color: var(--text-secondary);
  font-size: 13px;
}

.interest-tag {
  padding: var(--spacing-xs) var(--spacing-md);
  background-color: var(--success-light);
  color: var(--success-color);
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
}
</style>
