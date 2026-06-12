<template>
  <div class="chat-page">
    <!-- 左侧历史对话列表 -->
    <aside class="conversation-sidebar">
      <div class="sidebar-header">
        <h2>历史对话</h2>
        <button class="new-chat-btn" @click="createNewChat">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="12" y1="5" x2="12" y2="19"/>
            <line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          <span>新对话</span>
        </button>
      </div>
      
      <div class="conversation-list">
        <div
          v-for="conv in conversations"
          :key="conv.id"
          :class="['conversation-item', { active: currentConversation?.id === conv.id }]"
          @click="selectConversation(conv)"
        >
          <div class="conv-icon">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
          </div>
          <div class="conv-info">
            <h3 class="conv-title">{{ conv.title }}</h3>
            <p class="conv-preview">{{ conv.preview }}</p>
          </div>
          <span class="conv-time">{{ conv.time }}</span>
        </div>
      </div>
    </aside>

    <!-- 中间聊天区域 -->
    <main class="chat-main">
      <!-- 聊天头部 -->
      <div v-if="currentConversation" class="chat-header">
        <h2>{{ currentConversation.title }}</h2>
        <div class="header-actions">
          <button class="action-btn" @click="renameConversation">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
          </button>
          <button class="action-btn" @click="deleteConversation">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18"/>
              <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>
              <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- 欢迎页面 -->
      <div v-if="!currentConversation" class="welcome-screen">
        <div class="welcome-icon">
          <svg viewBox="0 0 24 24" width="64" height="64" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
        </div>
        <h1>智能对话助手</h1>
        <p>选择一个对话开始，或创建新对话</p>
        <button class="start-btn" @click="createNewChat">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
          开始新对话
        </button>
      </div>

      <!-- 消息列表 -->
      <div v-else ref="messageContainer" class="message-container">
        <div class="messages-wrapper">
          <div
            v-for="(msg, index) in messages"
            :key="msg.id"
            :id="`message-${msg.id}`"
            :class="['message-item', `message-${msg.role}`]"
          >
            <div class="message-avatar">
              <div v-if="msg.role === 'user'" class="avatar-user">
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                  <circle cx="12" cy="7" r="4"/>
                </svg>
              </div>
              <div v-else class="avatar-assistant">
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                  <path d="M2 17l10 5 10-5"/>
                  <path d="M2 12l10 5 10-5"/>
                </svg>
              </div>
            </div>
            <div class="message-content">
              <div v-if="msg.role === 'assistant'" class="message-header">
                <span class="sender-name">AI助手</span>
                <span class="message-time">{{ msg.time }}</span>
              </div>
              <div class="message-body">{{ msg.content }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 输入区域 -->
      <div v-if="currentConversation" class="input-section">
        <div class="input-wrapper">
          <textarea
            v-model="inputMessage"
            placeholder="输入你的问题..."
            rows="1"
            @keydown.enter.exact.prevent="sendMessage"
            @input="autoResize"
            ref="textareaRef"
          ></textarea>
          <button
            class="send-btn"
            :disabled="!inputMessage.trim()"
            @click="sendMessage"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="22" y1="2" x2="11" y2="13"/>
              <polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>
        <p class="input-hint">按 Enter 发送</p>
      </div>
    </main>

    <!-- 右侧问题点导航 -->
    <aside class="questions-sidebar" v-if="currentConversation && userQuestions.length > 0">
      <div class="sidebar-header">
        <h3>问题导航</h3>
        <span class="count">{{ userQuestions.length }} 个问题</span>
      </div>
      
      <div class="questions-track">
        <div
          v-for="(question, index) in userQuestions"
          :key="question.id"
          :class="['question-dot', { active: activeQuestionIndex === index }]"
          :title="question.text"
          @mouseenter="hoveredQuestion = question"
          @mouseleave="hoveredQuestion = null"
          @click="scrollToMessage(question.id)"
        >
          <span class="dot-number">{{ index + 1 }}</span>
        </div>
        
        <!-- 悬停提示框 -->
        <div
          v-if="hoveredQuestion"
          class="tooltip"
          :style="{ top: getTooltipPosition(hoveredQuestion) + 'px' }"
        >
          <div class="tooltip-content">
            <p>{{ hoveredQuestion.text }}</p>
            <span class="tooltip-arrow"></span>
          </div>
        </div>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, nextTick, computed } from 'vue'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  time: string
}

