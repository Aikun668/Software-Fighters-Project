<script setup lang="ts">
import { computed } from 'vue'

import type { SseEvent } from '@/types/resource'

const props = defineProps<{
  events: SseEvent[]
}>()

const stageLabels: Record<string, string> = {
  plan: '规划资源',
  generate: '生成内容',
  validate: '结构检查',
  review: '质量评审',
  repair: '受限修复',
  fallback: '兼容降级',
  finalize: '整理结果',
}

const stages = computed(() => {
  const byStage = new Map<string, { stage: string; label: string; status: 'running' | 'done' | 'error'; message: string }>()
  for (const event of props.events) {
    if (!event.stage || event.type === 'done') continue
    const current = byStage.get(event.stage) ?? {
      stage: event.stage,
      label: stageLabels[event.stage] ?? event.stage,
      status: 'running' as const,
      message: event.message ?? '',
    }
    current.message = event.message ?? current.message
    if (event.type === 'stage_end') current.status = 'done'
    if (event.type === 'error') current.status = 'error'
    byStage.set(event.stage, current)
  }
  return [...byStage.values()]
})
</script>

<template>
  <section v-if="stages.length" class="timeline" aria-label="生成过程">
    <div class="section-heading">
      <span class="section-kicker">WORKFLOW</span>
      <h2>生成过程</h2>
    </div>
    <ol class="timeline-list">
      <li v-for="item in stages" :key="item.stage" class="timeline-item" :class="item.status">
        <span class="timeline-marker" aria-hidden="true" />
        <div>
          <div class="timeline-label">{{ item.label }}</div>
          <div v-if="item.message" class="timeline-message">{{ item.message }}</div>
        </div>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.timeline {
  border-bottom: 1px solid #e7ebf1;
  padding-bottom: 20px;
}
.section-heading {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.section-heading h2 {
  margin: 0;
  color: #263446;
  font-size: 18px;
}
.section-kicker {
  color: #6b7b90;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.12em;
}
.timeline-list {
  display: grid;
  gap: 12px;
  margin: 18px 0 0;
  padding: 0;
  list-style: none;
}
.timeline-item {
  display: grid;
  grid-template-columns: 10px 1fr;
  gap: 10px;
  align-items: start;
}
.timeline-marker {
  width: 9px;
  height: 9px;
  margin-top: 5px;
  border: 2px solid #aeb9c8;
  border-radius: 999px;
  background: #fff;
}
.timeline-item.running .timeline-marker {
  border-color: #2864c7;
  background: #2864c7;
}
.timeline-item.done .timeline-marker {
  border-color: #4b9b75;
  background: #4b9b75;
}
.timeline-item.error .timeline-marker {
  border-color: #b34c45;
  background: #b34c45;
}
.timeline-label {
  color: #344258;
  font-size: 13px;
  font-weight: 700;
}
.timeline-message {
  margin-top: 2px;
  color: #8290a1;
  font-size: 12px;
}
</style>
