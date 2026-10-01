<script setup lang="ts">
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

/** 距底部多少像素内仍视为“贴底” */
const BOTTOM_THRESHOLD = 80

const onScroll = (event: Event) => {
  const el = event.target as HTMLElement
  emit('scrollState', el.scrollHeight - el.scrollTop - el.clientHeight <= BOTTOM_THRESHOLD)
}

/**
 * 是否给这条消息显示朗读操作条。
 * 出错的消息与正在流式输出的消息都不显示：前者没有稳定正文可念，
 * 后者会让按钮在输出过程中反复出现又消失（由 MessageActions 内部再兜一层）。
 */
const canSpeak = (msg: ChatMessage) =>
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
            <p v-if="msg.content" class="msg-text">{{ msg.content }}<span v-if="msg.streaming" class="stream-cursor">▍</span></p>
            <p v-else-if="msg.streaming && !msg.error" class="msg-pending">{{ progressText || '正在思考…' }}</p>
            <p v-if="msg.streaming && msg.content && progressText" class="msg-pending">{{ progressText }}</p>
            <p v-if="msg.error" class="msg-error">{{ msg.error }}</p>
            <MessageActions
              v-if="canSpeak(msg)"
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
.msg-images { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.msg-images img { width: 120px; max-width: 100%; height: 120px; border-radius: 8px; object-fit: cover; background: rgba(255,255,255,.25); }
.msg-error { margin: 0; color: #b4483c; font-size: 14px; }
.msg-pending { margin: 0; color: var(--muted); }
.stream-cursor { display: inline-block; margin-left: 1px; color: var(--clay); animation: blink 1s steps(2) infinite; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
@media (max-width: 620px) { .msg-bubble { max-width: 90%; } }
</style>