interface Conversation {
  id: string
  title: string
  preview: string
  time: string
}

interface QuestionPoint {
  id: string
  text: string
  messageId: string
}

// 状态
const conversations = ref<Conversation[]>([
  { id: '1', title: '机器学习入门', preview: '什么是机器学习？', time: '10分钟前' },
  { id: '2', title: 'Python学习', preview: '如何安装Python？', time: '1小时前' },
  { id: '3', title: '深度学习', preview: '神经网络是什么？', time: '昨天' },
  { id: '4', title: '数据结构', preview: '什么是二叉树？', time: '2天前' }
])

const currentConversation = ref<Conversation | null>(null)
const messages = ref<Message[]>([])
const userQuestions = ref<QuestionPoint[]>([])
const inputMessage = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const messageContainer = ref<HTMLElement | null>(null)
const hoveredQuestion = ref<QuestionPoint | null>(null)
const activeQuestionIndex = ref(-1)

// 计算属性
const activeQuestion = computed(() => {
  return userQuestions.value[activeQuestionIndex.value] || null
})

// 选择对话
const selectConversation = (conv: Conversation) => {
  currentConversation.value = conv
  loadMessages(conv.id)
}

// 加载消息
const loadMessages = (convId: string) => {
  messages.value = [
    { id: 'm1', role: 'user', content: '什么是机器学习？', time: '10:30' },
    { id: 'm2', role: 'assistant', content: '机器学习是人工智能的一个分支，它使计算机系统能够从数据中学习并改进其性能，而无需进行明确编程。', time: '10:31' },
    { id: 'm3', role: 'user', content: '机器学习有哪些主要类型？', time: '10:32' },
    { id: 'm4', role: 'assistant', content: '主要分为三类：监督学习、无监督学习和强化学习。监督学习使用标注数据进行训练，无监督学习从无标注数据中发现模式，强化学习通过试错学习。', time: '10:33' },
    { id: 'm5', role: 'user', content: '监督学习和无监督学习有什么区别？', time: '10:35' },
    { id: 'm6', role: 'assistant', content: '监督学习需要标注数据，目标是预测或分类。无监督学习不需要标注，目标是发现数据中的结构，如聚类或降维。', time: '10:36' },
    { id: 'm7', role: 'user', content: '请推荐一些机器学习入门书籍', time: '10:38' },
    { id: 'm8', role: 'assistant', content: '推荐《机器学习实战》、《统计学习方法》和《Hands-On Machine Learning with Scikit-Learn, Keras, and TensorFlow》。', time: '10:40' }
  ]
  
  // 提取用户问题作为问题点
  userQuestions.value = messages.value
    .filter(m => m.role === 'user')
    .map((msg, index) => ({
      id: `q-${index}`,
      text: msg.content,
      messageId: msg.id
    }))
  
  activeQuestionIndex.value = -1
}

// 创建新对话
const createNewChat = () => {
  const newConv: Conversation = {
    id: Date.now().toString(),
    title: '新对话',
    preview: '开始新的对话...',
    time: '刚刚'
  }
  conversations.value.unshift(newConv)
  currentConversation.value = newConv
  messages.value = []
  userQuestions.value = []
}

