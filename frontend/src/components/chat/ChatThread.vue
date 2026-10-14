<script setup lang="ts">
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { ChatMessage } from './chat-types'
import MessageActions from './MessageActions.vue'

defineProps<{
  conversationStarted: boolean
  resourceMode: boolean
  messages: ChatMessage[]
  progressText: string
}>()

const emit = defineEmits<{
  /** 滚动位置是否已贴底；父级据此决定流式输出时要不要继续跟随 */
  scrollState: [atBottom: boolean]
  /** 消息内图片加载完成（会改变滚动高度，需要重新贴底） */
  imageLoaded: []
}>()

/**
 * 助手正文按 Markdown 渲染。
 *
 * - `breaks: true` 让单个换行也生效（聊天场景下更贴近用户预期）；
 * - `gfm: true` 开启表格 / 删除线等 GitHub 风格语法；
 * - **必须经 DOMPurify 清洗**：`marked` 默认放行原始 HTML，而正文来自大模型，
 *   未经清洗直接 `v-html` 会形成 XSS 通道（`<img src=x onerror=...>` 之类）。
 */
const renderMarkdown = (content: string): string =>
  DOMPurify.sanitize(marked.parse(content, { breaks: true, gfm: true }) as string)

/** 距底部多少像素内仍视为“贴底” */
const BOTTOM_THRESHOLD = 80

const onScroll = (event: Event) => {
  const el = event.target as HTMLElement
  emit('scrollState', el.scrollHeight - el.scrollTop - el.clientHeight <= BOTTOM_THRESHOLD)
}

/**
 * 是否给这条消息显示操作条（朗读 / 复制）。
 * 出错的消息与正在流式输出的消息都不显示：前者没有稳定正文可念也不该被复制，
 * 后者会让按钮在输出过程中反复出现又消失（由 MessageActions 内部再兜一层）。
 *
 * 注意这里**不再**判断浏览器是否支持 TTS：复制不依赖 Web Speech API，
 * 不支持朗读的环境也应该能复制（由 MessageActions 内部单独隐藏朗读按钮）。
 */
const canShowActions = (msg: ChatMessage) =>
  msg.role === 'assistant' && !msg.streaming && !msg.error && msg.content.trim().length > 0
</script>

