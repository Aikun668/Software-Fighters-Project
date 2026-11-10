<script setup lang="ts">
import { computed, inject, nextTick, ref, watch } from 'vue'
import { BookOpen, Sparkles } from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import { sendMessageStream, parseSSEStream } from '@/api/chat'
import { getConversationMessages } from '@/api/conversations'
import { uploadFile } from '@/api/files'
import { consumeLearningDraft } from '@/utils/learningDraft'
import { resolveErrorMessage } from '@/utils/request'
import ChatComposer from '@/components/chat/ChatComposer.vue'
import AdaptivePlanWorkspace from '@/components/plans/AdaptivePlanWorkspace.vue'
import ChatThread from '@/components/chat/ChatThread.vue'
import type { ChatAttachment, ChatMessage, ChatMode, ChatStyle } from '@/components/chat/chat-types'
import type { DispatchResult } from '@/components/chat/ui-blocks/registry'

const router = useRouter()
const route = useRoute()
const planPanelOpen = ref(typeof route.query.planId === 'string')
const prompt = ref(typeof route.query.learningContext === 'string' ? consumeLearningDraft(route.query.learningContext) : typeof route.query.draft === 'string' ? route.query.draft.slice(0, 16000) : '')
const messages = ref<ChatMessage[]>([])
/** T007：消息 id → visualization block 列表（onVisualization 回调按当前助手消息归位） */
const visualizationBlocks = ref<Record<string, DispatchResult[]>>({})
const currentConversationId = ref<number | null>(null)
const sending = ref(false)
/** 阶段 D：当前执行进度文案（来自后端 `progress` 事件；先按占位文案展示） */
const progressText = ref('')
const resourceMode = computed(() => route.query.mode === 'resource')
const conversationStarted = computed(() => messages.value.length > 0)
const selectedMode = ref<ChatMode>(resourceMode.value ? 'resource' : 'auto')
const selectedStyle = ref<ChatStyle>('standard')
const attachments = ref<ChatAttachment[]>([])
const uploadingFile = ref(false)
const uploadError = ref('')
const modeOptions: Array<{ value: ChatMode; label: string }> = [
  { value: 'auto', label: '自动' },
  { value: 'plan', label: '学习规划' },
  { value: 'resource', label: '资源生成' },
  { value: 'exercise', label: '练习生成' },
]
const styleOptions: Array<{ value: ChatStyle; label: string }> = [
  { value: 'standard', label: '标准答疑' },
  { value: 'socratic', label: '苏格拉底式' },
]
const selectedModeLabel = computed(() => modeOptions.find((item) => item.value === selectedMode.value)?.label ?? '自动')
const selectedStyleLabel = computed(() => styleOptions.find((item) => item.value === selectedStyle.value)?.label ?? '标准答疑')
const suggestions = [
  { label: '梳理 Transformer 学习路径', icon: Sparkles, path: '/learning-path' },
  { label: '生成一组专项练习', icon: BookOpen, path: '/exercise' },
  { label: '解释反向传播', icon: BookOpen, path: '/learning-resource-network' },
]
const refreshConversations = inject<() => void>('refreshConversations')

const chooseMode = (mode: ChatMode) => {
  selectedMode.value = mode
}

const chooseStyle = (style: ChatStyle) => {
  selectedStyle.value = style
}

/** 单个附件体积上限，与后端 multipart 上限保持一致（20MB） */
const MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024

/** 剪贴板截图常常没有文件名，按 MIME 兜底一个可读名字 */
const fallbackAttachmentName = (file: File) => {
  if (file.name && file.name.trim()) return file.name
  const ext = file.type.split('/')[1] || 'png'
  return `粘贴的附件-${new Date().toLocaleTimeString('zh-CN', { hour12: false })}.${ext}`
}

/**
 * 上传一个或多个附件（文件选择、粘贴、拖拽共用）。
 *
 * 附件不限类型：任何文件都能上传进附件条。只有图片会被标记为
 * `isImage`，发送时作为多模态输入放进 `images`；其他附件仍随消息上传，
 * 只是 AI 当前只消费图片。
 *
 * 逐个串行上传：任一失败只记录错误并继续处理后面的文件，
 * 已成功的条目保留在附件条里，避免一次失败把整批都丢掉。
 */
