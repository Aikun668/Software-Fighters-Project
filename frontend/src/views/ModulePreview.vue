<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, BarChart3, CalendarCheck2, CheckCircle2, FolderOpen, Network, PencilLine } from '@lucide/vue'

const route = useRoute()
const router = useRouter()
const info = computed(() => ({
  title: String(route.meta.title || '学习空间'),
  eyebrow: String(route.meta.eyebrow || '继续你的学习探索'),
}))
const cards = computed(() => {
  if (route.path.includes('analysis')) return [
    { title: '本周学习概览', value: '8.5h', text: '比上周多学习 1.2 小时', icon: BarChart3 },
    { title: '当前学习画像', value: '83%', text: '已形成 5/6 个稳定维度', icon: CheckCircle2 },
    { title: '最值得关注', value: '矩阵运算', text: '建议开始一组专项练习', icon: PencilLine },
  ]
  if (route.path.includes('path')) return [
    { title: '今日学习计划', value: '3 项', text: '还有 2 项待完成', icon: CalendarCheck2 },
    { title: '当前阶段', value: '深度学习基础', text: '按计划继续前进', icon: Network },
    { title: '预计用时', value: '45 min', text: '完成今日任务所需', icon: CheckCircle2 },
  ]
  if (route.path.includes('exercise')) return [
    { title: '待完成练习', value: '6 组', text: '根据你的薄弱点推荐', icon: PencilLine },
    { title: '最近正确率', value: '76%', text: '比上周提升 6%', icon: BarChart3 },
    { title: '建议练习', value: '矩阵运算', text: '预计 15 分钟', icon: CheckCircle2 },
  ]
  if (route.path.includes('resource')) return [
    { title: '我的资源', value: '12 份', text: '课程、笔记与可视化资料', icon: FolderOpen },
    { title: '最近查看', value: 'Transformer', text: '继续上次的学习内容', icon: Network },
    { title: '推荐资源', value: '3 份', text: '根据你的学习方式匹配', icon: CheckCircle2 },
  ]
  return [
    { title: '知识节点', value: '23 个', text: '你的学习网络正在生长', icon: Network },
    { title: '已掌握', value: '8 个', text: '掌握度达到 80% 以上', icon: CheckCircle2 },
    { title: '待巩固', value: '5 个', text: '建议安排专项练习', icon: PencilLine },
  ]
})
</script>

<template>
  <section class="module-page">
    <div class="module-inner">
      <div class="module-topline"><span>{{ info.eyebrow }}</span><button @click="router.push('/question-nav-chat')">回到对话 <ArrowRight :size="15" /></button></div>
      <h1>{{ info.title }}</h1>
      <p class="module-intro">这里会聚合你的学习记录，帮助你清晰地看到当前状态，并决定下一步如何继续。</p>
      <div class="preview-list">
        <article v-for="card in cards" :key="card.title" class="preview-row">
          <component :is="card.icon" :size="22" :stroke-width="1.35" />
          <div class="row-copy"><span>{{ card.title }}</span><small>{{ card.text }}</small></div>
          <strong>{{ card.value }}</strong><ArrowRight :size="18" class="row-action" />
        </article>
      </div>
      <div class="module-note">静态演示数据 · 后续可接入真实学习记录</div>
    </div>
  </section>
</template>

<style scoped>
.module-page { min-height: 100vh; padding: 12vh 8vw; }.module-inner { width: min(920px, 100%); margin: 0 auto; }.module-topline { display: flex; align-items: center; justify-content: space-between; color: var(--muted); font-size: 13px; }.module-topline button { display: inline-flex; align-items: center; gap: 7px; border: 0; background: transparent; color: var(--muted); cursor: pointer; }.module-topline button:hover { color: var(--ink); }.module-page h1 { margin: 21px 0 9px; font-family: var(--font-display); font-size: clamp(42px, 5vw, 62px); font-weight: 500; letter-spacing: -.05em; }.module-intro { max-width: 600px; margin: 0; color: var(--muted); font-size: 15px; }.preview-list { margin-top: 64px; border-top: 1px solid var(--line); }.preview-row { display: flex; align-items: center; gap: 18px; min-height: 92px; border-bottom: 1px solid var(--line); color: var(--muted); }.preview-row > svg { color: var(--sage); }.row-copy { display: grid; gap: 3px; flex: 1; color: var(--ink); font-size: 16px; }.row-copy small { color: var(--muted); font-size: 13px; }.preview-row strong { color: var(--ink); font-family: var(--font-display); font-size: 26px; font-weight: 500; }.row-action { margin-left: 8px; color: var(--soft-muted); }.module-note { margin-top: 28px; color: var(--soft-muted); font-size: 12px; }
</style>
