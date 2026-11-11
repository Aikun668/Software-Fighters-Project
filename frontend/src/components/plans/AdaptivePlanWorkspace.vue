<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { addAdaptiveTask, listAdaptivePlans, getAdaptivePlan, createAdaptivePlan, updateAdaptiveTask, proposeAdjustment, applyAdjustment, undoAdjustment, type AdaptivePlan, type AdaptiveTask, type AdaptiveTaskStatus, type PlanProposal } from '@/api/adaptivePlans'
import { setLearningDraft } from '@/utils/learningDraft'
import { resolveErrorMessage } from '@/utils/request'
const props = defineProps<{ planId?: string; compact?: boolean }>()
const router = useRouter(), route = useRoute()
const plans = ref<AdaptivePlan[]>([])
const current = ref<AdaptivePlan | null>(null)
const loading = ref(false), busy = ref(false), error = ref(''), notice = ref(''), creating = ref(false)
const title = ref(''), goal = ref(''), dailyMinutes = ref(20), deadline = ref('')
const draftModules = ref([{ title: '', tasks: [{ title: '', minutes: 20 }] }])
const proposedDeadline = ref('')
const adjustment = ref(''), proposedDaily = ref<number | undefined>(), proposal = ref<PlanProposal | null>(null), resolution = ref('')
const refining = ref<string | null>(null), newTaskTitle = ref(''), newTaskMinutes = ref(20), newTaskNext = ref(''), adjustmentTask = ref('')
const editing = ref<string | null>(null), checkpoint = ref(''), nextAction = ref(''), editStatus = ref<AdaptiveTaskStatus>('paused')
function errorMessage(e: unknown): string {
  const response = (e as {response?: {data?: {message?: string}}})?.response?.data?.message
  return response || resolveErrorMessage(e)
}
const labels: Record<AdaptiveTaskStatus, string> = { pending: '待开始', in_progress: '进行中', paused: '已暂停', blocked: '有卡点', completed: '自报完成', deferred: '已延期' }
const tasks = computed(() => current.value?.modules.flatMap(module => module.tasks) ?? [])
const completed = computed(() => tasks.value.filter(task => task.status === 'completed').length)
const upcoming = computed(() => tasks.value.filter(task => !['completed', 'deferred'].includes(task.status)).slice(0, 3))
const display = (value: unknown): string => {
  if (value === null || value === undefined) return '未设置'
  if (typeof value === 'string') return value || '未设置'
  if (typeof value === 'number') return `${value} 分钟`
  if (Array.isArray(value)) return value.map(display).join('；')
  if (value && typeof value === 'object' && 'title' in value) {
    const t = value as AdaptiveTask
    const parts = [`${t.title} · ${t.minutes} 分钟 · ${labels[t.status] || t.status}`]
    if (t.checkpoint) parts.push(`断点：${t.checkpoint}`)
    if (t.nextAction) parts.push(`下一步：${t.nextAction}`)
    return parts.join(' · ')
  }
  return JSON.stringify(value)
}
const changeLabels: Record<string, string> = { keep: '保留', split: '拆分', defer: '延期', checkpoint: '卡点', budget: '每日时间', deadline: '截止日期' }
const changeLabel = (kind: string): string => changeLabels[kind] || kind
function continueInChat() {
  if (!current.value) return
  const plan = current.value, task = upcoming.value[0]
  const module = plan.modules.find(m => m.tasks.some(t => t.id === task?.id))
  const draft = `当前计划 v${plan.version}（若与此前计划描述冲突，以本段为准）。\n请帮我继续学习，不要直接修改我的计划。\n目标：${plan.goal}\n模块：${module?.title || '尚未选择'}\n当前任务：${task?.title || '请帮我细化下一步'}\n断点：${task?.checkpoint || '无记录'}\n下一步：${task?.nextAction || '请建议一个可执行动作'}\n每日可用时间：${plan.dailyMinutes} 分钟。计划调整请在计划面板预览并由我确认。`
  const inExistingChat = props.compact && ['/question-nav-chat', '/ai-tutor'].includes(route.path)
  void router.push({path:inExistingChat ? route.path : '/question-nav-chat', query:{...(inExistingChat ? route.query : {}),planId:plan.id,learningContext:setLearningDraft(draft)}})
}
const resetDraft = () => { proposal.value = null; resolution.value = ''; editing.value = null }
function accept(plan: AdaptivePlan) { loadSequence++; current.value = plan; plans.value = [plan, ...plans.value.filter(item => item.id !== plan.id)]; resetDraft() }
async function perform(action: () => Promise<void>) { if (busy.value || loading.value) return; busy.value = true; error.value = ''; notice.value = ''; try { await action() } catch (e) { error.value = errorMessage(e) } finally { busy.value = false } }
let loadSequence = 0
async function load(id?: string) {
  if (busy.value) return
  const sequence = ++loadSequence
  adjustmentTask.value = ''; proposedDaily.value = undefined; proposedDeadline.value = ''; adjustment.value = ''; refining.value = null
  loading.value = true; error.value = ''; resetDraft()
  try {
    const all = await listAdaptivePlans()
    const selected = id ? await getAdaptivePlan(id) : all[0] ?? null
    if (sequence !== loadSequence) return
    plans.value = all; current.value = selected
  } catch (e) { if (sequence === loadSequence) error.value = errorMessage(e) }
  finally { if (sequence === loadSequence) loading.value = false }
}
async function selectPlan(event: Event) { const id = (event.target as HTMLSelectElement).value; await load(id); if (current.value?.id === id) await router.replace({query:{...route.query,planId:id}}) }
async function create() {
  await perform(async () => {
    if (!title.value.trim() || !goal.value.trim() || draftModules.value.some(m => !m.title.trim() || m.tasks.some(t => !t.title.trim() || t.minutes < 1))) throw new Error('请填写目标、模块和任务，预计用时至少 1 分钟。')
    accept(await createAdaptivePlan({ title: title.value.trim(), goal: goal.value.trim(), dailyMinutes: dailyMinutes.value, deadline: deadline.value || null, modules: draftModules.value }))
    creating.value = false; notice.value = '计划已保存。先做眼前的一小步。'
    await router.replace({query:{...route.query,planId:current.value!.id}})
  })
}
function edit(task: AdaptiveTask) { editing.value = task.id; checkpoint.value = task.checkpoint || ''; nextAction.value = task.nextAction || ''; editStatus.value = task.status === 'deferred' ? 'paused' : task.status }
async function saveTask(task: AdaptiveTask, status: AdaptiveTaskStatus, fromEditor = false) {
  if (!current.value) return
  const plan = current.value
  await perform(async () => { accept(await updateAdaptiveTask(plan.id, task.id, { version: plan.version, status, checkpoint: fromEditor ? checkpoint.value : task.checkpoint || '', nextAction: fromEditor ? nextAction.value : task.nextAction || '' })); notice.value = status === 'completed' ? '已记录你自报完成；不会据此宣称已掌握。' : '断点与状态已保存。' })
}
async function propose() {
  if (!current.value || !adjustment.value.trim()) return
  const plan = current.value
  await perform(async () => { proposal.value = await proposeAdjustment(plan.id, { version: plan.version, message: adjustment.value.trim(), ...(proposedDeadline.value ? {deadline:proposedDeadline.value} : {}), ...(adjustmentTask.value ? {taskId:adjustmentTask.value} : {}), ...(proposedDaily.value ? { dailyMinutes: proposedDaily.value } : {}) }); resolution.value = '' })
}
async function confirm() {
  if (!current.value || !proposal.value || (proposal.value.conflict && !resolution.value)) return
  const plan = current.value, draft = proposal.value
  await perform(async () => { accept(await applyAdjustment(plan.id, draft.id, { version: draft.baseVersion, ...(resolution.value ? {resolution: resolution.value} : {}) })); notice.value = '调整已保存，已完成内容保留。'; adjustment.value = '' })
}
async function undo() { if (!current.value) return; const plan = current.value; await perform(async () => { accept(await undoAdjustment(plan.id, {version: plan.version})); notice.value = '最近一次调整已撤销。' }) }
async function addTask(moduleId: string) {
  if (!current.value) return
  const plan = current.value
  await perform(async () => { accept(await addAdaptiveTask(plan.id, moduleId, {version:plan.version,title:newTaskTitle.value.trim(),minutes:newTaskMinutes.value,nextAction:newTaskNext.value.trim()})); refining.value = null; newTaskTitle.value = ''; newTaskNext.value = ''; notice.value = '新的小任务已保存。' })
}
onMounted(() => { void load(props.planId) })
watch([adjustment, proposedDaily, proposedDeadline, adjustmentTask], () => { proposal.value = null; resolution.value = '' })
let pendingRouteLoad = false
watch(() => props.planId, id => {
  if (id === current.value?.id) return
  if (busy.value) pendingRouteLoad = true
  else void load(id)
})
watch(busy, isBusy => {
  if (!isBusy && pendingRouteLoad) {
    pendingRouteLoad = false
    void load(props.planId)
  }
})
</script>
<template>
  <section class="adaptive-workspace" :class="{compact}" aria-label="动态学习计划">
    <header class="plan-heading"><div><span class="eyebrow">LEARNING, ONE STEP AT A TIME</span><h1>{{ compact ? '对话中的计划' : '学习计划' }}</h1><p>计划可以中断，进度不必重来。</p></div><div class="toolbar"><button :disabled="busy || loading" @click="load(current?.id)">刷新</button><button :disabled="busy || loading" @click="creating = !creating">{{ creating ? '收起新建' : '新建计划' }}</button></div></header>
    <p v-if="error" role="alert" class="error">{{ error }} <span>未确认的更改不会保存；若版本已变化，请刷新后重试。</span></p>
    <p v-if="notice" role="status" class="notice">{{ notice }}</p>
    <p v-if="loading" role="status">正在读取保存的计划…</p>
    <form v-if="!loading && (creating || (!loading && !current && !error))" class="panel create-form" @submit.prevent="create">
      <h2>把一个目标变成几个可执行的块</h2><p>先列出模块和任务；不清楚的远期内容只写模块，也可以稍后再细化。</p>
      <label>计划名称<input data-testid="create-title" v-model="title" required maxlength="120" placeholder="例如：数据库事务入门" /></label>
      <label>想达成什么<textarea data-testid="create-goal" v-model="goal" required maxlength="1000" placeholder="例如：能解释隔离级别，并运行一个幻读例子" /></label>
      <div class="form-row"><label>每天可投入（分钟）<input data-testid="create-daily" v-model.number="dailyMinutes" type="number" min="1" max="480" required /></label><label>期望截止日（可选）<input data-testid="create-deadline" v-model="deadline" type="date" /></label></div>
      <fieldset v-for="(module, index) in draftModules" :key="index"><legend>模块 {{ index + 1 }}</legend><label>模块名称<input :data-testid="`module-title-${index}`" v-model="module.title" required maxlength="120" /></label><div v-for="(task, taskIndex) in module.tasks" :key="taskIndex" class="draft-task"><label>小任务<input :data-testid="`task-title-${index}-${taskIndex}`" v-model="task.title" required maxlength="200" placeholder="一个具体动作" /></label><label>分钟<input :data-testid="`task-minutes-${index}-${taskIndex}`" v-model.number="task.minutes" type="number" min="1" max="480" required /></label><button type="button" :aria-label="`移除任务 ${taskIndex + 1}`" @click="module.tasks.splice(taskIndex,1)">移除</button></div><button type="button" @click="module.tasks.push({title:'',minutes:20})">＋小任务</button><button v-if="draftModules.length > 1" type="button" @click="draftModules.splice(index,1)">移除模块</button></fieldset>
      <div class="toolbar"><button type="button" @click="draftModules.push({title:'',tasks:[]})">＋远期模块</button><button data-testid="create-submit" class="primary" :disabled="busy" type="submit">{{ busy ? '正在保存…' : '创建并保存' }}</button></div>
    </form>
    <template v-if="current && !loading">
      <div class="plan-summary"><select data-testid="select-plan" aria-label="选择计划" :value="current.id" :disabled="busy" @change="selectPlan"><option v-for="plan in plans" :key="plan.id" :value="plan.id">{{plan.title}}</option></select><span>v{{current.version}} · 每天 {{current.dailyMinutes}} 分钟</span><span v-if="current.deadline">期望 {{current.deadline}}</span></div>
      <p class="goal">{{current.goal}}</p><p v-if="current.capacityWarning" class="conflict" role="status">{{current.capacityWarning}} 请在下方预览调整，明确选择延长期限或延期部分任务。</p>
      <div class="overview"><strong>{{completed}} / {{tasks.length}} <small>任务自报完成</small></strong><span>完成不等于掌握；不会自动修改知识图谱。</span></div>
      <section class="panel next-panel"><div class="section-title"><h2>接下来，只看这 {{upcoming.length}} 步</h2><button @click="continueInChat">{{compact ? '用最新计划准备续学草稿' : '带着计划去对话 ↗'}}</button></div><p v-if="!upcoming.length">{{tasks.length && completed === tasks.length ? '已列出的任务都已完成。回顾目标，决定下一阶段。' : '暂无近期任务。先细化模块，或调整延期任务。'}}</p><article v-for="task in upcoming" :key="task.id" class="next-task"><div><b>{{task.title}}</b><span>{{task.minutes}} 分钟 · {{labels[task.status]}}</span></div><p v-if="task.checkpoint">上次停在：{{task.checkpoint}}</p><p v-if="task.nextAction">下一步：{{task.nextAction}}</p><div class="toolbar"><button :data-test="`resume-${task.id}`" :disabled="busy" @click="saveTask(task,'in_progress')">{{['paused','blocked'].includes(task.status) ? '从断点继续' : '开始这一小步'}}</button><button :disabled="busy" :data-testid="`edit-${task.id}`" @click="edit(task)">记录断点 / 暂停</button><button :disabled="busy" :data-testid="`complete-${task.id}`" @click="saveTask(task,'completed')">我已完成</button></div></article></section>
      <section v-if="editing" class="panel checkpoint-editor"><h2>留下一个能接住自己的断点</h2><label>做到哪里 / 卡在哪里<textarea data-testid="checkpoint" v-model="checkpoint" maxlength="2000" placeholder="例如：读到幻读定义，但还没有跑示例" /></label><label>回来后的第一步<input data-testid="next-action" v-model="nextAction" maxlength="1000" placeholder="例如：打开两个终端，运行示例 SQL" /></label><label>当前状态<select data-testid="task-status" v-model="editStatus"><option value="pending">还没开始</option><option value="in_progress">继续进行</option><option value="paused">暂停，稍后继续</option><option value="blocked">有卡点，需要帮助</option><option value="completed">已完成（自报）</option></select></label><div class="toolbar"><button :disabled="busy" @click="editing=null">取消</button><button class="primary" :disabled="busy" data-testid="save-checkpoint" @click="saveTask(tasks.find(t => t.id === editing)!,editStatus,true)">保存断点</button></div></section>
      <section class="panel adjustment"><h2>情况变了？局部调整，不推倒重来</h2><p>当前 MVP 支持每天分钟数、拆分、卡点和延期。先预览，再由你确认。普通问答或「学习规划」模式生成的文字不会修改此计划。计划修改也不会自动更新聊天上下文，请用「最新计划准备续学草稿」再确认发送。</p><label>告诉计划发生了什么<textarea data-test="adjust-message" v-model="adjustment" maxlength="2000" placeholder="例如：每天只有20分钟，想把长任务拆小；或：延期某个任务" :disabled="busy" /></label><label>要调整的任务（卡点 / 延期）<select v-model="adjustmentTask" :disabled="busy"><option value="">默认：第一个未完成且未延期的任务</option><option v-for="task in tasks.filter(t => !['completed', 'deferred'].includes(t.status))" :key="task.id" :value="task.id">{{task.title}}</option></select></label><p>延期任务请先在完整路线中「重新列入」，再进行调整。</p><label>新的每日预算（可选）<input v-model.number="proposedDaily" type="number" min="1" max="480" :disabled="busy" placeholder="分钟" /></label><label>新的期望截止日（可选）<input v-model="proposedDeadline" type="date" :disabled="busy" /></label><button data-test="propose" class="primary" :disabled="busy || !adjustment.trim()" @click="propose">{{busy ? '处理中…' : '预览调整'}}</button>
        <div v-if="proposal" class="proposal" aria-live="polite"><h3>待确认的改动 · 尚未保存</h3><p v-if="proposal.message">你的请求：{{proposal.message}}</p><p v-if="proposal.proposedPlan">每日预算：{{current.dailyMinutes}} → {{proposal.proposedPlan.dailyMinutes}} 分钟<br />期望期限：{{current.deadline || '未设置'}} → {{proposal.proposedPlan.deadline || '未设置'}}</p><ul><li v-for="(change,index) in proposal.changes" :key="index"><b>{{ changeLabel(change.kind) }}</b><div>{{display(change.before)}} → {{display(change.after)}}</div></li></ul><p v-if="!proposal.changes.length">没有任务变更。请检查你的调整内容。</p><div v-if="proposal.conflict" class="conflict"><b>目标期限与可用时间冲突</b><p>{{typeof proposal.conflict === 'string' ? proposal.conflict : proposal.conflict.message || display(proposal.conflict)}}</p><p v-if="proposal.extendedDeadline">保留全部内容：新期限 {{proposal.extendedDeadline}}</p><div v-if="proposal.deferredTasks?.length"><b>若选择延期，将移出本期期限（仍保留，可重新列入）：</b><ul><li v-for="task in proposal.deferredTasks" :key="task.id">{{task.title}} · {{task.minutes}} 分钟</li></ul></div><label>明确选择后才能保存<select v-model="resolution" data-test="conflict-resolution"><option value="">请选择取舍</option><option value="extend">延长期限，保留全部内容</option><option value="defer">延期超出的内容，不算完成</option></select></label></div><div class="toolbar"><button data-test="cancel-proposal" :disabled="busy" @click="proposal=null; resolution=''">取消，不修改计划</button><button data-test="confirm-proposal" class="primary" :disabled="busy || (!!proposal.conflict && !resolution)" @click="confirm">确认并保存</button></div></div>
      </section>
      <section class="panel"><div class="section-title"><h2>完整路线</h2><button :disabled="busy || !current.history?.length || current.canUndo === false" data-testid="undo" @click="undo">撤销最近一次调整</button></div><details v-for="module in current.modules" :key="module.id" open><summary>{{module.title}} <small>{{module.tasks.filter(t=>t.status==='completed').length}} / {{module.tasks.length}}</small></summary><p v-if="!module.tasks.length">远期模块，尚未细化。</p><div v-for="task in module.tasks" :key="task.id" class="route-task"><span>{{task.title}}</span><small>{{task.minutes}} 分钟 · {{labels[task.status]}}</small><button v-if="task.status === 'deferred'" :disabled="busy" :data-testid="`restore-${task.id}`" @click="saveTask(task,'pending')">重新列入</button><button v-if="task.status === 'completed'" :disabled="busy" :data-testid="`reopen-${task.id}`" @click="saveTask(task,'pending')">改回未完成</button></div>
        <button :disabled="busy" :data-testid="`refine-${module.id}`" @click="refining=module.id">＋细化下一步</button>
        <form v-if="refining === module.id" class="refine-form" @submit.prevent="addTask(module.id)"><label>任务名称<input data-testid="refine-title" v-model="newTaskTitle" required maxlength="200" /></label><label>预计分钟<input data-testid="refine-minutes" v-model.number="newTaskMinutes" type="number" min="1" max="480" required /></label><label>第一步<input v-model="newTaskNext" maxlength="1000" /></label><div class="toolbar"><button type="button" :disabled="busy" @click="refining=null">取消</button><button data-testid="refine-submit" type="submit" :disabled="busy" class="primary">保存小任务</button></div></form>
      </details><details v-if="current.history?.length"><summary>调整记录（{{current.history.length}}）</summary><p v-for="(item,index) in current.history" :key="index">{{item.message || item.action || display(item)}}</p></details></section>
    </template>
  </section>
