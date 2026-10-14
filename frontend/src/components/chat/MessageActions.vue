<script setup lang="ts">
/**
 * AI 消息气泡下方的操作条（对齐 ChatGPT）。
 *
 * 目前有「朗读」「复制」两项；操作条本身做成容器，后续加「重新生成」
 * 只需在此追加按钮，不必再改动 ChatThread。
 *
 * 两个按钮的显示条件**刻意分开**：朗读依赖浏览器 TTS，复制不依赖。
 * 早期版本用 `supported && …` 控制整条操作条，在 http 局域网访问
 * （`navigator.clipboard` 与 `speechSynthesis` 都不可用）等场景下会把
 * 复制按钮一起藏掉，所以现在只在朗读按钮上单独判断 `supported`。
 */
import { computed, onBeforeUnmount, ref } from 'vue'
import { Check, Copy, Volume2, VolumeX } from '@lucide/vue'
import { useSpeech } from '@/composables/useSpeech'
import { copyTextToClipboard } from '@/utils/clipboard'

const props = defineProps<{
  /** 消息 id，用于判断本条是否正在朗读 */
  messageId: string
  /** 原始 Markdown 正文：朗读前会被清洗，复制则保持原文 */
  text: string
  /** 是否正在流式输出；输出中不显示操作条 */
  streaming?: boolean
}>()

const { supported, isPlaying, isPaused, stop, toggle } = useSpeech()

/** 本条是否处于朗读中或暂停中 */
const isActive = computed(() => isPlaying(props.messageId) || isPaused(props.messageId))

/**
 * 操作条是否渲染。
 * 只要求「有正文且不在流式中」——复制是纯浏览器能力，不受 TTS 支持与否影响。
 */
const visible = computed(() => !props.streaming && props.text.trim().length > 0)

const label = computed(() => {
  if (isPaused(props.messageId)) return '继续朗读'
  if (isPlaying(props.messageId)) return '暂停朗读'
  return '朗读'
})

const onClick = () => {
  toggle(props.messageId, props.text)
}

/* ── 复制 ───────────────────────────────────────────────────── */

/** 'idle' 待复制 | 'copied' 已复制 | 'failed' 复制失败 */
const copyState = ref<'idle' | 'copied' | 'failed'>('idle')

/**
 * 反馈自动回到 idle 的定时器。
 * 必须持有句柄：连点复制时若不取消上一个定时器，先前的那个会提前把新反馈抹掉。
 */
let copyFeedbackTimer: ReturnType<typeof setTimeout> | null = null

const clearCopyFeedback = () => {
  if (copyFeedbackTimer !== null) {
    clearTimeout(copyFeedbackTimer)
    copyFeedbackTimer = null
  }
}

const copyLabel = computed(() => {
  if (copyState.value === 'copied') return '已复制'
  if (copyState.value === 'failed') return '复制失败'
  return '复制'
})

const onCopy = async () => {
  clearCopyFeedback()
  // 复制的是**原始 Markdown 正文**（不是渲染后的 HTML），粘贴到文档里能保留格式
  const ok = await copyTextToClipboard(props.text)
  copyState.value = ok ? 'copied' : 'failed'
  copyFeedbackTimer = setTimeout(() => {
    copyState.value = 'idle'
    copyFeedbackTimer = null
  }, 1600)
}

/**
 * 组件销毁时若本条正在朗读则停掉。
 * 播放状态活在模块级单例里，不随组件销毁而消失；离开聊天页后不清理的话，
 * 声音会继续念一条已经不存在的消息。
 */
onBeforeUnmount(() => {
  clearCopyFeedback()
  if (isActive.value) stop()
})
</script>

<template>
  <div v-if="visible" class="message-actions">
    <button
      v-if="supported"
      type="button"
      class="action-btn"
      :class="{ 'is-active': isActive }"
      :title="label"
      :aria-label="label"
      :aria-pressed="isActive"
      @click="onClick"
    >
      <VolumeX v-if="isPlaying(messageId)" :size="14" :stroke-width="2" />
      <Volume2 v-else :size="14" :stroke-width="2" />
      <span class="action-label">{{ label }}</span>
    </button>

    <button
      type="button"
      class="action-btn copy-btn"
      :class="{ 'is-done': copyState === 'copied', 'is-failed': copyState === 'failed' }"
      :title="copyLabel"
      :aria-label="copyLabel"
      @click="onCopy"
    >
      <Check v-if="copyState === 'copied'" :size="14" :stroke-width="2" />
      <Copy v-else :size="14" :stroke-width="2" />
      <span class="action-label">{{ copyLabel }}</span>
    </button>
  </div>
</template>

<style scoped>
.message-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-top: 7px;
  /* 微负边距让图标左沿与正文对齐，而不是被按钮内边距顶出去 */
  margin-left: -8px;
}
.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 9px 4px 7px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--muted);
  font-family: inherit;
  font-size: 12.5px;
  line-height: 1;
  cursor: pointer;
  transition: color .15s ease, background-color .15s ease, border-color .15s ease;
}
.action-btn:hover { color: var(--ink); background: rgba(0, 0, 0, .05); }
.action-btn:focus-visible { outline: 2px solid var(--clay); outline-offset: 2px; }
/* 朗读中：黏土底色 + 主色图标，与停顿时区分 */
.action-btn.is-active {
  color: var(--clay);
  background: var(--clay-soft);
  border-color: rgba(200, 143, 120, .35);
}
/* 复制成功：鼠尾草绿，和「朗读中」的黏土色区分开，避免误以为在念 */
.copy-btn.is-done { color: var(--sage); background: var(--sage-soft); border-color: rgba(127, 146, 122, .35); }
.copy-btn.is-failed { color: #b4483c; background: rgba(180, 72, 60, .08); border-color: rgba(180, 72, 60, .28); }
.action-label { white-space: nowrap; }
</style>
