<script setup lang="ts">
import { computed } from 'vue'

import type { ReviewStatus } from '@/types/resource'

const props = defineProps<{
  reviewStatus: ReviewStatus
  repairAttempted: boolean
  fallbackUsed: boolean
  finalStatus: string
}>()

const summary = computed(() => {
  if (props.finalStatus !== 'success') {
    return {
      tone: 'error',
      title: '生成未完成',
      detail: '这次没有形成可交付结果，可以保留主题后重新生成。',
    }
  }
  if (props.reviewStatus === 'skipped') {
    return {
      tone: 'muted',
      title: '质量评审暂不可用',
      detail: '已交付通过结构检查的结果。',
    }
  }
  if (props.reviewStatus === 'repair' && !props.repairAttempted) {
    return {
      tone: 'observe',
      title: '发现可改进项，当前保留原结果',
      detail: '当前处于观察模式，评审建议会被记录但不会改写本次结果。',
    }
  }
  if (props.repairAttempted) {
    return {
      tone: 'success',
      title: '已执行一次受限修复',
      detail: '修复后重新完成了结构检查。',
    }
  }
  return {
    tone: 'success',
    title: '已完成质量检查',
    detail: '结果通过了当前工作流的基础质量检查。',
  }
})

const notes = computed(() => props.fallbackUsed
  ? '已使用兼容的课程资料结果。'
  : '')
</script>

<template>
  <section class="quality-summary" :class="`tone-${summary.tone}`" aria-label="质量摘要">
    <span class="quality-mark" aria-hidden="true">{{ summary.tone === 'error' ? '!' : '✓' }}</span>
    <div>
      <div class="quality-kicker">QUALITY CHECK</div>
      <h3>{{ summary.title }}</h3>
      <p>{{ summary.detail }}</p>
      <p v-if="notes" class="quality-note">{{ notes }}</p>
    </div>
  </section>
</template>

<style scoped>
.quality-summary {
  display: flex;
  gap: 12px;
  margin-top: 28px;
  border-top: 1px solid #e5eaf1;
  padding-top: 18px;
}
.quality-mark {
  display: grid;
  flex: 0 0 26px;
  width: 26px;
  height: 26px;
  place-items: center;
  border-radius: 50%;
  color: #fff;
  background: #4b9b75;
  font-size: 13px;
  font-weight: 800;
}
.quality-kicker {
  color: #7f8da2;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.12em;
}
.quality-summary h3 {
  margin: 5px 0 4px;
  color: #344258;
  font-size: 14px;
}
.quality-summary p {
  margin: 0;
  color: #7a8798;
  font-size: 12px;
  line-height: 1.6;
}
.quality-note {
  margin-top: 4px !important;
}
.tone-observe .quality-mark {
  color: #8b6a2d;
  background: #f2d899;
}
.tone-muted .quality-mark {
  background: #8491a2;
}
.tone-error .quality-mark {
  background: #b34c45;
}
</style>