const handleFileUploads = async (files: File[]) => {
  if (!files.length) return
  uploadError.value = ''

  const accepted: File[] = []
  for (const file of files) {
    if (file.size > MAX_ATTACHMENT_BYTES) {
      uploadError.value = '附件过大，请控制在 20MB 以内'
      continue
    }
    accepted.push(file)
  }
  if (!accepted.length) return

  uploadingFile.value = true
  try {
    for (const file of accepted) {
      try {
        const result = await uploadFile(file)
        attachments.value.push({
          fileId: result.fileId,
          name: result.originalName || fallbackAttachmentName(file),
          url: result.url,
          isImage: file.type.startsWith('image/'),
        })
      } catch (error) {
        // 拦截器 reject 的是后端信封对象而非 Error 实例，
        // 直接读 error.message 会拿到 undefined 并退化成误导性的兜底文案。
        uploadError.value = resolveErrorMessage(error)
      }
    }
  } finally {
    uploadingFile.value = false
  }
}

const removeAttachment = (fileId: number) => {
  attachments.value = attachments.value.filter((item) => item.fileId !== fileId)
}

const findMessage = (id: string) => messages.value.find((m) => m.id === id)

const openConversation = async (id: number) => {
  if (sending.value) return

  try {
    const history = await getConversationMessages(id)
    messages.value = history.map((message) => ({
      id: `m-${message.id}`,
      role: message.role === 'assistant' ? 'assistant' : 'user',
      content: message.content ?? '',
      // 后端已按落库的 fileId 重新签发 URL；丢掉它会让历史图片永远不显示
      images: message.images ?? [],
    }))
    currentConversationId.value = id
    // T007：历史会话没有 visualization block 数据，切换会话时清掉旧会话的残留
    visualizationBlocks.value = {}
    progressText.value = ''
    // 打开历史会话总是跳到最新消息
    followOutput.value = true
    await scrollToEnd(true)
    await nextTick()
    const sourceId = route.query.sourceMessageId
    if (typeof sourceId === 'string' && /^\d+$/.test(sourceId)) {
      document.getElementById(`chat-message-m-${sourceId}`)?.scrollIntoView?.({ block: 'center' })
    }
  } catch (error) {
    console.error('加载会话消息失败', error)
  }
}

const startNewConversation = () => {
  if (sending.value) return
  messages.value = []
  // T007：新会话从零开始，旧会话的 visualization block 一并清空
  visualizationBlocks.value = {}
  currentConversationId.value = null
  progressText.value = ''
}

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

/**
 * 是否跟随流式输出自动贴底。
 *
 * 用户往上翻看历史时必须保持不动，否则每个 token 都会把他拽回底部
 * （表现为"划都划不上去"）。只有原本就在底部时才继续跟随。
 */
const followOutput = ref(true)

/** 消息滚动容器的宿主组件；根元素即 .chat-scroll-region */
const threadRef = ref<{ $el: HTMLElement } | null>(null)

const scrollToEnd = async (force = false) => {
  await nextTick()
  if (!force && !followOutput.value) return
  // 用组件根元素而不是全局 document 查询：后者拿不到未挂载的实例，
  // 多实例时还可能滚错容器。
  const list = threadRef.value?.$el
  if (list) list.scrollTop = list.scrollHeight
}

/** 打开历史会话时强制贴底；用户手动滚动时更新跟随状态 */
const handleScrollState = (atBottom: boolean) => {
  followOutput.value = atBottom
}

const failMessage = (id: string, error: unknown) => {
  const msg = findMessage(id)
  if (msg) {
    msg.streaming = false
    msg.error = error instanceof Error ? error.message : String(error)
  }
  progressText.value = ''
  sending.value = false
}

/** 只发附件不打字时的占位提问：Python 侧 message 有 min_length=1 约束，空串会被拒 */
const ATTACHMENT_ONLY_PROMPT = '请看我上传的附件'

