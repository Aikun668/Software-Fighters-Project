<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, CalendarDays, Check, ChevronDown, Clock3, Edit3, Plus, RefreshCw, Sparkles, X } from '@lucide/vue'
import { getLearningSnapshot, type LearningSnapshot } from '@/api/learningSnapshot'
import { updatePlanProgress } from '@/api/plans'
import { resolveErrorMessage } from '@/utils/request'

type Task = { title: string; type: string; duration: string; source: string; done: boolean }
const router = useRouter()
const route = useRoute()
const editing = ref(false)
const aiAdjusting = ref(false)
const showAll = ref(true)
const onlyIncomplete = ref(false)
const planMenuOpen = ref(false)
const adjustmentOpen = ref(false)
const planName = ref('AI 工程师学习路径')
const actionSnapshot = ref<LearningSnapshot | null>(null)
const actionLoading = ref(false)
const actionSubmitting = ref(false)
const actionError = ref('')
const tasks = ref<Task[]>([
  { title: '复习监督学习与无监督学习的概念区别', type: '阅读', duration: '30min', source: 'ML基础', done: true },
  { title: '完成模型评估章节的阅读', type: '资源', duration: '45min', source: 'ML基础', done: false },
  { title: '练习 10 道交叉验证题', type: '练习', duration: '25min', source: 'ML基础', done: false },
  { title: '阅读 Transformer 架构概述', type: '阅读', duration: '20min', source: 'DL专项', done: false },
])
const completedCount = computed(() => tasks.value.filter(task => task.done).length)
const visibleTasks = computed(() => onlyIncomplete.value ? tasks.value.filter(task => !task.done) : tasks.value)
const toggleTask = (task: Task) => { task.done = !task.done }
const addTask = () => tasks.value.push({ title: '整理今天的学习笔记', type: '资源', duration: '20min', source: '自定义', done: false })
const removeTask = (task: Task) => { tasks.value = tasks.value.filter(item => item !== task) }
const regenerate = () => { aiAdjusting.value = true; window.setTimeout(() => { aiAdjusting.value = false }, 700) }
const choosePlan = (name: string) => { planName.value = name; planMenuOpen.value = false }

const queryValue = (value: unknown) => typeof value === 'string' ? value : ''
const courseId = computed(() => queryValue(route.query.courseId) || 'ai_intro')
const actionKind = computed(() => queryValue(route.query.actionKind))
const isPlanAction = computed(() => actionKind.value === 'resume_plan' || actionKind.value === 'review_current_node')
const actionTitle = computed(() => actionKind.value === 'review_current_node' ? '复习当前知识点' : '继续本周计划')
const actionActivityType = computed(() => actionKind.value === 'review_current_node' ? 'review' : 'study')
const currentStep = computed(() => actionSnapshot.value?.active_plan?.current_step ?? null)
const actionStepId = computed(() => {
  const fromQuery = Number(queryValue(route.query.stepId))
  return Number.isInteger(fromQuery) && fromQuery > 0 ? fromQuery : currentStep.value?.step_id ?? null
})
const actionPlanId = computed(() => actionSnapshot.value?.active_plan?.plan_id ?? null)
const actionTopic = computed(() => currentStep.value?.topic || actionSnapshot.value?.current_node?.name || '当前学习内容')
const canCompleteAction = computed(() => Boolean(actionPlanId.value && actionStepId.value))

const loadActionSnapshot = async () => {
  if (!isPlanAction.value) return
  actionLoading.value = true
  actionError.value = ''
  try {
    actionSnapshot.value = await getLearningSnapshot(courseId.value)
  } catch (error) {
    actionError.value = resolveErrorMessage(error)
  } finally {
    actionLoading.value = false
  }
}

const completeLearningAction = async () => {
  if (!canCompleteAction.value || !actionPlanId.value || !actionStepId.value) {
    actionError.value = '当前快照没有可提交的计划步骤，请返回学习入口重新读取。'
    return
  }

  actionSubmitting.value = true
  actionError.value = ''
  try {
    const response = await updatePlanProgress(actionPlanId.value, {
      step_id: actionStepId.value,
      step_order: currentStep.value?.order ?? 0,
      status: 'completed',
      activity_type: actionActivityType.value,
      score: 1,
      duration_minutes: 0,
    })
    const status = response.message || response.status || '计划动作已提交'
    await router.push({ path: '/learning-analysis', query: { courseId: courseId.value, progressStatus: status } })
  } catch (error) {
    actionError.value = resolveErrorMessage(error)
  } finally {
    actionSubmitting.value = false
  }
}

