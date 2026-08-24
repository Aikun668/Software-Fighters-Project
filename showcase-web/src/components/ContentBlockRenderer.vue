<script setup lang="ts">
import StructuredDiagram from './StructuredDiagram.vue'
import type { ContentBlock } from '@/types/resource'

defineProps<{
  block: ContentBlock
}>()
</script>

<template>
  <article v-if="block.type === 'section'" class="content-block section-block">
    <h3 v-if="block.heading">{{ block.heading }}</h3>
    <p>{{ block.content }}</p>
  </article>
  <article v-else-if="block.type === 'callout'" class="content-block callout-block">
    <div v-if="block.heading" class="callout-heading">{{ block.heading }}</div>
    <p>{{ block.content }}</p>
  </article>
  <article v-else-if="block.type === 'code'" class="content-block code-block">
    <div v-if="block.heading" class="code-heading">{{ block.heading }}</div>
    <pre><code>{{ block.content }}</code></pre>
  </article>
  <article v-else-if="block.type === 'interactive_diagram'" class="content-block diagram-block">
    <StructuredDiagram v-if="block.diagram" :diagram="block.diagram" />
    <p v-else class="unsupported-block">图解数据不完整，暂时无法预览。</p>
  </article>
  <article v-else class="content-block unsupported-block">
    {{ block.heading || '暂不支持此资源块' }}
  </article>
</template>

<style scoped>
.content-block {
  margin-top: 20px;
}
.content-block h3,
.callout-heading,
.code-heading {
  margin: 0 0 8px;
  color: #263446;
  font-size: 17px;
  font-weight: 750;
}
.content-block p {
  margin: 0;
  color: #536276;
  line-height: 1.8;
  white-space: pre-wrap;
}
.callout-block {
  border-left: 3px solid #78a4e7;
  border-radius: 0 10px 10px 0;
  padding: 14px 16px;
  background: #f2f6fd;
}
.callout-heading {
  color: #2864c7;
  font-size: 14px;
}
.code-block {
  overflow: hidden;
  border: 1px solid #dbe2ec;
  border-radius: 10px;
  background: #f8fafc;
}
.code-heading {
  margin: 0;
  border-bottom: 1px solid #dbe2ec;
  padding: 10px 12px;
  font-size: 13px;
}
.code-block pre {
  margin: 0;
  overflow-x: auto;
  padding: 14px;
}
.code-block code {
  color: #36465c;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 13px;
  line-height: 1.6;
}
.unsupported-block {
  color: #8895a6;
  font-size: 13px;
}
</style>