const send = async () => {
  const text = prompt.value.trim()
  // 只有图片能作为多模态内容送给 AI；其他附件随消息上传但不进 images
  const imageAttachments = attachments.value.filter((item) => item.isImage)
  const images = imageAttachments.map((item) => item.url)
  // 同时上报 fileId，后端据此把图片持久化到消息表（URL 会过期，不能存）
  const imageFileIds = imageAttachments.map((item) => item.fileId)
  const hasAttachments = attachments.value.length > 0
  // 允许"只发图片/附件"：粘贴截图后直接回车是最自然的用法
  if ((!text && !hasAttachments) || sending.value) return

  const outgoing = text || ATTACHMENT_ONLY_PROMPT
  prompt.value = ''
  const history = buildHistory()
  messages.value.push({ id: `u-${Date.now()}`, role: 'user', content: outgoing, images })
  const assistantId = `a-${Date.now()}`
  messages.value.push({ id: assistantId, role: 'assistant', content: '', streaming: true })
  sending.value = true
  progressText.value = ''
  // 自己发消息时重新跟随输出
  followOutput.value = true
  await scrollToEnd(true)

  try {
    const request: Parameters<typeof sendMessageStream>[0] = {
      message: outgoing,
      conversation_id: currentConversationId.value,
      messages: history,
    }
    if (selectedMode.value !== 'auto') request.mode = selectedMode.value
    if (selectedStyle.value !== 'standard') request.style = selectedStyle.value
    if (images.length) request.images = images
    if (imageFileIds.length) request.image_file_ids = imageFileIds

    const stream = await sendMessageStream(request)
    await parseSSEStream(
      stream,
      (delta) => {
        const msg = findMessage(assistantId)
        if (msg) msg.content += delta
        // 用户往上翻时不得抢滚动
        void scrollToEnd()
      },
      (conversationId) => {
        if (conversationId !== null) {
          currentConversationId.value = conversationId
          // D-016：URL 会因这次 replace 变化（新会话首条消息）时才设抑制标志——
          // 若 URL 已是同一会话 id，replace 不触发 watch，标志会残留并误吞
          // 用户下一次主动切换会话的重载。
          if (routeConversationId(route.query.conversationId) !== conversationId) {
            suppressAutoReload.value = true
          }
          // 同步到 URL：侧栏据 route.query.conversationId 高亮"当前会话"；
          // 用 replace 避免产生一条多余的历史记录。
          void router.replace({
            path: '/question-nav-chat',
            query: { conversationId: String(conversationId), ...(typeof route.query.planId === 'string' ? {planId:route.query.planId} : {}), ...(typeof route.query.learningContext === 'string' ? {learningContext:route.query.learningContext} : {}) },
          })
        }
        const msg = findMessage(assistantId)
        if (msg) {
          msg.streaming = false
          if (!msg.content && !msg.error) {
            msg.error = '后端没有返回任何内容'
          }
        }
        progressText.value = ''
        sending.value = false
        attachments.value = []
        refreshConversations?.()
      },
      (error) => {
        failMessage(assistantId, error)
      },
      (progress) => {
        // 阶段 D：进度只更新**文案**，正文仍只由 onData 追加（不重复渲染）
        progressText.value = progress.message
      },
      (block) => {
        // T007：visualization 事件经 dispatchUiBlock 校验后按当前助手消息 id 归位，
        // ChatThread 据 msg.id 渲染（合法走动态组件，非法显示灰字降级提示）
        const list = visualizationBlocks.value[assistantId]
        if (list) {
          list.push(block)
        } else {
          visualizationBlocks.value[assistantId] = [block]
        }
      },
    )
  } catch (error) {
    failMessage(assistantId, error)
  }
  await scrollToEnd()
}

const routeConversationId = (value: unknown) => {
  const raw = Array.isArray(value) ? value[0] : value
  const id = Number(raw)
  return Number.isInteger(id) && id > 0 ? id : null
}

/**
 * D-016：抑制「本轮对话自身的 URL 同步」引发的消息重载。
 *
 * onDone 首次拿到会话 id 后会 router.replace 把 conversationId 写进 URL
 * （新会话首条消息时 URL 从无 id → 有 id），路由 watch 随之触发
 * openConversation → 用数据库消息整体替换内存消息并清空 visualizationBlocks
 * ——刚渲染出来的交互图组件就这样被"闪没"了（用户随机测试永远看不到图）。
 * 该标志在 onDone 设置一次、路由 watch 消费一次：只同步 id，不重载不清空；
 * 用户之后主动切换会话不受影响（标志已被消费）。
 */
const suppressAutoReload = ref(false)

watch([() => route.query.learningContext, sending], ([value, isSending]) => {
  if (isSending || typeof value !== 'string') return
  const draft = consumeLearningDraft(value)
  // A used token is a no-op; do not erase unsent text on later sending transitions.
  if (!draft) return
  prompt.value = prompt.value.trim() ? `${prompt.value}\n\n【新增的续学上下文，请确认后发送】\n${draft}` : draft
})

watch(() => route.query.draft, (value) => {
  if (!sending.value && typeof value === 'string') prompt.value = value.slice(0, 16000)
})

watch(
  () => route.query.conversationId,
  (value) => {
    const id = routeConversationId(value)
    if (suppressAutoReload.value) {
      suppressAutoReload.value = false
      if (id !== null) currentConversationId.value = id
      return
    }
    if (id === null) {
      startNewConversation()
    } else {
      void openConversation(id)
    }
  },
  { immediate: true },
)
</script>