onMounted(() => { void loadActionSnapshot() })
</script>

<template>
  <section class="plan-page"><div class="plan-inner">
    <header class="plan-header">
      <div><span class="eyebrow">把目标变成今天可以完成的任务</span><h1>学习计划</h1></div>
      <div class="plan-actions">
        <div class="plan-selector">
          <button class="select-plan" @click="planMenuOpen = !planMenuOpen">当前计划：{{ planName }}<ChevronDown :size="15" /></button>
          <div v-if="planMenuOpen" class="plan-menu">
            <button class="selected" @click="choosePlan('AI 工程师学习路径')"><strong>AI 工程师学习路径</strong><small>65% · 12 模块 · 8 已完成</small></button>
            <button @click="choosePlan('数据分析师学习路径')"><strong>数据分析师学习路径</strong><small>30% · 6 模块 · 2 已完成</small></button>
            <button @click="choosePlan('Python 进阶专项')"><strong>Python 进阶专项</strong><small>10% · 4 模块 · 0 已完成</small></button>
            <button class="new-plan" @click="planMenuOpen = false"><Plus :size="14" />新建计划</button>
          </div>
        </div>
        <button class="outline-action" @click="planMenuOpen = true"><Plus :size="16" />新建计划</button>
      </div>
    </header>

    <section v-if="isPlanAction" class="learning-action-context" aria-live="polite">
      <div class="action-context-copy">
        <span class="eyebrow">从学习入口进入</span>
        <h2>{{ actionTitle }}</h2>
        <p>当前目标：{{ actionTopic }}</p>
        <small v-if="route.query.source === 'learning_snapshot'">本次动作来自学习快照建议，完成后会重新读取学情。</small>
      </div>
      <div class="action-context-controls">
        <span v-if="actionLoading" class="action-status">正在读取计划步骤…</span>
        <span v-else-if="actionError" class="action-error">{{ actionError }}</span>
        <button
          v-else
          data-test="complete-learning-action"
          class="primary-action"
          :disabled="actionSubmitting || !canCompleteAction"
          @click="completeLearningAction"
        >
          {{ actionSubmitting ? '正在提交…' : '完成本次动作' }}
          <Check :size="15" />
        </button>
      </div>
    </section>

    <section class="today-panel">
      <div class="today-head"><div><div class="today-title"><CalendarDays :size="20" :stroke-width="1.45" />今日计划 — 7月14日 周一</div><p>预计 2h · 来自 2 个计划 · 已完成 {{ completedCount }}/{{ tasks.length }}</p></div><button class="text-action" @click="editing = !editing"><Edit3 :size="15" />{{ editing ? '完成编辑' : '编辑' }}</button></div>
      <div class="task-list">
        <div v-for="task in visibleTasks" :key="task.title" class="task-row" :class="{ completed: task.done }">
          <button v-if="editing" class="drag-handle" aria-label="拖动任务">⋮⋮</button><button class="task-check" :class="{ checked: task.done }" @click="toggleTask(task)"><Check v-if="task.done" :size="14" /></button><span class="task-name" :contenteditable="editing" @blur="task.title = ($event.target as HTMLElement).innerText">{{ task.title }}</span><span class="task-type">{{ task.type }}</span><span class="task-duration"><Clock3 :size="14" />{{ task.duration }}</span><span class="task-source">{{ task.source }}</span><button v-if="editing" class="delete-task" aria-label="删除任务" @click="removeTask(task)">×</button>
        </div>
      </div>
      <div v-if="editing" class="edit-hint">拖动 ⋮⋮ 调整排序 · 点击任务文字修改 · 点击 × 删除任务</div>
      <div class="today-actions"><button class="outline-action" @click="addTask"><Plus :size="15" />{{ editing ? '添加一行' : '手动添加' }}</button><button class="outline-action" :class="{ loading: aiAdjusting }" @click="regenerate"><RefreshCw :size="15" />重新生成</button><button class="primary-action" @click="tasks.forEach(task => task.done = true)"><Check :size="15" />全部完成</button></div>
    </section>

    <div class="plan-grid">
      <section class="timeline-panel">
        <div class="section-head"><div><span class="eyebrow">长期计划</span><h2>{{ planName }}</h2></div><button class="text-action" @click="editing = !editing"><Edit3 :size="15" />编辑路径</button></div>
        <div class="timeline-summary"><div><strong>65%</strong><span>12 模块 · 8 已完成 · 预计 12 周 · 连续学习 14 天</span></div><div class="timeline-controls"><button :class="{ active: onlyIncomplete }" @click="onlyIncomplete = !onlyIncomplete">仅看未完成</button><button :class="{ active: !showAll }" @click="showAll = !showAll">{{ showAll ? '全部折叠' : '全部展开' }}</button><button @click="adjustmentOpen = true"><RefreshCw :size="13" />AI 调整计划</button></div></div>
        <div class="timeline">
          <div v-for="(item, index) in [{ title: '机器学习基础', detail: '监督学习、模型评估与交叉验证', status: 'done', progress: '100%' }, { title: '深度学习专项', detail: 'CNN、Transformer 与训练方法', status: 'current', progress: '42%' }, { title: 'AI 工程实践', detail: '模型部署、项目实战与作品集', status: 'pending', progress: '0%' }]" :key="item.title" class="timeline-item"><div class="timeline-marker" :class="item.status"><Check v-if="item.status === 'done'" :size="13" /><span v-else>{{ index + 1 }}</span></div><div class="timeline-copy"><strong>{{ item.title }}</strong><p v-if="showAll || item.status !== 'done'">{{ item.detail }}</p><div class="progress-track"><i :style="{ width: item.progress }" /></div><small>{{ item.progress }} 完成</small><div v-if="showAll && item.status === 'current'" class="submodule-row"><span>✓ 监督学习</span><span>✓ 无监督学习</span><span>› 模型评估</span><span>○ 特征工程</span></div></div><button v-if="item.status !== 'pending'" class="row-arrow" @click="router.push('/learning-resource-network')"><ArrowRight :size="17" /></button></div>
        </div><button class="show-more" @click="showAll = !showAll">{{ showAll ? '收起路径' : '查看完整路径' }} <ChevronDown :size="15" /></button>
      </section>
      <aside class="insight-panel"><div class="section-head"><div><span class="eyebrow">计划洞察</span><h2>保持当前节奏</h2></div><Sparkles :size="20" :stroke-width="1.35" /></div><div class="insight-list"><p>⚠ 数学基础已 14 天未复习，掌握度从 90% 衰减至 55%。</p><p>↗ 按当前节奏，预计比原计划提前 3 天完成。</p><p>⌁ 知识图谱新增了“注意力机制”节点。 <button class="inline-link" @click="addTask">一键加入</button></p></div><div class="insight-metric"><strong>6天</strong><span>连续学习</span></div><div class="insight-metric"><strong>76%</strong><span>本周完成率</span></div><button class="text-action" @click="router.push('/learning-analysis')">查看完整学情分析 <ArrowRight :size="15" /></button></aside>
    </div>
  </div>
  <div v-if="adjustmentOpen" class="modal-backdrop" @click.self="adjustmentOpen = false"><section class="adjust-modal"><button class="close-modal" @click="adjustmentOpen = false"><X :size="18" /></button><span class="eyebrow">AI 调整预览</span><h2>根据你的近期节奏调整计划</h2><p>系统会只调整受影响的依赖链，并保留已完成模块。</p><div class="adjust-preview"><strong>预计调整</strong><span>深度学习专项：本周任务减少 1 项</span><span>恢复后自动加入：矩阵运算复习（30min）</span><span>新的预计完成日：10 月 20 日</span></div><footer><button class="outline-action" @click="adjustmentOpen = false">取消</button><button class="primary-action" @click="adjustmentOpen = false; regenerate()">应用调整</button></footer></section></div>
  </section>
