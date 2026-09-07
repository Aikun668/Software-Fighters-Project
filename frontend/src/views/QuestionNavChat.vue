<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { ArrowUp, BookOpen, ChevronDown, Paperclip, Sparkles } from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import { sendMessageStream, parseSSEStream } from '@/api/chat'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  /** 后端返回的真实错误信息；有值时不得用任何本地内容顶替 */
  error?: string
  streaming?: boolean
}

const router = useRouter()
const route = useRoute()
const prompt = ref('')
const messages = ref<ChatMessage[]>([])
const sending = ref(false)
const resourceMode = computed(() => route.query.mode === 'resource')
const conversationStarted = computed(() => messages.value.length > 0)
const suggestions = [
  { label: '梳理 Transformer 学习路径', icon: Sparkles, path: '/learning-path' },
  { label: '生成一组专项练习', icon: BookOpen, path: '/exercise' },
  { label: '解释反向传播', icon: BookOpen, path: '/learning-resource-network' },
]

const findMessage = (id: string) => messages.value.find((m) => m.id === id)

/**
 * 已完成的对话历史：只收完整且有正文的 user/assistant 轮次。
 * - 正在流式生成、内容为空的 assistant 气泡不进历史；对应 user 也不单独送入模型；
 * - 出错但已有部分正文的 assistant，连同其 user 按用户实际看到的内容保留；
 * - 不含当前这次要发送的消息（后端会把 message 追加为最后一条）。
 */
const buildHistory = () => {
  const history: Array<{ role: 'user' | 'assistant'; content: string }> = []
  let pendingUser: { role: 'user'; content: string } | null = null

  for (const message of messages.value) {
    const content = message.content.trim()
    if (!content) continue
    if (message.role === 'user') {
      pendingUser = { role: 'user', content: message.content }
      continue
    }
    if (pendingUser) {
      history.push(pendingUser, { role: 'assistant', content: message.content })
      pendingUser = null
    }
  }
  return history
}

const scrollToEnd = async () => {
  await nextTick()
  const list = document.querySelector('.conversation-list')
  if (list) list.scrollTop = list.scrollHeight
}

const failMessage = (id: string, error: unknown) => {
  const msg = findMessage(id)
  if (msg) {
    msg.streaming = false
    msg.error = error instanceof Error ? error.message : String(error)
  }
  sending.value = false
}

const send = async () => {
  const text = prompt.value.trim()
  if (!text || sending.value) return

  prompt.value = ''
  const history = buildHistory()
  messages.value.push({ id: `u-${Date.now()}`, role: 'user', content: text })
  const assistantId = `a-${Date.now()}`
  messages.value.push({ id: assistantId, role: 'assistant', content: '', streaming: true })
  sending.value = true
  await scrollToEnd()

  try {
    const stream = await sendMessageStream({ message: text, conversation_id: null, messages: history })
    await parseSSEStream(
      stream,
      (delta) => {
        const msg = findMessage(assistantId)
        if (msg) msg.content += delta
        void scrollToEnd()
      },
      () => {
        const msg = findMessage(assistantId)
        if (msg) {
          msg.streaming = false
          if (!msg.content && !msg.error) {
            msg.error = '后端没有返回任何内容'
          }
        }
        sending.value = false
      },
      (error) => {
        failMessage(assistantId, error)
      },
    )
  } catch (error) {
    failMessage(assistantId, error)
  }
  await scrollToEnd()
}
</script>

<template>
  <section class="chat-page">
    <div class="chat-content">
      <div v-if="!conversationStarted" class="chat-heading">
        <span class="heading-mark"><BookOpen :size="26" :stroke-width="1.25" /></span>
        <div>
          <h1>{{ resourceMode ? '想生成什么学习资料？' : '下午好——今天想研究什么？' }}</h1>
          <p>{{ resourceMode ? '告诉我主题、难度和格式，我会整理成适合你的学习资源。' : '我是你的 AI 学习伙伴，随时为你答疑解惑、规划路径、陪伴进步。' }}</p>
        </div>
      </div>

      <div v-if="!conversationStarted" class="suggestions" aria-label="学习入口">
        <button v-for="item in suggestions" :key="item.label" class="suggestion-row" @click="router.push(item.path)">
          <component :is="item.icon" :size="22" :stroke-width="1.35" />
          <span>{{ item.label }}</span>
          <span class="row-arrow">→</span>
        </button>
      </div>

      <div v-if="conversationStarted" class="conversation-list">
        <div
          v-for="msg in messages"
          :key="msg.id"
          :class="['msg-row', `msg-${msg.role}`]"
        >
          <div class="msg-bubble">
            <template v-if="msg.role === 'assistant'">
              <p v-if="msg.content" class="msg-text">{{ msg.content }}<span v-if="msg.streaming" class="stream-cursor">▍</span></p>
              <p v-else-if="msg.streaming && !msg.error" class="msg-pending">正在思考…</p>
              <p v-if="msg.error" class="msg-error">{{ msg.error }}</p>
            </template>
            <p v-else class="msg-text">{{ msg.content }}</p>
          </div>
        </div>
      </div>

      <div class="composer">
        <textarea v-model="prompt" rows="4" :placeholder="resourceMode ? '输入主题，我生成学习资料...' : '向我提问，或粘贴学习内容...'" @keydown.enter.exact.prevent="send" />
        <div class="composer-toolbar">
          <button class="toolbar-select"><Sparkles :size="16" :stroke-width="1.45" />{{ resourceMode ? '资源生成' : '自动' }} <ChevronDown :size="14" /></button>
          <button><Paperclip :size="17" :stroke-width="1.45" />附件</button>
          <button><BookOpen :size="17" :stroke-width="1.45" />学习方式 <ChevronDown :size="14" /></button>
          <button class="send-button" aria-label="发送" :disabled="sending" @click="send"><ArrowUp :size="20" :stroke-width="1.6" /></button>
        </div>
      </div>
      <p class="input-hint">按 Enter 发送，Shift + Enter 换行</p>
    </div>
  </section>
