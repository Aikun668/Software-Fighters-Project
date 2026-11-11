<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { ChatMessage } from './chat-types'
import MessageActions from './MessageActions.vue'
import { renderMermaidBlocks } from '@/utils/mermaid'
import { renderChatMarkdown } from '@/utils/markdown'
import type { DispatchResult } from './ui-blocks/registry'

const props = defineProps<{
  conversationStarted: boolean
  resourceMode: boolean
  messages: ChatMessage[]
  progressText: string
  /** T004：消息 id → visualization block 列表（来自 parseSSEStream 的 onVisualization
   *  回调，由父层装配到对应助手消息）。合法走动态组件渲染，非法显示灰字降级提示。
   *  可选 prop：不传时行为与原先完全一致。 */
  visualizationBlocks?: Record<string, DispatchResult[]>
}>()

const emit = defineEmits<{
  /** 滚动位置是否已贴底；父级据此决定流式输出时要不要继续跟随 */
  scrollState: [atBottom: boolean]
  /** 消息内图片加载完成（会改变滚动高度，需要重新贴底） */
  imageLoaded: []
  /** 把推荐练习填成下一条提问 */
  usePrompt: [prompt: string]
}>()

const greeting = computed(() => {
  if (props.resourceMode) return '想生成什么学习资料？'
  const hour = new Date().getHours()
  if (hour < 5) return '夜深了——还想研究什么？'
  if (hour < 11) return '早上好——今天想研究什么？'
  if (hour < 14) return '中午好——今天想研究什么？'
  if (hour < 18) return '下午好——今天想研究什么？'
  return '晚上好——今天想研究什么？'
})

const threadRef = ref<HTMLElement | { $el?: HTMLElement } | null>(null)

/** ref 绑在普通 div 上拿到的是 DOM 元素本身（无 $el）；绑在组件上才是实例（有 $el）。两种都兼容。 */
const threadEl = (): HTMLElement | null => {
  const value = threadRef.value
  if (!value) return null
  return value instanceof HTMLElement ? value : (value.$el ?? null)
}

/**
 * 助手正文按 Markdown 渲染（含数学公式）。
 *
 * 渲染实现已收敛到 `@/utils/markdown` 的单一入口：那边统一处理
 * Markdown + KaTeX 公式 + DOMPurify 清洗，避免各处重复实现漂移。
 * 本组件不再直接依赖 `marked` / `DOMPurify`。
 */
const renderMarkdown = renderChatMarkdown

/**
 * FINAL 用户需求：AI 返回的 mermaid 图（mindmap/流程图…）此前只是代码块渲染不出来。
 * 在 Markdown 落到 DOM 后扫描 ```mermaid 代码块并替换为 SVG。
 * - 幂等（已渲染的块带标记跳过），流式期间反复触发也安全；
 * - **只在流结束后渲染**：流式中途图表语法还不完整，渲染必报错；
 *   流式中的 token 更新（`m.streaming:1` 前缀变化）直接跳过，避免无效渲染尝试。
 */
watch(
  () => props.messages.map((m) => `${m.id}:${m.streaming ? 1 : 0}:${m.content.length}`).join('|'),
  async (value, oldValue) => {
    // 流式进行中（本轮 watch 仍因同一批 streaming 消息的长度变化触发）不渲染：
    // 语法残缺时 mermaid.render 必失败，白白消耗且可能留下残图。
    const wasStreamingOnly =
      oldValue !== undefined &&
      props.messages.some((m) => m.streaming) &&
      value.split('|').length === oldValue.split('|').length &&
      value.split('|').every((seg, i) => {
        const old = oldValue.split('|')[i]
        if (!old) return false
        const [id, flag] = seg.split(':')
        const [oldId, oldFlag] = old.split(':')
        return id === oldId && flag === oldFlag && flag === '1'
      })
    if (wasStreamingOnly) return
    await nextTick()
    await renderMermaidBlocks(threadEl())
  },
  { immediate: true },
)

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
  <div ref="threadRef" class="chat-scroll-region" @scroll.passive="onScroll">
    <div v-if="!conversationStarted" class="chat-empty-state">
      <div class="chat-heading">
        <h1>{{ greeting }}</h1>
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
            <button
              v-if="msg.recommendation && !msg.streaming"
              type="button"
              class="msg-recommendation"
              @click="emit('usePrompt', msg.recommendation.prompt)"
            >{{ msg.recommendation.label }}</button>
            <!-- T004：结构化 UI block（visualization 事件）渲染在正文下方；
                 合法走动态组件 + props，非法显示灰字降级提示，均不影响正文 -->
            <div
              v-for="(block, bi) in visualizationBlocks?.[msg.id] ?? []"
              :key="`viz-${bi}`"
              class="msg-visualization"
            >
              <component :is="block.ok ? block.component : null" v-if="block.ok" v-bind="block.ok ? block.props : {}" />
              <p v-else class="msg-visualization-fallback">图表数据不合法，已隐藏（{{ block.error }}）</p>
            </div>
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
/* mermaid 渲染结果：白底卡片 + 可横向滚动，宽图不撑破气泡 */
.msg-markdown :deep(.mermaid-figure) {
  margin: 10px 0; padding: 12px;
  border: 1px solid var(--line); border-radius: 9px;
  background: #fff; overflow-x: auto;
}
.msg-markdown :deep(.mermaid-figure svg) { max-width: 100%; height: auto; display: block; margin: 0 auto; }

.msg-images { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.msg-images img { width: 120px; max-width: 100%; height: 120px; border-radius: 8px; object-fit: cover; background: rgba(255,255,255,.25); }
.msg-error { margin: 0; color: #b4483c; font-size: 14px; }
.msg-recommendation { display: inline-flex; margin-top: 8px; padding: 0; border: 0; background: transparent; color: var(--muted); cursor: pointer; font-size: 13px; }
.msg-recommendation:hover { color: var(--ink); }
.msg-pending { margin: 0; color: var(--muted); }
/* 流式光标：v-html 之后它独立于正文，需自带换行避免黏在段落末尾 */
.stream-cursor { display: inline-block; margin-left: 1px; color: var(--clay); animation: blink 1s steps(2) infinite; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
@media (max-width: 620px) { .msg-bubble { max-width: 90%; } }

/* ── T004：结构化 UI block（visualization 事件） ─────────────
   合法 block 的动态组件容器 + 非法 block 的灰字降级提示（与 msg-pending 同色调）。 */
.msg-visualization { margin: 10px 0 2px; }
.msg-visualization :deep(.attention-wrap) { max-width: 100%; }
.msg-visualization-fallback { margin: 0; color: var(--muted); font-size: 13px; }
</style>