<template>
  <div class="chat-scroll-region" @scroll.passive="onScroll">
    <div v-if="!conversationStarted" class="chat-empty-state">
      <div class="chat-heading">
        <h1>{{ resourceMode ? '想生成什么学习资料？' : '下午好——今天想研究什么？' }}</h1>
        <p>{{ resourceMode ? '告诉我主题、难度和格式，我会整理成适合你的学习资源。' : '我是你的 AI 学习伙伴，随时为你答疑解惑、规划路径、陪伴进步。' }}</p>
      </div>
    </div>

    <div v-if="conversationStarted" class="message-list">
      <div v-for="msg in messages" :key="msg.id" :class="['msg-row', `msg-${msg.role}`]">
        <div class="msg-bubble">
          <template v-if="msg.role === 'assistant'">
            <!-- 正文走 Markdown；流式光标放在 v-html 之外，否则会被渲染结果覆盖掉 -->
            <div v-if="msg.content" class="msg-markdown" v-html="renderMarkdown(msg.content)" />
            <p v-else-if="msg.streaming && !msg.error" class="msg-pending">{{ progressText || '正在思考…' }}</p>
            <span v-if="msg.streaming && msg.content" class="stream-cursor">▍</span>
            <p v-if="msg.streaming && msg.content && progressText" class="msg-pending">{{ progressText }}</p>
            <p v-if="msg.error" class="msg-error">{{ msg.error }}</p>
            <MessageActions
              v-if="canShowActions(msg)"
              :message-id="msg.id"
              :text="msg.content"
              :streaming="msg.streaming"
            />
          </template>
          <template v-else>
            <div v-if="msg.images?.length" class="msg-images">
              <img
                v-for="(url, i) in msg.images"
                :key="i"
                :src="url"
                alt="上传的图片"
                loading="lazy"
                @load="emit('imageLoaded')"
                @error="emit('imageLoaded')"
              />
            </div>
            <p class="msg-text">{{ msg.content }}</p>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-scroll-region { flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain; scrollbar-width: thin; scrollbar-color: #cfc7ba transparent; }
/* 空态标题：居中、无图标；尺寸与间距由父级 --empty-* 参数控制（同参考稿） */
.chat-empty-state { width: 100%; display: flex; justify-content: center; padding-bottom: var(--empty-heading-to-composer, 56px); }
.chat-heading { display: flex; flex-direction: column; align-items: center; gap: var(--empty-title-gap, 26px); text-align: center; }
.chat-heading h1 { margin: 0; font-family: var(--font-display); font-size: var(--empty-title-size, clamp(32px, 2.7vw, 50px)); font-weight: 500; letter-spacing: -.01em; line-height: 1.25; }
.chat-heading p { margin: 0; color: var(--muted); font-size: var(--empty-subtitle-size, clamp(14px, 1.05vw, 17px)); }
.message-list { display: flex; flex-direction: column; gap: 18px; padding: 8px 2px 24px; }
.msg-row { display: flex; }.msg-user { justify-content: flex-end; }
.msg-assistant { justify-content: flex-start; }
.msg-bubble { max-width: 78%; padding: 13px 17px; border-radius: 14px; font-size: 15px; line-height: 1.65; }
.msg-user .msg-bubble { background: var(--clay); color: #fffaf6; border-bottom-right-radius: 4px; }
.msg-assistant .msg-bubble { background: rgba(255,254,250,.85); border: 1px solid var(--line); color: var(--ink); border-bottom-left-radius: 4px; }
.msg-text { margin: 0; white-space: pre-wrap; word-break: break-word; }

/* ── Markdown 正文（助手消息） ──────────────────────────────
   作用：把 marked 产出的 HTML 标签排版成可读的富文本。
   用 :deep() 穿透 scoped 样式，否则 v-html 注入的标签拿不到这些规则。 */
.msg-markdown { word-break: break-word; }
.msg-markdown :deep(> *:first-child) { margin-top: 0; }
.msg-markdown :deep(> *:last-child) { margin-bottom: 0; }
.msg-markdown :deep(p) { margin: 0 0 10px; }
.msg-markdown :deep(h1),
.msg-markdown :deep(h2),
.msg-markdown :deep(h3),
.msg-markdown :deep(h4) { margin: 14px 0 8px; font-family: var(--font-display); font-weight: 600; line-height: 1.35; }
.msg-markdown :deep(h1) { font-size: 1.45em; }
.msg-markdown :deep(h2) { font-size: 1.28em; }
.msg-markdown :deep(h3) { font-size: 1.13em; }
.msg-markdown :deep(h4) { font-size: 1.02em; }
.msg-markdown :deep(ul),
.msg-markdown :deep(ol) { margin: 0 0 10px; padding-left: 1.4em; }
.msg-markdown :deep(li) { margin: 3px 0; }
.msg-markdown :deep(li > p) { margin: 0; }
.msg-markdown :deep(a) { color: var(--sage); text-decoration: underline; text-underline-offset: 2px; }
.msg-markdown :deep(strong) { font-weight: 600; }
.msg-markdown :deep(hr) { margin: 14px 0; border: 0; border-top: 1px solid var(--line); }
.msg-markdown :deep(blockquote) {
  margin: 10px 0; padding: 2px 0 2px 12px;
  border-left: 3px solid var(--sage); color: var(--muted);
}
/* 行内代码：代码块内的 code 由下面的 pre code 规则覆盖，不重复加底色 */
.msg-markdown :deep(code) {
  padding: 1px 5px; border-radius: 4px;
  background: rgba(120,105,85,.12);
  font-family: 'Fira Code', 'Monaco', ui-monospace, monospace;
  font-size: .88em;
}
.msg-markdown :deep(pre) {
  margin: 10px 0; padding: 12px 14px; overflow-x: auto;
  border: 1px solid var(--line); border-radius: 9px;
  background: rgba(120,105,85,.08);
}
.msg-markdown :deep(pre code) { padding: 0; background: none; font-size: .86em; line-height: 1.6; }
.msg-markdown :deep(table) { width: 100%; margin: 10px 0; border-collapse: collapse; font-size: .92em; }
.msg-markdown :deep(th),
.msg-markdown :deep(td) { padding: 6px 10px; border: 1px solid var(--line); text-align: left; }
.msg-markdown :deep(th) { background: rgba(120,105,85,.08); font-weight: 600; }
.msg-markdown :deep(img) { max-width: 100%; height: auto; border-radius: 8px; }

.msg-images { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.msg-images img { width: 120px; max-width: 100%; height: 120px; border-radius: 8px; object-fit: cover; background: rgba(255,255,255,.25); }
.msg-error { margin: 0; color: #b4483c; font-size: 14px; }
.msg-pending { margin: 0; color: var(--muted); }
/* 流式光标：v-html 之后它独立于正文，需自带换行避免黏在段落末尾 */
.stream-cursor { display: inline-block; margin-left: 1px; color: var(--clay); animation: blink 1s steps(2) infinite; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
@media (max-width: 620px) { .msg-bubble { max-width: 90%; } }
</style>
