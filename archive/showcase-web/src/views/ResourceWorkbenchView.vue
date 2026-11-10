<script setup lang="ts">
import { ref } from 'vue'

import ResourceInputPanel from '@/components/ResourceInputPanel.vue'
import ResourceResult from '@/components/ResourceResult.vue'
import QualitySummary from '@/components/QualitySummary.vue'
import WorkflowTimeline from '@/components/WorkflowTimeline.vue'
import { generateResource } from '@/api/resourceSse'
import type { DonePayload, PageState, ResourceType, SseEvent } from '@/types/resource'

const pageState = ref<PageState>('idle')
const selectedType = ref<ResourceType>('document')
const topic = ref('')
const events = ref<SseEvent[]>([])
const done = ref<DonePayload | null>(null)
const errorMessage = ref('')

async function handleSubmit(payload: { topic: string; resourceType: ResourceType }): Promise<void> {
  pageState.value = 'streaming'
  selectedType.value = payload.resourceType
  topic.value = payload.topic
  events.value = []
  done.value = null
  errorMessage.value = ''

  try {
    done.value = await generateResource(
      { topic: payload.topic, resource_type: payload.resourceType },
      (event) => events.value.push(event),
    )
    pageState.value = done.value.final_status === 'success' ? 'success' : 'error'
    if (pageState.value === 'error') {
      errorMessage.value = done.value.error || '资源没有完整生成，请重试。'
    }
  } catch (error) {
    pageState.value = 'error'
    errorMessage.value = error instanceof Error ? error.message : '资源生成失败，请重试。'
  }
}
</script>

<template>
  <main class="workbench-page">
    <header class="workbench-header">
      <div>
        <p class="brand-mark">AI LEARNING WORKBENCH</p>
        <h1>AI 学习资源工作台</h1>
        <p class="subtitle">把一个学习主题，变成可以阅读和探索的学习材料。</p>
      </div>
      <div class="header-note">一次生成 · 两种资源 · 可见过程</div>
    </header>

    <section class="workbench-grid">
      <aside class="control-column">
        <ResourceInputPanel :disabled="pageState === 'streaming'" @submit="handleSubmit" />
      </aside>

      <section class="result-column" aria-live="polite">
        <WorkflowTimeline :events="events" />

        <div v-if="pageState === 'idle'" class="empty-state">
          <span class="empty-number">01</span>
          <h2>从一个问题开始</h2>
          <p>输入你正在学习的主题，工作台会展示资源生成的每个主要阶段。</p>
        </div>
        <div v-else-if="pageState === 'error'" class="error-state" role="alert">
          <span class="empty-number">!</span>
          <h2>这次生成没有完成</h2>
          <p>{{ errorMessage }}</p>
          <p class="error-hint">你的主题已经保留，可以直接重新生成。</p>
        </div>
        <ResourceResult
          v-else-if="done"
          :topic="topic"
          :response="done.response || '资源已经生成，接下来可以阅读结果。'"
          :blocks="done.content_blocks"
        />
        <QualitySummary
          v-if="done"
          :review-status="done.review_status"
          :repair-attempted="done.repair_attempted"
          :fallback-used="done.fallback_used"
          :final-status="done.final_status"
        />
        <div v-else class="streaming-state">
          <span class="loading-dot" aria-hidden="true" />
          <p>正在整理资源，请稍候…</p>
        </div>
      </section>
    </section>
  </main>
</template>

<style scoped>
.workbench-page {
  width: min(1180px, calc(100% - 48px));
  margin: 0 auto;
  padding: 48px 0 64px;
}
.workbench-header {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: end;
  margin-bottom: 32px;
}
.brand-mark,
.result-kicker {
  margin: 0 0 8px;
  color: #2864c7;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.12em;
}
.workbench-header h1 {
  margin: 0;
  color: #182333;
  font-size: clamp(30px, 4vw, 48px);
  letter-spacing: -0.04em;
}
.subtitle {
  margin: 12px 0 0;
  color: #718095;
  font-size: 16px;
}
.header-note {
  padding-bottom: 5px;
  color: #7a8798;
  font-size: 12px;
}
.workbench-grid {
  display: grid;
  grid-template-columns: minmax(280px, 0.78fr) minmax(0, 1.45fr);
  gap: 24px;
  align-items: start;
}
.control-column,
.result-column {
  min-width: 0;
  border: 1px solid #e1e7ef;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 12px 30px rgba(50, 70, 100, 0.06);
}
.control-column {
  padding: 24px;
}
.result-column {
  min-height: 560px;
  padding: 24px;
}
.empty-state,
.error-state,
.streaming-state,
.response-preview {
  padding: 68px 28px;
}
.empty-number {
  display: inline-grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 10px;
  color: #2864c7;
  background: #eaf1ff;
  font-size: 13px;
  font-weight: 800;
}
.empty-state h2,
.error-state h2,
.response-preview h2 {
  margin: 20px 0 10px;
  color: #263446;
  font-size: 25px;
  letter-spacing: -0.02em;
}
.empty-state p,
.error-state p,
.response-preview > p {
  max-width: 560px;
  margin: 0;
  color: #718095;
  line-height: 1.8;
}
.error-state .empty-number {
  color: #b34c45;
  background: #fff0ee;
}
.error-hint {
  margin-top: 8px !important;
  color: #9b6f6a !important;
  font-size: 13px;
}
.streaming-state {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #718095;
}
.loading-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #2864c7;
  box-shadow: 0 0 0 6px #eaf1ff;
}
.response-preview {
  padding-top: 42px;
}
@media (max-width: 760px) {
  .workbench-page {
    width: min(100% - 28px, 620px);
    padding-top: 28px;
  }
  .workbench-header {
    display: block;
  }
  .header-note {
    margin-top: 16px;
  }
  .workbench-grid {
    grid-template-columns: 1fr;
  }
  .result-column {
    min-height: 420px;
  }
}
</style>
