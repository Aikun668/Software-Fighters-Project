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
                <span v-if="msg.mode" class="mode-tag">{{ getModeLabel(msg.mode) }}</span>
                <span class="message-time">{{ msg.time }}</span>
              </div>
              <div class="message-body" v-if="msg.role === 'user'">{{ msg.content }}</div>
              <div class="message-body markdown-body" v-else v-html="renderMarkdown(msg.content)">
                
              </div>
              <!-- 流式输出时的加载指示器 -->
              <div v-if="msg.streaming" class="typing-indicator">
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
              </div>
              <!-- 错误提示和重试按钮 -->
              <div v-if="streamError && !msg.streaming && msg.role === 'assistant' && messages.indexOf(msg) === messages.length - 1" class="error-actions">
                <span class="error-text">{{ streamError }}</span>
                <button class="retry-btn" @click="retryLastMessage">
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="23 4 23 10 17 10"/>
                    <polyline points="1 20 1 14 7 14"/>
                    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                  </svg>
                  重试
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 输入区域 -->
      <div v-if="currentConversation" class="input-section">
        <div class="input-wrapper">
          <textarea
            v-model="inputMessage"
            :placeholder="isStreaming ? 'AI正在回答中...' : '输入你的问题...'"
            rows="1"
            @keydown.enter.exact.prevent="sendMessage"
            @input="autoResize"
            ref="textareaRef"
            :disabled="isStreaming"
          ></textarea>
          <button
            class="send-btn"
            :disabled="!inputMessage.trim() || isStreaming"
            @click="sendMessage"
          >
            <svg v-if="!isStreaming" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="22" y1="2" x2="11" y2="13"/>
              <polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
            <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" class="loading-icon">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 6v6l4 2"/>
            </svg>
          </button>
        </div>
        <p class="input-hint">
          <span v-if="isStreaming" class="streaming-hint">
            <span class="hint-dot"></span>
            正在生成回答...
          </span>
          <span v-else>按 Enter 发送</span>
        </p>
      </div>
    </main>

    <!-- 右侧问题点导航 -->
    <aside class="questions-sidebar" v-if="currentConversation && userQuestions.length > 0">
      <div class="sidebar-header">
        <h3>问题导航</h3>
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
import { ref, reactive, nextTick, computed, onMounted } from 'vue'
import { marked } from 'marked'
//#ts-ignore
import { sendMessageStream, parseSSEStream } from '@/api/chat'
import { createConversation, getConversations, getConversationMessages, deleteConversation as deleteConversationAPI } from '@/api/conversations'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  time: string
  streaming?: boolean
  mode?: string
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

// 配置 marked 支持表格和其他格式
marked.setOptions({
  breaks: true,
  gfm: true
})

// Markdown 渲染函数
const renderMarkdown = (content: string): string => {
  if (!content) return ''
  try {
    return marked(content)
  } catch (e) {
    console.error('[Chat] Markdown 渲染错误:', e)
    return content
  }
}

// 状态
const conversations = ref<Conversation[]>([])
const currentConversation = ref<Conversation | null>(null)
const messages = ref<Message[]>([])
const userQuestions = ref<QuestionPoint[]>([])
const inputMessage = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const messageContainer = ref<HTMLElement | null>(null)
const hoveredQuestion = ref<QuestionPoint | null>(null)
const activeQuestionIndex = ref(-1)
const isStreaming = ref(false)  // 流式输出状态
const streamError = ref<string | null>(null)  // 流式错误信息

// 获取模式标签
const getModeLabel = (mode: string): string => {
  const modeMap: Record<string, string> = {
    tutor: '导师答疑',
    path: '学习路径',
    resource: '资源生成',
    profile: '画像构建',
    chat: '普通聊天'
  }
  return modeMap[mode] || mode
}

// 加载会话列表
const loadConversations = async () => {
  try {
    const convList = await getConversations()
    conversations.value = convList.map(conv => ({
      id: conv.id?.toString() || '',
      title: conv.title || '未命名对话',
      preview: conv.preview || '',
      time: conv.updatedAt || conv.createdAt || ''
    }))
  } catch (error) {
    console.error('加载会话列表失败:', error)
    // 使用模拟数据作为降级方案
    conversations.value = [
      { id: '1', title: '机器学习入门', preview: '什么是机器学习？', time: '10分钟前' },
      { id: '2', title: 'Python学习', preview: '如何安装Python？', time: '1小时前' },
      { id: '3', title: '深度学习', preview: '神经网络是什么？', time: '昨天' },
      { id: '4', title: '数据结构', preview: '什么是二叉树？', time: '2天前' }
    ]
  }
}

// 初始化
onMounted(() => {
  loadConversations()
})

