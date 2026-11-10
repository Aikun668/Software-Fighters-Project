<template>
  <div class="chat-layout">
    <!-- 主聊天区域 -->
    <main class="chat-main">
      <!-- 消息列表 -->
      <div 
        class="messages-container" 
        ref="messageListRef"
        @scroll="handleScroll"
        @wheel="handleScrollStart"
        @touchstart="handleScrollStart"
        @touchend="handleScrollEnd"
      >
        <div class="messages-wrapper">
          <!-- 欢迎消息 -->
          <div v-if="messages.length === 0" class="welcome-message">
            <div class="welcome-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                <path d="M2 17l10 5 10-5"/>
                <path d="M2 12l10 5 10-5"/>
              </svg>
            </div>
            <h2>你好，我是AI学习助手</h2>
            <p>我可以帮你分析学习情况，制定个性化学习计划</p>
          </div>

          <!-- 消息列表 -->
          <div
            v-for="msg in messages"
            :key="msg.id"
            :class="['message-item', `message-${msg.role}`]"
          >
            <div class="message-avatar">
              <div v-if="msg.role === 'user'" class="avatar-inner user-avatar-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                  <circle cx="12" cy="7" r="4"/>
                </svg>
              </div>
              <div v-else class="avatar-inner ai-avatar-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                  <path d="M2 17l10 5 10-5"/>
                  <path d="M2 12l10 5 10-5"/>
                </svg>
              </div>
            </div>
            <div class="message-bubble">
              <div v-if="msg.role === 'assistant'" class="message-header">
                <span class="sender-name">AI学习助手</span>
                <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
              </div>
              <div class="message-content" :class="{ 'streaming': msg.streaming }" v-html="renderMarkdown(msg.streaming ? streamContent : msg.content)"></div>
              <div v-if="msg.role === 'assistant' && msg.streaming" class="typing-indicator">
                <span class="dot"></span>
                <span class="dot"></span>
                <span class="dot"></span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部输入区域 -->
      <div class="input-section">
        <div class="input-wrapper">
          <div class="input-box">
            <textarea
              v-model="inputText"
              placeholder="输入你的问题..."
              rows="1"
              @keydown.enter.exact.prevent="handleSend"
              @input="autoResize"
              ref="textareaRef"
            ></textarea>
          </div>
          <button
            class="send-button"
            :disabled="!inputText.trim()"
            @click="handleSend()"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="22" y1="2" x2="11" y2="13"/>
              <polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>
        <p class="input-hint">按 Enter 发送，Shift + Enter 换行</p>
      </div>
    </main>

    <!-- 右侧学生画像 -->
    <aside class="profile-sidebar">
      <div class="profile-header">
        <h2>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
          </svg>
          学习画像
        </h2>
        <button class="refresh-btn" @click="refreshProfile">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="23 4 23 10 17 10"/>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
        </button>
      </div>

      <div class="profile-content">
        <div class="profile-card">
          <div class="card-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2L2 7l10 5 10-5-10-5z"/>
              <path d="M2 17l10 5 10-5"/>
              <path d="M2 12l10 5 10-5"/>
            </svg>
          </div>
          <div class="card-info">
            <span class="card-label">知识基础</span>
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: profile.knowledgeBase + '%' }"></div>
            </div>
            <span class="progress-text">{{ profile.knowledgeBase }}%</span>
          </div>
        </div>

        <div class="profile-card">
          <div class="card-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>
            </svg>
          </div>
          <div class="card-info">
            <span class="card-label">认知风格</span>
            <div class="tags-list">
              <span v-for="style in profile.cognitiveStyle" :key="style" class="tag">{{ style }}</span>
            </div>
          </div>
        </div>

        <div class="profile-card">
          <div class="card-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
            </svg>
          </div>
          <div class="card-info">
            <span class="card-label">学习目标</span>
            <p class="goal-text">{{ profile.learningGoals }}</p>
          </div>
        </div>

        <div class="profile-card">
          <div class="card-icon warning">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
          </div>
          <div class="card-info">
            <span class="card-label">易错点</span>
            <ul class="weak-list">
              <li v-for="(point, index) in profile.entries.weak_points" :key="index" :class="['weak-item', point.status]">
                <span class="weak-text">{{ point.text }}</span>
                <span class="weak-confidence">{{ point.confidence }}/10</span>
              </li>
            </ul>
          </div>
        </div>

        <div class="profile-card">
          <div class="card-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
          </div>
          <div class="card-info">
            <span class="card-label">学习节奏</span>
            <div class="rhythm-info">
              <div class="rhythm-item">
                <span class="rhythm-label">每日学习</span>
                <span class="rhythm-value">{{ profile.learningRhythm.dailyHours }}小时</span>
              </div>
              <div class="rhythm-item">
                <span class="rhythm-label">学习频率</span>
                <span class="rhythm-value">{{ profile.learningRhythm.frequency }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="profile-card">
          <div class="card-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
            </svg>
          </div>
          <div class="card-info">
            <span class="card-label">兴趣方向</span>
            <div class="interests-list">
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
    </aside>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, nextTick, onMounted } from 'vue'