</template>

<style scoped>
.plan-page{min-height:100vh;padding:44px 52px 70px}.plan-inner{max-width:1240px;margin:auto}.eyebrow{color:var(--muted);font-size:12px}.plan-header{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:34px}.plan-header h1{margin:8px 0 0;font-family:var(--font-display);font-size:40px;font-weight:500;letter-spacing:-.04em}.plan-actions{display:flex;gap:10px}.plan-selector{position:relative}.select-plan,.outline-action,.primary-action,.text-action{display:inline-flex;align-items:center;gap:7px;border:1px solid var(--line);border-radius:9px;background:transparent;cursor:pointer;font-size:12px}.select-plan{padding:10px 12px;color:var(--ink)}.outline-action{padding:9px 12px;color:var(--muted)}.primary-action{padding:9px 13px;border-color:var(--sage);background:var(--sage);color:#fff}.text-action{border:0;padding:0;color:var(--muted)}button:hover{color:var(--ink)}.plan-menu{position:absolute;top:44px;right:0;z-index:3;display:grid;width:280px;padding:7px;border:1px solid var(--line);border-radius:11px;background:var(--page);box-shadow:0 12px 30px rgba(70,58,43,.12)}.plan-menu button{display:grid;gap:4px;padding:11px;border:0;border-radius:7px;background:transparent;text-align:left;cursor:pointer}.plan-menu button:hover,.plan-menu button.selected{background:var(--sage-soft)}.plan-menu strong{font-size:12px;font-weight:500}.plan-menu small{color:var(--muted);font-size:10px}.plan-menu .new-plan{display:flex;align-items:center;color:var(--sage)}.today-panel,.timeline-panel,.insight-panel{border:1px solid var(--line);border-radius:var(--radius-panel);background:rgba(255,254,250,.58)}.today-panel{padding:25px}.today-head,.today-actions,.section-head{display:flex;align-items:center;justify-content:space-between}.today-title{display:flex;align-items:center;gap:9px;font-size:17px}.today-title svg{color:var(--sage)}.today-head p{margin:8px 0 0;color:var(--muted);font-size:12px}.task-list{margin-top:22px;border-top:1px solid var(--line)}.task-row{display:flex;align-items:center;gap:12px;min-height:54px;border-bottom:1px solid var(--line);font-size:13px}.task-row.completed .task-name{color:var(--soft-muted);text-decoration:line-through}.task-check{display:grid;place-items:center;width:19px;height:19px;border:1px solid #cfc8bb;border-radius:5px;background:transparent;color:#fff;cursor:pointer}.task-check.checked{border-color:var(--sage);background:var(--sage)}.drag-handle{border:0;background:transparent;color:var(--soft-muted);cursor:grab}.task-name{flex:1;color:var(--ink);outline:0}.task-type,.task-source{color:var(--muted);font-size:11px}.task-duration{display:inline-flex;align-items:center;gap:4px;width:68px;color:var(--muted);font-size:11px}.delete-task{border:0;background:transparent;color:var(--clay);font-size:18px;cursor:pointer}.edit-hint{padding:10px 0;color:var(--soft-muted);font-size:11px}.today-actions{justify-content:flex-start;gap:9px;margin-top:20px}.loading svg{animation:spin .7s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}.plan-grid{display:grid;grid-template-columns:1.45fr .75fr;gap:18px;margin-top:18px}.timeline-panel,.insight-panel{padding:25px}.section-head h2{margin:7px 0 0;font-family:var(--font-display);font-size:22px;font-weight:500}.timeline-summary{display:flex;justify-content:space-between;gap:15px;align-items:flex-end;margin-top:25px;padding:16px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.timeline-summary div:first-child{display:grid;gap:4px}.timeline-summary strong{font-family:var(--font-display);font-size:29px;font-weight:500}.timeline-summary span{color:var(--muted);font-size:11px}.timeline-controls{display:flex;gap:6px}.timeline-controls button{display:inline-flex;align-items:center;gap:4px;padding:6px 8px;border:1px solid var(--line);border-radius:7px;background:transparent;color:var(--muted);cursor:pointer;font-size:10px}.timeline-controls button.active,.timeline-controls button:hover{background:var(--sage-soft);color:var(--ink)}.timeline{margin-top:28px}.timeline-item{display:flex;gap:15px;min-height:98px}.timeline-marker{display:grid;place-items:center;width:25px;height:25px;flex:0 0 auto;margin-top:1px;border:1px solid #c7c1b5;border-radius:50%;color:var(--muted);font-size:11px}.timeline-marker.done{border-color:var(--sage);background:var(--sage);color:#fff}.timeline-marker.current{border-color:var(--sage);color:var(--sage)}.timeline-copy{flex:1}.timeline-copy strong{font-size:14px;font-weight:500}.timeline-copy p{margin:4px 0 9px;color:var(--muted);font-size:12px}.progress-track{height:5px;background:#eeeae2;border-radius:10px}.progress-track i{display:block;height:100%;border-radius:10px;background:var(--sage)}.timeline-copy small{display:block;margin-top:5px;color:var(--soft-muted);font-size:10px}.submodule-row{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px;color:var(--muted);font-size:10px}.submodule-row span{padding:4px 6px;border:1px solid var(--line);border-radius:5px}.row-arrow{align-self:flex-start;margin-top:2px;border:0;background:transparent;color:var(--muted);cursor:pointer}.show-more{display:inline-flex;align-items:center;gap:6px;margin:5px 0 0 40px;border:0;background:transparent;color:var(--muted);cursor:pointer;font-size:11px}.insight-panel p{margin:0;padding:11px 0;border-bottom:1px solid var(--line);color:var(--muted);font-size:12px;line-height:1.6}.insight-list{margin:22px 0}.inline-link{border:0;background:transparent;color:var(--sage);cursor:pointer;font-size:11px}.insight-metric{display:inline-flex;flex-direction:column;gap:2px;width:49%;padding:15px 0;border-top:1px solid var(--line)}.insight-metric strong{font-family:var(--font-display);font-size:28px;font-weight:500}.insight-metric span{color:var(--muted);font-size:11px}.insight-panel .text-action{margin-top:25px}.modal-backdrop{position:fixed;inset:0;z-index:5;display:grid;place-items:center;background:rgba(36,35,31,.16)}.adjust-modal{position:relative;width:min(520px,90vw);padding:28px;border:1px solid var(--line);border-radius:15px;background:var(--page);box-shadow:0 18px 50px rgba(70,58,43,.12)}.adjust-modal h2{margin:9px 0;font-family:var(--font-display);font-size:24px;font-weight:500}.adjust-modal p{color:var(--muted);font-size:13px}.close-modal{position:absolute;top:18px;right:18px;border:0;background:transparent;color:var(--muted);cursor:pointer}.adjust-preview{display:grid;gap:9px;margin:22px 0;padding:17px;border:1px solid var(--line);border-radius:10px;background:var(--surface-muted);color:var(--muted);font-size:12px}.adjust-preview strong{color:var(--ink);font-weight:500}.adjust-modal footer{display:flex;justify-content:flex-end;gap:8px}@media(max-width:1000px){.plan-page{padding:30px 24px}.plan-header,.plan-actions{align-items:flex-start;flex-direction:column}.plan-grid{grid-template-columns:1fr}.timeline-summary{align-items:flex-start;flex-direction:column}}@media(max-width:650px){.plan-page{padding:24px 16px}.today-panel,.timeline-panel,.insight-panel{padding:18px}.task-row{flex-wrap:wrap;padding:10px 0;gap:8px}.task-name{min-width:calc(100% - 35px)}.task-type{margin-left:31px}.today-actions,.timeline-controls{flex-wrap:wrap}}
.learning-action-context{display:flex;align-items:center;justify-content:space-between;gap:24px;margin-bottom:18px;padding:20px 24px;border:1px solid var(--line);border-radius:var(--radius-panel);background:rgba(255,254,250,.58)}.action-context-copy{display:grid;gap:6px}.action-context-copy h2{margin:0;font-family:var(--font-display);font-size:22px;font-weight:500}.action-context-copy p{margin:0;color:var(--ink);font-size:13px}.action-context-copy small{color:var(--muted);font-size:11px}.action-context-controls{display:flex;align-items:center;gap:12px;flex:0 0 auto}.action-status,.action-error{color:var(--muted);font-size:12px}.action-error{max-width:280px;color:#b4483c}@media(max-width:650px){.learning-action-context{align-items:flex-start;flex-direction:column;padding:18px}.action-context-controls{width:100%}.action-context-controls .primary-action{width:100%}}
</style>