// 选择对话
const selectConversation = (conv: Conversation) => {
  currentConversation.value = conv
  loadMessages(conv.id)
}

// 加载消息
const loadMessages = async (convId: string) => {
  try {
    // 调用API加载消息历史
    const msgList = await getConversationMessages(parseInt(convId))
    
    messages.value = msgList.map(msg => ({
      id: msg.id?.toString() || `m-${Date.now()}`,
      role: msg.role as 'user' | 'assistant',
      content: msg.content || '',
      time: msg.createdAt || '',
      mode: msg.mode
    }))
    
    // 提取用户问题作为问题点
    userQuestions.value = messages.value
      .filter(m => m.role === 'user')
      .map((msg, index) => ({
        id: `q-${index}`,
        text: msg.content,
        messageId: msg.id
      }))
    
    activeQuestionIndex.value = -1
    
    // 滚动到底部
    await nextTick()
    scrollToBottom()
  } catch (error) {
    console.error('加载消息失败:', error)
    // 使用模拟数据作为降级方案
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
    
    // 滚动到底部
    await nextTick()
    scrollToBottom()
  }
}

// 创建新对话
const createNewChat = async () => {
  try {
    // 调用API创建会话
    const newConvData = await createConversation()
    
    const newConv: Conversation = {
      id: newConvData.id?.toString() || Date.now().toString(),
      title: newConvData.title || '新对话',
      preview: '开始新的对话...',
      time: '刚刚'
    }
    
    conversations.value.unshift(newConv)
    currentConversation.value = newConv
    messages.value = []
    userQuestions.value = []
  } catch (error) {
    console.error('创建会话失败:', error)
    // 降级方案：本地创建
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
}

// 发送消息
const sendMessage = async () => {
  console.log('[Chat] 开始发送消息')
  if (!inputMessage.value.trim() || isStreaming.value) {
    console.log('[Chat] 消息为空或正在流式输出，跳过')
    return
  }
  
  // 清除之前的错误状态
  streamError.value = null
  
  const userMsg: Message = {
    id: `m-${Date.now()}`,
    role: 'user',
    content: inputMessage.value.trim(),
    time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  
  messages.value.push(userMsg)
  console.log('[Chat] 用户消息已添加:', userMsg.content.substring(0, 30))
  
  // 添加到问题点
  userQuestions.value.push({
    id: `q-${userQuestions.value.length}`,
    text: userMsg.content,
    messageId: userMsg.id
  })
  
  inputMessage.value = ''
  isStreaming.value = true
  
  // 滚动到底部
  await nextTick()
  scrollToBottom()
  
  // 创建AI回复占位消息（使用reactive确保响应式更新）
  const assistantMsg = reactive<Message>({
    id: `m-${Date.now()}`,
    role: 'assistant',
    content: '',
    time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
    streaming: true,
    mode: 'chat'
  })
  messages.value.push(assistantMsg)
  console.log('[Chat] AI占位消息已添加')
  // 滚动到底部
    await nextTick()
    scrollToBottom()
    
  try {
    console.log('[Chat] 调用 sendMessageStream...')
    const stream = await sendMessageStream({
      message: userMsg.content,
      conversation_id: currentConversation.value ? parseInt(currentConversation.value.id) : null
    })
    console.log('[Chat] 获取到数据流，开始解析...')
    
    await parseSSEStream(
      stream,
      (delta, mode) => {
        // 逐字追加文本到消息内容
        assistantMsg.content += delta
        assistantMsg.mode = mode
        // 滚动到底部显示最新内容
        nextTick(() => {
          scrollToBottom()
        })
      },
      () => {
        console.log('[Chat] 流式传输完成，最终内容:', assistantMsg.content)
        assistantMsg.streaming = false
        isStreaming.value = false
        updateConversationPreview(userMsg.content, assistantMsg.content)
      },
      (error) => {
        console.error('[Chat] SSE错误:', error)
        streamError.value = '连接中断，请点击重试'
        assistantMsg.content = '抱歉，连接过程中出现问题。'
        assistantMsg.streaming = false
        isStreaming.value = false
      }
    )
  } catch (error) {
    console.error('[Chat] 发送消息异常:', error)
    streamError.value = '发送失败，请检查网络连接后重试'
    // 模拟回复作为降级方案
    assistantMsg.content = '这是一个很好的问题！让我来为您解答...\n\n根据您的问题，我可以提供一些相关的学习建议和资源。如果您需要更详细的信息，可以继续提问。'
    assistantMsg.streaming = false
    isStreaming.value = false
    updateConversationPreview(userMsg.content, assistantMsg.content)
  }
  
  nextTick(() => {
    scrollToBottom()
  })
}

// 重试发送消息
const retryLastMessage = async () => {
  if (messages.value.length < 2) return
  
  // 找到最后一条用户消息
  const lastUserMsg = [...messages.value].reverse().find(m => m.role === 'user')
  if (!lastUserMsg) return
  
  // 移除最后一条失败的AI回复
  const lastAssistantMsg = messages.value[messages.value.length - 1]
  if (lastAssistantMsg.role === 'assistant') {
    messages.value.pop()
  }
  
  // 重新发送
  inputMessage.value = lastUserMsg.content
  streamError.value = null
  
  // 移除用户消息（因为sendMessage会重新添加）
  messages.value = messages.value.filter(m => m.id !== lastUserMsg.id)
  userQuestions.value = userQuestions.value.filter(q => q.messageId !== lastUserMsg.id)
  
  await sendMessage()
}

// 更新对话预览
const updateConversationPreview = (userMsg: string, assistantMsg: string) => {
  if (currentConversation.value) {
    currentConversation.value.preview = userMsg.length > 30 ? userMsg.substring(0, 30) + '...' : userMsg
    if (assistantMsg.length > 20) {
      currentConversation.value.preview = assistantMsg.substring(0, 20) + '...'
    }
    currentConversation.value.time = '刚刚'
  }
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
const deleteConversation = async () => {
  if (!currentConversation.value) return
  if (confirm('确定删除这个对话吗？')) {
    try {
      // 调用API删除会话
      await deleteConversationAPI(parseInt(currentConversation.value.id))
      
      const index = conversations.value.findIndex(c => c.id === currentConversation.value?.id)
      if (index !== -1) {
        conversations.value.splice(index, 1)
        currentConversation.value = conversations.value[0] || null
        if (currentConversation.value) {
          loadMessages(currentConversation.value.id)
        }
      }
    } catch (error) {
      console.error('删除会话失败:', error)
      // 降级方案：本地删除
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
  gap: 8px;
  margin-bottom: 6px;
}

.sender-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.mode-tag {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(34, 197, 94, 0.15);
  color: var(--primary-color);
  font-weight: 500;
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

.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 8px 16px;
}

.typing-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-secondary);
  animation: typing 1.4s infinite ease-in-out;
}

.typing-dot:nth-child(1) { animation-delay: 0s; }
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
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

.input-wrapper textarea:disabled {
  background: var(--bg-page);
  cursor: not-allowed;
  opacity: 0.7;
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

/* 加载图标动画 */
.loading-icon {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 流式输出提示 */
.streaming-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--primary-color);
}

.hint-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary-color);
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.4; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1); }
}