// 发送消息
const sendMessage = async () => {
  if (!inputMessage.value.trim()) return
  
  const userMsg: Message = {
    id: `m-${Date.now()}`,
    role: 'user',
    content: inputMessage.value.trim(),
    time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  
  messages.value.push(userMsg)
  
  // 添加到问题点
  userQuestions.value.push({
    id: `q-${userQuestions.value.length}`,
    text: userMsg.content,
    messageId: userMsg.id
  })
  
  inputMessage.value = ''
  
  // 滚动到底部
  await nextTick()
  scrollToBottom()
  
  // 模拟AI回复
  setTimeout(() => {
    const assistantMsg: Message = {
      id: `m-${Date.now()}`,
      role: 'assistant',
      content: '这是一个很好的问题！让我来为您解答...',
      time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    }
    messages.value.push(assistantMsg)
    
    nextTick(() => {
      scrollToBottom()
    })
  }, 1000)
}

// 滚动到底部
const scrollToBottom = () => {
  if (messageContainer.value) {
    messageContainer.value.scrollTop = messageContainer.value.scrollHeight
  }
}

// 滚动到指定消息
const scrollToMessage = (questionId: string) => {
  const question = userQuestions.value.find(q => q.id === questionId)
  if (!question) return
  
  const messageId = question.messageId
  const element = document.getElementById(`message-${messageId}`)
  
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'center' })
    
    // 更新激活状态
    const index = userQuestions.value.findIndex(q => q.id === questionId)
    activeQuestionIndex.value = index
  }
}

// 获取提示框位置
const getTooltipPosition = (question: QuestionPoint) => {
  const index = userQuestions.value.indexOf(question)
  const dotSpacing = 40
  return index * dotSpacing + 20
}

// 自动调整textarea高度
const autoResize = () => {
  nextTick(() => {
    if (textareaRef.value) {
      textareaRef.value.style.height = 'auto'
      const scrollHeight = textareaRef.value.scrollHeight
      const maxHeight = 120
      textareaRef.value.style.height = Math.min(scrollHeight, maxHeight) + 'px'
    }
  })
}

// 重命名对话
const renameConversation = () => {
  if (!currentConversation.value) return
  const newTitle = prompt('请输入对话名称', currentConversation.value.title)
  if (newTitle && newTitle.trim()) {
    currentConversation.value.title = newTitle.trim()
  }
}

// 删除对话
const deleteConversation = () => {
  if (!currentConversation.value) return
  if (confirm('确定删除这个对话吗？')) {
    const index = conversations.value.findIndex(c => c.id === currentConversation.value?.id)
    if (index !== -1) {
      conversations.value.splice(index, 1)
      currentConversation.value = conversations.value[0] || null
      if (currentConversation.value) {
        loadMessages(currentConversation.value.id)
      }
    }
  }
}
</script>

<style scoped>
.chat-page {
  display: flex;
  width: 100%;
  height: calc(100vh - 64px);
  background: var(--bg-page);
  overflow: hidden;
}

/* 左侧对话列表 */
.conversation-sidebar {
  width: 280px;
  background: var(--bg-card);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-header {
  padding: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border-color);
}

.sidebar-header h2 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.new-chat-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: var(--primary-bg);
  color: var(--primary-color);
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.new-chat-btn:hover {
  background: var(--primary-color);
  color: white;
}

.conversation-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.conversation-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  margin-bottom: 4px;
}

.conversation-item:hover {
  background: var(--card-bg);
}

.conversation-item.active {
  background: var(--primary-bg);
}

.conv-icon {
  width: 36px;
  height: 36px;
  border-radius: 9px;
  background: var(--card-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary-color);
  flex-shrink: 0;
}

.conv-info {
  flex: 1;
  min-width: 0;
}

