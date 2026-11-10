<script setup lang="ts">
import ContentBlockRenderer from './ContentBlockRenderer.vue'
import type { ContentBlock } from '@/types/resource'

defineProps<{
  topic: string
  response: string
  blocks: ContentBlock[]
}>()
</script>

<template>
  <section class="resource-result" aria-label="生成结果">
    <div class="result-heading">
      <span class="result-kicker">RESOURCE</span>
      <h2>{{ topic }}</h2>
      <p v-if="response" class="result-response">{{ response }}</p>
    </div>
    <div v-if="blocks.length" class="block-list">
      <ContentBlockRenderer v-for="(block, index) in blocks" :key="`${block.type}-${index}`" :block="block" />
    </div>
    <p v-else class="unavailable-message">暂时没有可展示的资源内容。</p>
  </section>
</template>

<style scoped>
.resource-result {
  padding-top: 38px;
}
.result-kicker {
  color: #2864c7;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.12em;
}
.result-heading h2 {
  margin: 8px 0 8px;
  color: #263446;
  font-size: 26px;
  letter-spacing: -0.025em;
}
.result-response,
.unavailable-message {
  margin: 0;
  color: #718095;
  line-height: 1.8;
}
.block-list {
  margin-top: 22px;
}
.unavailable-message {
  margin-top: 24px;
  border: 1px dashed #cbd5e1;
  border-radius: 10px;
  padding: 20px;
}
</style>