import { renderChatMarkdown } from '@/utils/markdown'

interface Message {
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
  learningRhythm: {
    dailyHours: number
    frequency: string
  }
  entries: {
    weak_points: ProfileEntry[]
    interest_direction: ProfileEntry[]
  }
}

const messages = ref<Message[]>([])
const inputText = ref('')
const isStreaming = ref(false)
const streamContent = ref('')
const messageListRef = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const shouldAutoScroll = ref(true)
const isUserScrolling = ref(false)

const profile = reactive<ProfileData>({
  knowledgeBase: 65,
  cognitiveStyle: ['视觉型', '反思型', '理论型'],
  learningGoals: '掌握人工智能基础理论，能够独立完成简单AI项目开发',
  learningRhythm: {
    dailyHours: 2.5,
    frequency: '每周5-6次'
  },
  entries: {
    weak_points: [
      { text: '梯度消失问题', confidence: 8, status: 'active' },
      { text: '过拟合处理', confidence: 7, status: 'active' },
      { text: '正则化参数选择', confidence: 5, status: 'tentative' }
    ],
    interest_direction: [
      { text: '机器学习', confidence: 9, status: 'active' },
      { text: '深度学习', confidence: 8, status: 'active' },
      { text: 'NLP', confidence: 7, status: 'active' },
      { text: '计算机视觉', confidence: 6, status: 'tentative' }
    ]
  }
})

const formatTime = (timestamp: number) => {
  return new Date(timestamp).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit'
  })
}

/** 助手正文渲染统一走 `@/utils/markdown`（Markdown + KaTeX 公式 + XSS 清洗）。 */
const renderMarkdown = renderChatMarkdown

const autoResize = () => {
  nextTick(() => {
    if (textareaRef.value) {
      textareaRef.value.style.height = 'auto'
      textareaRef.value.style.height = Math.min(textareaRef.value.scrollHeight, 120) + 'px'
    }
  })
}

const scrollToBottom = async (force = false) => {
  await nextTick()
  if (messageListRef.value && (shouldAutoScroll.value || force)) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight
  }
}

const handleScroll = () => {
  if (!messageListRef.value) return

  const { scrollTop, scrollHeight, clientHeight } = messageListRef.value
  const isAtBottom = scrollHeight - scrollTop - clientHeight <= 50

  if (isUserScrolling.value) {
    shouldAutoScroll.value = isAtBottom
  }
}

const handleScrollStart = () => {
  isUserScrolling.value = true
}

const handleScrollEnd = () => {
  setTimeout(() => {
    isUserScrolling.value = false
    if (messageListRef.value) {
      const { scrollTop, scrollHeight, clientHeight } = messageListRef.value
      const isAtBottom = scrollHeight - scrollTop - clientHeight <= 50
      if (isAtBottom) {
        shouldAutoScroll.value = true
      }
    }
  }, 200)
}

const handleSend = async () => {
  if (!inputText.value.trim() || isStreaming.value) return

  const userMsg: Message = {
    id: Date.now().toString(),
    role: 'user',
    content: inputText.value.trim(),
    timestamp: Date.now()
  }
  messages.value.push(userMsg)
  inputText.value = ''

  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
  }

  await scrollToBottom()
}

const refreshProfile = () => {
  profile.knowledgeBase = Math.min(100, profile.knowledgeBase + 1)
}

onMounted(() => {
  messages.value.push({
    id: 'welcome',
    role: 'assistant',
    content: '你好！我是你的AI学习助手。让我来帮助你了解自己的学习情况。请问你平时是怎么学习AI的？',
    timestamp: Date.now()
  })
})
</script>

<style scoped>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

