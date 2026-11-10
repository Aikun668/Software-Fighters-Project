<script setup lang="ts">
import { ref } from 'vue'

import type { ResourceType } from '@/types/resource'

defineProps<{
  disabled?: boolean
}>()

const emit = defineEmits<{
  submit: [{ topic: string; resourceType: ResourceType }]
}>()

const topic = ref('')
const resourceType = ref<ResourceType>('document')
const validationMessage = ref('')

const examples = [
  '面向初学者解释 Transformer 自注意力机制',
  'CNN 的卷积层和池化层如何工作',
  '用一个例子理解反向传播',
]

function submit(): void {
  const trimmed = topic.value.trim()
  if (!trimmed) {
    validationMessage.value = '请输入想学习的主题'
    return
  }
  validationMessage.value = ''
  emit('submit', { topic: trimmed, resourceType: resourceType.value })
}
</script>

<template>
  <form class="input-panel" @submit.prevent="submit">
    <div class="eyebrow">开始一次学习生成</div>
    <label class="field-label" for="resource-topic">你想学什么？</label>
    <textarea
      id="resource-topic"
      v-model="topic"
      class="topic-input"
      maxlength="2000"
      rows="5"
      placeholder="例如：面向初学者解释 Transformer 自注意力机制"
      :disabled="disabled"
    />
    <div class="example-list" aria-label="示例主题">
      <button
        v-for="example in examples"
        :key="example"
        type="button"
        class="example-button"
        :disabled="disabled"
        @click="topic = example"
      >
        {{ example }}
      </button>
    </div>

    <fieldset class="type-fieldset">
      <legend class="field-label">资源形式</legend>
      <div class="type-options">
        <button
          type="button"
          class="type-option"
          :class="{ selected: resourceType === 'document' }"
          data-resource-type="document"
          :disabled="disabled"
          @click="resourceType = 'document'"
        >
          <span>课程资料</span>
          <small>分节讲解，适合阅读</small>
        </button>
        <button
          type="button"
          class="type-option"
          :class="{ selected: resourceType === 'interactive_diagram' }"
          data-resource-type="interactive_diagram"
          :disabled="disabled"
          @click="resourceType = 'interactive_diagram'"
        >
          <span>交互图解</span>
          <small>查看概念关系和流程</small>
        </button>
      </div>
    </fieldset>

    <p v-if="validationMessage" class="validation-message" role="alert">
      {{ validationMessage }}
    </p>
    <button class="submit-button" type="submit" :disabled="disabled">
      {{ disabled ? '正在生成…' : '开始生成' }}
    </button>
  </form>
</template>

<style scoped>
.input-panel {
  display: grid;
  gap: 16px;
}
.eyebrow {
  color: #2864c7;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.field-label {
  color: #263446;
  font-size: 14px;
  font-weight: 700;
}
.topic-input {
  width: 100%;
  resize: vertical;
  border: 1px solid #d5dce7;
  border-radius: 12px;
  padding: 14px;
  color: #1b2430;
  background: #fff;
  line-height: 1.6;
}
.topic-input::placeholder {
  color: #99a5b5;
}
.example-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.example-button,
.type-option {
  border: 1px solid #dbe2ec;
  border-radius: 9px;
  color: #536276;
  background: #fff;
  cursor: pointer;
}
.example-button {
  padding: 6px 9px;
  font-size: 12px;
  text-align: left;
}
.example-button:hover {
  border-color: #9fb9e8;
  color: #2864c7;
}
.type-fieldset {
  display: grid;
  gap: 10px;
  border: 0;
  padding: 0;
}
.type-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.type-option {
  display: grid;
  gap: 5px;
  padding: 12px;
  text-align: left;
}
.type-option span {
  color: #263446;
  font-size: 14px;
  font-weight: 700;
}
.type-option small {
  color: #768396;
  font-size: 12px;
}
.type-option.selected {
  border-color: #4d82d8;
  background: #f1f6ff;
  box-shadow: inset 0 0 0 1px #4d82d8;
}
.validation-message {
  margin: 0;
  color: #b34c45;
  font-size: 13px;
}
.submit-button {
  border: 0;
  border-radius: 10px;
  padding: 12px 16px;
  color: #fff;
  background: #2864c7;
  cursor: pointer;
  font-weight: 700;
}
.submit-button:disabled,
.type-option:disabled,
.example-button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
</style>