</template>
<style scoped>
.adaptive-workspace{max-width:1040px;margin:auto;padding:32px 24px 80px;color:#1f3431;font-size:14px;line-height:1.6}.plan-heading,.section-title,.plan-summary,.overview,.next-task>div:first-child{display:flex;justify-content:space-between;align-items:center;gap:16px}.eyebrow{font-size:10px;letter-spacing:2px;color:#67857b}h1{font-size:30px;margin:4px 0}h2{font-size:18px;margin:0 0 12px}h3{font-size:16px}p{color:#6d7a76;margin:8px 0 16px}.panel{background:#fff;border:1px solid #e0e8e3;border-radius:16px;padding:24px;margin:20px 0}.toolbar{display:flex;gap:8px;flex-wrap:wrap}button,select,input,textarea{font:inherit;border:1px solid #d6e1db;border-radius:8px;background:#fff;padding:9px 12px;color:inherit}button{cursor:pointer}button:hover{background:#eff5f1}button:disabled{opacity:.5;cursor:not-allowed}.primary{background:#285e4c;color:white;border-color:#285e4c}.primary:hover{background:#214d3e}label{display:flex;flex-direction:column;gap:6px;margin-bottom:14px}input,textarea{min-width:0;width:100%;box-sizing:border-box}textarea{resize:vertical;min-height:80px}.form-row,.draft-task{display:grid;grid-template-columns:1fr 1fr;gap:16px}.draft-task{grid-template-columns:1fr 110px auto;align-items:center}fieldset{border:1px solid #e0e8e3;border-radius:10px;margin-bottom:14px;padding:16px}.plan-summary{justify-content:flex-start;flex-wrap:wrap;margin-top:24px}.plan-summary span{font-size:12px;color:#75867f}.goal{font-size:18px;color:#36564a}.overview{background:#eaf2ec;border-radius:12px;padding:14px 20px}.overview strong{font-size:24px}.overview small,.overview>span{font-size:12px;font-weight:400}.next-panel{border-color:#bacfc0}.next-task{padding:18px 0;border-top:1px solid #e6ece7}.next-task span{font-size:12px;color:#748478}.next-task p{margin:8px 0}.route-task{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid #edf1ee}.route-task small,summary small{color:#7b8d82}summary{cursor:pointer;font-weight:600;padding:12px 0}.proposal{background:#f4f7f0;border-radius:12px;padding:20px;margin-top:20px}.proposal li{margin:14px 0;overflow-wrap:anywhere}.conflict,.error{padding:14px;background:#fff0e7;color:#975326;border-radius:10px}.error span{display:block;font-size:12px}.notice{padding:12px;background:#e9f5ec;color:#2b6741;border-radius:10px}.refine-form{margin:16px 0;padding:16px;background:#f4f7f0;border-radius:8px}.compact{padding:20px 8px;max-height:55vh;overflow:auto;border:1px solid #e0e8e3;border-radius:14px;flex-shrink:0}.compact h1{font-size:20px}.compact .panel{padding:16px}.compact .plan-heading p{display:none}@media(max-width:640px){.adaptive-workspace{padding:20px 12px 60px}.plan-heading,.overview,.section-title,.next-task>div:first-child{align-items:flex-start;flex-direction:column}.panel{padding:16px}.form-row{grid-template-columns:1fr}.draft-task{grid-template-columns:1fr 80px}.draft-task>button{grid-column:1/-1}.route-task{flex-direction:column;gap:2px}.compact{padding:12px;max-height:50vh}}
</style>