/* 错误提示和重试按钮 */
.error-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
  padding: 8px 12px;
  background: var(--danger-bg);
  border-radius: 8px;
}

.error-text {
  color: var(--danger-color);
  font-size: 13px;
}

.retry-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: var(--danger-color);
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.retry-btn:hover {
  opacity: 0.9;
  transform: translateY(-1px);
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

/* Markdown 样式 */
.markdown-body {
  padding: 12px 16px;
  border-radius: 16px;
  font-size: 14px;
  line-height: 1.6;
}

.markdown-body :deep(pre) {
  background-color: #0F172A;
  padding: 12px 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 12px 0;
}

.markdown-body :deep(code) {
  background-color: rgba(255, 255, 255, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'Fira Code', 'Consolas', monospace;
}

.markdown-body :deep(pre code) {
  background-color: transparent;
  padding: 0;
  color: #E2E8F0;
}

.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border-color);
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--border-color);
  padding: 10px 14px;
  text-align: left;
}

.markdown-body :deep(th) {
  background-color: rgba(34, 197, 94, 0.1);
  font-weight: 600;
}

.markdown-body :deep(tr:nth-child(even)) {
  background-color: rgba(0, 0, 0, 0.02);
}

.markdown-body :deep(a) {
  color: var(--primary-color);
  text-decoration: none;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--primary-color);
  padding-left: 12px;
  color: var(--text-secondary);
  margin: 12px 0;
  font-style: italic;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin: 16px 0 8px;
  font-weight: 600;
  color: var(--text-primary);
}

.markdown-body :deep(h1) { font-size: 18px; }
.markdown-body :deep(h2) { font-size: 16px; }
.markdown-body :deep(h3) { font-size: 15px; }
.markdown-body :deep(h4) { font-size: 14px; }

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 20px;
  margin: 8px 0;
}

.markdown-body :deep(li) {
  margin: 4px 0;
}

.markdown-body :deep(p) {
  margin: 8px 0;
}

.markdown-body :deep(strong) {
  font-weight: 600;
  color: var(--text-primary);
}

.markdown-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--border-color);
  margin: 16px 0;
}

.markdown-body :deep(img) {
  max-width: 100%;
  border-radius: 8px;
}
</style>