</template>

<style scoped>
.chat-page { min-height: 100vh; display: flex; justify-content: center; padding: 0 40px; }.chat-content { width: min(920px, 100%); padding-top: 22vh; display: flex; flex-direction: column; min-height: 100vh; }.heading-mark { display: grid; place-items: center; margin-top: 9px; color: var(--ink); }.chat-heading { display: flex; align-items: flex-start; gap: 18px; }.chat-heading h1 { margin: 0; font-family: var(--font-display); font-size: clamp(34px, 4vw, 52px); font-weight: 500; letter-spacing: -.04em; line-height: 1.18; }.chat-heading p { margin: 14px 0 0; color: var(--muted); font-size: 15px; }.suggestions { margin: 50px 0 68px; border-top: 1px solid var(--line); }.suggestion-row { display: flex; align-items: center; gap: 17px; width: 100%; min-height: 64px; padding: 0 9px; border: 0; border-bottom: 1px solid var(--line); background: transparent; color: var(--ink); cursor: pointer; text-align: left; font-size: 15px; }.suggestion-row:hover { background: rgba(255,255,255,.42); }.suggestion-row svg { color: var(--muted); }.row-arrow { margin-left: auto; color: var(--muted); font-size: 23px; font-weight: 300; }.composer { overflow: hidden; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,254,250,.72); box-shadow: 0 10px 28px rgba(122,105,82,.05); }.composer textarea { display: block; width: 100%; min-height: 155px; padding: 21px 23px; resize: vertical; border: 0; outline: 0; background: transparent; color: var(--ink); font-size: 15px; }.composer textarea::placeholder { color: var(--soft-muted); }.composer-toolbar { display: flex; align-items: center; gap: 26px; min-height: 64px; padding: 0 18px 0 21px; border-top: 1px solid var(--line); }.composer-toolbar button { display: inline-flex; align-items: center; gap: 7px; border: 0; background: transparent; color: var(--muted); cursor: pointer; font-size: 13px; }.composer-toolbar button:hover { color: var(--ink); }.toolbar-select { padding-right: 17px !important; border-right: 1px solid var(--line) !important; }.send-button { justify-content: center; width: 40px; height: 40px; margin-left: auto; border-radius: 50% !important; background: var(--clay) !important; color: #fffaf6 !important; }.send-button:hover { background: #b97c65 !important; }.send-button:disabled { opacity: .55; cursor: not-allowed; }
/* ── 对话态 ─────────────────────────────────────────────── */
.chat-content.in-conversation, .chat-content:has(.conversation-list) { padding-top: 6vh; }
.conversation-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 18px; padding: 8px 2px 24px; margin-bottom: 16px; }
.msg-row { display: flex; }
.msg-user { justify-content: flex-end; }
.msg-assistant { justify-content: flex-start; }
.msg-bubble { max-width: 78%; padding: 13px 17px; border-radius: 14px; font-size: 15px; line-height: 1.65; }
.msg-user .msg-bubble { background: var(--clay); color: #fffaf6; border-bottom-right-radius: 4px; }
.msg-assistant .msg-bubble { background: rgba(255,254,250,.85); border: 1px solid var(--line); color: var(--ink); border-bottom-left-radius: 4px; }
.msg-text { margin: 0; white-space: pre-wrap; word-break: break-word; }
.msg-error { margin: 0; color: #b4483c; font-size: 14px; }
.msg-pending { margin: 0; color: var(--muted); }
.stream-cursor { display: inline-block; margin-left: 1px; color: var(--clay); animation: blink 1s steps(2) infinite; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
.input-hint { margin: 12px 3px 28px; color: var(--muted); font-size: 12px; }
@media (max-width: 900px) { .chat-page { padding: 0 24px; }.chat-content { padding-top: 13vh; }.chat-heading h1 { font-size: 36px; }.suggestions { margin: 38px 0 46px; } }
</style>
