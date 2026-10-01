<script setup lang="ts">
/**
 * AI 消息气泡下方的操作条（对齐 ChatGPT）。
 *
 * 目前只有「朗读」一项；操作条本身做成容器，后续加「复制」「重新生成」
 * 只需在此追加按钮，不必再改动 ChatThread。
 */
import { computed, onBeforeUnmount } from 'vue'
import { Volume2, VolumeX } from '@lucide/vue'
import { useSpeech } from '@/composables/useSpeech'

const props = defineProps<{
  /** 消息 id，用于判断本条是否正在朗读 */
  messageId: string
  /** 待朗读的原始 Markdown 正文（由 composable 内部清洗） */
  text: string
  /** 是否正在流式输出；输出中不显示朗读按钮 */
  streaming?: boolean
}>()

const { supported, isPlaying, isPaused, stop, toggle } = useSpeech()

/** 本条是否处于朗读中或暂停中 */
const isActive = computed(() => isPlaying(props.messageId) || isPaused(props.messageId))

/** 流式中、无正文、或浏览器不支持 TTS 时，整条操作条不渲染 */
const visible = computed(() => supported && !props.streaming && props.text.trim().length > 0)

const label = computed(() => {
  if (isPaused(props.messageId)) return '继续朗读'
  if (isPlaying(props.messageId)) return '暂停朗读'
  return '朗读'
})

const onClick = () => {
  toggle(props.messageId, props.text)
}

/**
 * 组件销毁时若本条正在朗读则停掉。
 * 播放状态活在模块级单例里，不随组件销毁而消失；离开聊天页后不清理的话，
 * 声音会继续念一条已经不存在的消息。
 */
onBeforeUnmount(() => {
  if (isActive.value) stop()
})
</script>

<template>
  <div v-if="visible" class="message-actions">
    <button
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
.action-label { white-space: nowrap; }
</style>
