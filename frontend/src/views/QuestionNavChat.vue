<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowUp, BookOpen, ChevronDown, Paperclip, Sparkles } from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'

const router = useRouter()
const route = useRoute()
const prompt = ref('')
const sent = ref(false)
const resourceMode = computed(() => route.query.mode === 'resource')
const suggestions = [
  { label: '梳理 Transformer 学习路径', icon: Sparkles, path: '/learning-path' },
  { label: '生成一组专项练习', icon: BookOpen, path: '/exercise' },
  { label: '解释反向传播', icon: BookOpen, path: '/learning-resource-network' },
]
const send = () => { if (prompt.value.trim()) sent.value = true }
</script>

<template>
  <section class="chat-page">
    <div class="chat-content">
      <div class="chat-heading">
        <span class="heading-mark"><BookOpen :size="26" :stroke-width="1.25" /></span>
        <div>
          <h1>{{ resourceMode ? '想生成什么学习资料？' : '下午好——今天想研究什么？' }}</h1>
          <p>{{ resourceMode ? '告诉我主题、难度和格式，我会整理成适合你的学习资源。' : '我是你的 AI 学习伙伴，随时为你答疑解惑、规划路径、陪伴进步。' }}</p>
        </div>
      </div>

      <div class="suggestions" aria-label="学习入口">
        <button v-for="item in suggestions" :key="item.label" class="suggestion-row" @click="router.push(item.path)">
          <component :is="item.icon" :size="22" :stroke-width="1.35" />
          <span>{{ item.label }}</span>
          <span class="row-arrow">→</span>
        </button>
      </div>

      <div class="composer" :class="{ sent }">
        <textarea v-model="prompt" rows="4" :placeholder="resourceMode ? '输入主题，我生成学习资料...' : '向我提问，或粘贴学习内容...'" @keydown.enter.exact.prevent="send" />
        <div class="composer-toolbar">
          <button class="toolbar-select"><Sparkles :size="16" :stroke-width="1.45" />{{ resourceMode ? '资源生成' : '自动' }} <ChevronDown :size="14" /></button>
          <button><Paperclip :size="17" :stroke-width="1.45" />附件</button>
          <button><BookOpen :size="17" :stroke-width="1.45" />学习方式 <ChevronDown :size="14" /></button>
          <button class="send-button" aria-label="发送" @click="send"><ArrowUp :size="20" :stroke-width="1.6" /></button>
        </div>
      </div>
      <p v-if="sent" class="sent-note">已记录你的问题，静态演示模式下会在这里展开回答。</p>
    </div>
  </section>
</template>

<style scoped>
.chat-page { min-height: 100vh; display: flex; justify-content: center; padding: 0 40px; }.chat-content { width: min(920px, 100%); padding-top: 22vh; }.chat-heading { display: flex; align-items: flex-start; gap: 18px; }.heading-mark { display: grid; place-items: center; margin-top: 9px; color: var(--ink); }.chat-heading h1 { margin: 0; font-family: var(--font-display); font-size: clamp(34px, 4vw, 52px); font-weight: 500; letter-spacing: -.04em; line-height: 1.18; }.chat-heading p { margin: 14px 0 0; color: var(--muted); font-size: 15px; }.suggestions { margin: 50px 0 68px; border-top: 1px solid var(--line); }.suggestion-row { display: flex; align-items: center; gap: 17px; width: 100%; min-height: 64px; padding: 0 9px; border: 0; border-bottom: 1px solid var(--line); background: transparent; color: var(--ink); cursor: pointer; text-align: left; font-size: 15px; }.suggestion-row:hover { background: rgba(255,255,255,.42); }.suggestion-row svg { color: var(--muted); }.row-arrow { margin-left: auto; color: var(--muted); font-size: 23px; font-weight: 300; }.composer { overflow: hidden; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,254,250,.72); box-shadow: 0 10px 28px rgba(122,105,82,.05); }.composer textarea { display: block; width: 100%; min-height: 155px; padding: 21px 23px; resize: vertical; border: 0; outline: 0; background: transparent; color: var(--ink); font-size: 15px; }.composer textarea::placeholder { color: var(--soft-muted); }.composer-toolbar { display: flex; align-items: center; gap: 26px; min-height: 64px; padding: 0 18px 0 21px; border-top: 1px solid var(--line); }.composer-toolbar button { display: inline-flex; align-items: center; gap: 7px; border: 0; background: transparent; color: var(--muted); cursor: pointer; font-size: 13px; }.composer-toolbar button:hover { color: var(--ink); }.toolbar-select { padding-right: 17px !important; border-right: 1px solid var(--line) !important; }.send-button { justify-content: center; width: 40px; height: 40px; margin-left: auto; border-radius: 50% !important; background: var(--clay) !important; color: #fffaf6 !important; }.send-button:hover { background: #b97c65 !important; }.sent-note { margin: 12px 3px; color: var(--sage); font-size: 12px; }
@media (max-width: 900px) { .chat-page { padding: 0 24px; }.chat-content { padding-top: 13vh; }.chat-heading h1 { font-size: 36px; }.suggestions { margin: 38px 0 46px; } }
</style>