.conv-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  margin: 0 0 4px 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-preview {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-time {
  font-size: 11px;
  color: var(--text-placeholder);
  flex-shrink: 0;
}

/* 中间聊天区域 */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-header {
  padding: 16px 24px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chat-header h2 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.action-btn:hover {
  background: var(--card-bg);
  color: var(--text-primary);
}

/* 欢迎页面 */
.welcome-screen {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  text-align: center;
}

.welcome-icon {
  width: 100px;
  height: 100px;
  border-radius: 24px;
  background: var(--gradient-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  margin-bottom: 24px;
  box-shadow: 0 10px 30px rgba(34, 197, 94, 0.3);
}

.welcome-screen h1 {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 8px 0;
}

.welcome-screen p {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0 0 24px 0;
}

.start-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
  background: var(--gradient-primary);
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 4px 12px rgba(34, 197, 94, 0.25);
}

.start-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(34, 197, 94, 0.35);
}

/* 消息容器 */
.message-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.messages-wrapper {
  max-width: 720px;
  margin: 0 auto;
}

.message-item {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.message-item.message-user {
  flex-direction: row-reverse;
}

.message-avatar {
  flex-shrink: 0;
}

.avatar-user {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #8b5cf6, #6d28d9);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}

.avatar-assistant {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #10b981, #059669);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}

.message-content {
  max-width: 70%;
}

.message-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 6px;
}

.sender-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.message-time {
  font-size: 11px;
  color: var(--text-placeholder);
}

.message-body {
  padding: 12px 16px;
  border-radius: 16px;
  font-size: 14px;
  line-height: 1.6;
}

.message-user .message-body {
  background: linear-gradient(135deg, #8b5cf6, #6d28d9);
  color: white;
  border-bottom-right-radius: 4px;
}

.message-assistant .message-body {
  background: var(--card-bg);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-bottom-left-radius: 4px;
}

/* 输入区域 */
.input-section {
  padding: 16px 24px;
  background: var(--bg-card);
  border-top: 1px solid var(--border-color);
}

.input-wrapper {
  display: flex;
  gap: 12px;
  max-width: 720px;
  margin: 0 auto;
}

.input-wrapper textarea {
  flex: 1;
  min-height: 48px;
  max-height: 120px;
  padding: 12px 16px;
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  font-size: 14px;
  color: var(--text-primary);
  resize: none;
  transition: all 0.2s ease;
}

.input-wrapper textarea:focus {
  outline: none;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px var(--primary-bg);
}

.input-wrapper textarea::placeholder {
  color: var(--text-placeholder);
}

.send-btn {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: var(--gradient-primary);
  border: none;
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(34, 197, 94, 0.3);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.input-hint {
  text-align: center;
  font-size: 12px;
  color: var(--text-placeholder);
  margin: 8px 0 0 0;
}

/* 右侧问题导航 */
.questions-sidebar {
  width: 60px;
  background: var(--bg-card);
  border-left: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.questions-sidebar .sidebar-header {
  padding: 12px 8px;
  text-align: center;
}

.questions-sidebar .sidebar-header h3 {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 0 0 4px 0;
}

.count {
  font-size: 11px;
  color: var(--primary-color);
  font-weight: 600;
}

.questions-track {
  flex: 1;
  padding: 16px 0;
  position: relative;
}

.question-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--border-color);
  margin: 0 auto 28px auto;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.question-dot:hover {
  transform: scale(1.5);
  background: var(--primary-color);
}

.question-dot.active {
  background: var(--primary-color);
  box-shadow: 0 0 0 4px var(--primary-bg);
}

.dot-number {
  font-size: 8px;
  color: white;
  font-weight: 600;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.question-dot:hover .dot-number,
.question-dot.active .dot-number {
  opacity: 1;
}

/* 悬停提示框 */
.tooltip {
  position: absolute;
  right: 100%;
  margin-right: 16px;
  z-index: 100;
  pointer-events: none;
}

.tooltip-content {
  background: rgba(17, 24, 39, 0.95);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 12px 16px;
  max-width: 200px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
}

.tooltip-content p {
  font-size: 13px;
  color: var(--text-primary);
  margin: 0;
  line-height: 1.5;
}

.tooltip-arrow {
  position: absolute;
  right: -6px;
  top: 50%;
  transform: translateY(-50%);
  width: 0;
  height: 0;
  border-top: 6px solid transparent;
  border-bottom: 6px solid transparent;
  border-left: 6px solid var(--border-color);
}

/* 响应式 */
@media (max-width: 1024px) {
  .conversation-sidebar {
    width: 240px;
  }
  
  .questions-sidebar {
    width: 50px;
  }
}

@media (max-width: 768px) {
  .conversation-sidebar {
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    z-index: 100;
    transform: translateX(-100%);
    transition: transform 0.3s ease;
  }
  
  .conversation-sidebar.show {
    transform: translateX(0);
  }
  
  .questions-sidebar {
    display: none;
  }
  
  .chat-main {
    width: 100%;
  }
  
  .message-content {
    max-width: 85%;
  }
}
</style>