/* === 布局容器 === */
.chat-layout {
  display: flex;
  width: 100%;
  max-width: 100%;
  height: 85vh;
  background: #0a0a0f;
  color: #e5e7eb;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  overflow: hidden;
  position: relative;
}

/* === 主聊天区域 === */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  height: 100%;
  width: calc(100% - 320px);
}

/* === 消息容器 === */
.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px 20px;
  width: 100%;
}

.messages-wrapper {
  max-width: 720px;
  margin: 0 auto;
  width: 100%;
}

/* === 欢迎消息 === */
.welcome-message {
  text-align: center;
  padding: 60px 20px;
}

.welcome-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 20px;
  background: linear-gradient(135deg, #10b981, #059669);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.welcome-icon svg {
  width: 32px;
  height: 32px;
  color: white;
}

.welcome-message h2 {
  font-size: 24px;
  font-weight: 600;
  color: #f3f4f6;
  margin-bottom: 8px;
}

.welcome-message p {
  font-size: 14px;
  color: #6b7280;
}

/* === 消息项 === */
.message-item {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
}

.message-user {
  flex-direction: row-reverse;
}

.message-avatar {
  flex-shrink: 0;
}

.avatar-inner {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.avatar-inner svg {
  width: 18px;
  height: 18px;
}

.user-avatar-icon {
  background: linear-gradient(135deg, #7c3aed, #a78bfa);
  color: white;
}

.ai-avatar-icon {
  background: linear-gradient(135deg, #10b981, #059669);
  color: white;
}

.message-bubble {
  max-width: 80%;
  display: flex;
  flex-direction: column;
  gap: 0 6px;
}

.message-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 4px;
}

.sender-name {
  font-size: 13px;
  font-weight: 600;
  color: #10b981;
}

.message-time {
  font-size: 11px;
  color: #4b5563;
}

.message-content {
  padding: 0 16px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  border-top-left-radius: 4px;
  font-size: 15px;
  line-height: 1.7;
  color: #e5e7eb;
}

.message-user .message-content {
  background: linear-gradient(135deg, #7c3aed, #a78bfa);
  border: none;
  border-radius: 12px;
  border-bottom-right-radius: 4px;
  color: white;
}

.message-content :deep(pre) {
  background: rgba(0, 0, 0, 0.4);
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 8px 0;
  font-size: 13px;
}

.message-content :deep(code) {
  background: rgba(255, 255, 255, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'Fira Code', 'Monaco', monospace;
}

.message-content :deep(blockquote) {
  border-left: 3px solid #10b981;
  padding-left: 12px;
  color: #9ca3af;
  margin: 8px 0;
}

/* === 打字指示器 === */
.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 8px 0;
}

.typing-indicator .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #10b981;
  animation: typing 1.4s infinite ease-in-out;
}

.typing-indicator .dot:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator .dot:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typing {
  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1); }
}

/* === 输入区域 === */
.input-section {
  padding: 16px 20px 20px;
  background: rgba(17, 24, 39, 0.95);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
}

.input-wrapper {
  max-width: 720px;
  margin: 0 auto;
  display: flex;
  gap: 12px;
  align-items: flex-end;
  width: 100%;
}

.input-box {
  flex: 1;
  min-width: 0;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  transition: all 0.2s ease;
}

.input-box:focus-within {
  border-color: #7c3aed;
  box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.15);
}

.input-box textarea {
  width: 100%;
  min-height: 44px;
  max-height: 120px;
  padding: 12px 16px;
  background: transparent;
  border: none;
  color: #e5e7eb;
  font-size: 15px;
  line-height: 1.5;
  resize: none;
  outline: none;
}

.input-box textarea::placeholder {
  color: #6b7280;
}

.send-button {
  width: 44px;
  height: 44px;
  background: linear-gradient(135deg, #10b981, #059669);
  border: none;
  border-radius: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.send-button:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.35);
}

.send-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.send-button.streaming {
  background: linear-gradient(135deg, #ef4444, #dc2626);
}

.send-button.streaming:hover:not(:disabled) {
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.35);
}

.send-button svg {
  width: 20px;
  height: 20px;
}

.input-hint {
  max-width: 720px;
  margin: 8px auto 0;
  text-align: center;
  font-size: 12px;
  color: #4b5563;
}

/* === 学生画像侧边栏 === */
.profile-sidebar {
  width: 320px;
  height: 100vh;
  background: rgba(17, 24, 39, 0.95);
  border-left: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow: hidden;
}

.profile-header {
  padding: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  flex-shrink: 0;
}