<template>
  <section class="chat-page">
    <div class="chat-content" :class="{ 'in-conversation': conversationStarted }">
      <div class="plan-chat-panel"><button class="plan-panel-toggle" @click="planPanelOpen=!planPanelOpen">{{planPanelOpen ? '收起动态计划' : '打开动态计划：创建 / 续学 / 调整'}}</button><AdaptivePlanWorkspace v-if="planPanelOpen" :plan-id="typeof route.query.planId === 'string' ? route.query.planId : undefined" compact /></div>
      <ChatThread
        ref="threadRef"
        class="chat-thread"
        :conversation-started="conversationStarted"
        :resource-mode="resourceMode"
        :messages="messages"
        :progress-text="progressText"
        :visualization-blocks="visualizationBlocks"
        @scroll-state="handleScrollState"
        @image-loaded="scrollToEnd()"
      />
      <div class="composer-dock">
        <ChatComposer
          v-model:prompt="prompt"
          :resource-mode="resourceMode"
          :selected-mode-label="selectedModeLabel"
          :selected-style-label="selectedStyleLabel"
          :mode-options="modeOptions"
          :style-options="styleOptions"
          :attachments="attachments"
          :upload-error="uploadError"
          :uploading-file="uploadingFile"
          :sending="sending"
          @send="send"
          @choose-mode="chooseMode"
          @choose-style="chooseStyle"
          @remove-attachment="removeAttachment"
          @upload-files="handleFileUploads"
        />
      </div>
      <div v-if="!conversationStarted" class="quick-asks" aria-label="学习入口">
        <span class="asks-divider" aria-hidden="true"><i />试试问我<i /></span>
        <div class="ask-links">
          <template v-for="(item, index) in suggestions" :key="item.label">
            <span v-if="index > 0" class="ask-dot">·</span>
            <button type="button" class="quick-ask" @click="router.push(item.path)">{{ item.label }}</button>
          </template>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.plan-chat-panel{flex-shrink:0;margin:8px 0}.plan-panel-toggle{background:transparent;border:1px solid #d6e1db;border-radius:8px;cursor:pointer;padding:8px;color:#285e4c;font-size:13px}
.chat-page { height: 100%; min-height: 0; display: flex; justify-content: center; overflow: hidden; padding: 0 24px; }
.chat-content { width: 100%; max-width: 960px; height: 100%; min-height: 0; display: flex; flex-direction: column; }
/* 空态整组居中（标题→输入框→快捷提问），Composer 落在屏幕中央。
   空态垂直节奏全部参数化，微调只改这里 */
.chat-content:not(.in-conversation) {
  --empty-title-size: clamp(32px, 2.7vw, 50px);      /* 主标题 */
  --empty-subtitle-size: clamp(14px, 1.05vw, 17px);  /* 副标题 */
  --empty-title-gap: 26px;                           /* 标题 → 副标题 */
  --empty-heading-to-composer: 56px;                 /* 副标题 → 输入框 */
  --empty-composer-to-divider: 64px;                 /* 输入框 → “试试问我” */
  --empty-divider-to-asks: 26px;                     /* “试试问我” → 快捷提问行 */
  justify-content: safe center;
  overflow-y: auto;
}
.chat-content:not(.in-conversation) .chat-thread { flex: 0 0 auto; }
.chat-content.in-conversation { padding-top: 18px; }
.composer-dock { position: relative; z-index: 1; flex: 0 0 auto; padding: 10px 0 16px; background: linear-gradient(to bottom, rgba(252,251,247,0), rgba(252,251,247,.96) 24%, var(--page) 58%); }
/* 输入框下方：“—— 试试问我 ——” 分隔标注 + 单行淡色快捷提问（· 分隔） */
.quick-asks { flex: 0 0 auto; display: flex; flex-direction: column; align-items: center; gap: var(--empty-divider-to-asks, 26px); width: 100%; margin-top: var(--empty-composer-to-divider, 64px); }
.asks-divider { display: inline-flex; align-items: center; gap: 14px; color: var(--soft-muted); font-size: 13px; letter-spacing: .06em; }
.asks-divider i { display: inline-block; width: 36px; height: 1px; background: var(--line); }
.ask-links { display: flex; align-items: center; justify-content: center; flex-wrap: wrap; gap: 8px 14px; }
.quick-ask { border: 0; background: transparent; padding: 4px 2px; color: var(--soft-muted); cursor: pointer; font-size: 14px; }
.quick-ask:hover { color: var(--ink); }
.ask-dot { color: var(--soft-muted); font-size: 16px; line-height: 1; }
@media (max-width: 900px) { .chat-page { padding: 0 16px; } }
@media (max-width: 620px) { .chat-page { padding: 0 12px; } }
</style>