.profile-header h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #f3f4f6;
}

.profile-header h2 svg {
  width: 18px;
  height: 18px;
  color: #10b981;
}

.refresh-btn {
  width: 32px;
  height: 32px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  cursor: pointer;
  color: #9ca3af;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.refresh-btn:hover {
  background: rgba(16, 185, 129, 0.1);
  border-color: #10b981;
  color: #10b981;
}

.refresh-btn svg {
  width: 16px;
  height: 16px;
}

.profile-content {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.profile-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 10px;
  padding: 14px;
  display: flex;
  gap: 12px;
}

.card-icon {
  width: 32px;
  height: 32px;
  background: rgba(16, 185, 129, 0.1);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.card-icon svg {
  width: 16px;
  height: 16px;
  color: #10b981;
}

.card-icon.warning {
  background: rgba(239, 68, 68, 0.1);
}

.card-icon.warning svg {
  color: #f87171;
}

.card-info {
  flex: 1;
  min-width: 0;
}

.card-label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: #6b7280;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.progress-bar {
  height: 6px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 6px;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #10b981, #059669);
  border-radius: 3px;
  transition: width 0.4s ease;
}

.progress-text {
  font-size: 13px;
  font-weight: 700;
  color: #10b981;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag {
  padding: 4px 10px;
  background: rgba(124, 58, 237, 0.15);
  color: #a78bfa;
  border-radius: 12px;
  font-size: 12px;
}

.goal-text {
  font-size: 13px;
  color: #d1d5db;
  line-height: 1.6;
}

.weak-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.weak-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  background: rgba(239, 68, 68, 0.08);
  border-radius: 6px;
  font-size: 12px;
}

.weak-item.tentative {
  background: rgba(245, 158, 11, 0.08);
}

.weak-text {
  color: #f87171;
}

.weak-item.tentative .weak-text {
  color: #f59e0b;
}

.weak-confidence {
  color: #6b7280;
  font-weight: 600;
}

.rhythm-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.rhythm-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.rhythm-label {
  font-size: 12px;
  color: #9ca3af;
}

.rhythm-value {
  font-size: 12px;
  color: #f3f4f6;
  font-weight: 500;
}

.interests-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.interest-tag {
  padding: 4px 10px;
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
  border-radius: 12px;
  font-size: 12px;
}

.interest-tag.tentative {
  background: rgba(245, 158, 11, 0.08);
  color: #f59e0b;
}

/* === 滚动条样式 === */
.messages-container::-webkit-scrollbar,
.profile-content::-webkit-scrollbar {
  width: 6px;
}

.messages-container::-webkit-scrollbar-track,
.profile-content::-webkit-scrollbar-track {
  background: transparent;
}

.messages-container::-webkit-scrollbar-thumb,
.profile-content::-webkit-scrollbar-thumb {
  background: #333;
  border-radius: 3px;
}

/* === 响应式布局 === */

/* 平板端 (768px - 1199px) */
@media (max-width: 1199px) and (min-width: 768px) {
  .chat-main {
    width: calc(100% - 280px);
  }

  .profile-sidebar {
    width: 280px;
  }

  .messages-wrapper {
    max-width: 600px;
  }

  .input-wrapper {
    max-width: 600px;
  }

  .input-hint {
    max-width: 600px;
  }
}

/* 移动端 (<768px) */
@media (max-width: 767px) {
  .chat-main {
    width: 100%;
  }

  .profile-sidebar {
    display: none;
  }

  .message-bubble {
    max-width: 88%;
  }

  .messages-container {
    padding: 16px 12px;
  }

  .messages-wrapper {
    max-width: 100%;
  }

  .welcome-message {
    padding: 40px 16px;
  }

  .welcome-icon {
    width: 56px;
    height: 56px;
  }

  .welcome-icon svg {
    width: 28px;
    height: 28px;
  }

  .welcome-message h2 {
    font-size: 20px;
  }

  .message-content {
    font-size: 14px;
    padding: 10px 14px;
  }

  .input-section {
    padding: 12px 12px 16px;
  }

  .send-button {
    width: 40px;
    height: 40px;
  }

  .send-button svg {
    width: 18px;
    height: 18px;
  }
}

/* 超大屏幕 (>1440px) */
@media (min-width: 1440px) {
  .messages-wrapper {
    max-width: 800px;
  }

  .input-wrapper {
    max-width: 800px;
  }

  .input-hint {
    max-width: 800px;
  }
}
</style>
