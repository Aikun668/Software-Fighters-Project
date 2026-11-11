<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, RefreshCw } from '@lucide/vue'
import { getLearningSnapshot, type LearningNextAction, type LearningSnapshot } from '@/api/learningSnapshot'
import { resolveErrorMessage } from '@/utils/request'

const router = useRouter()
const route = useRoute()
const snapshot = ref<LearningSnapshot | null>(null)
const snapshotLoading = ref(true)
const snapshotError = ref('')
const refreshing = ref(false)
const recommendationDismissed = ref(false)
const courseId = computed(() => {
  const value = route.query.courseId
  return typeof value === 'string' && value.trim() ? value : 'ai_intro'
})
const progressStatus = computed(() => {
  const value = route.query.progressStatus
  return typeof value === 'string' ? value : ''
})
const loadSnapshot = async () => {
  snapshotLoading.value = true
  refreshing.value = true
  snapshotError.value = ''
  snapshot.value = null
  recommendationDismissed.value = false

  try {
    snapshot.value = await getLearningSnapshot(courseId.value)
  } catch (error) {
    snapshotError.value = resolveErrorMessage(error)
  } finally {
    snapshotLoading.value = false
    refreshing.value = false
  }
}

const refresh = () => { void loadSnapshot() }

const freshnessIncomplete = computed(() => {
  const freshness = snapshot.value?.freshness
  return !freshness || freshness.stale || freshness.missing_sources.length > 0
})
const snapshotUnavailable = computed(() => Boolean(snapshotError.value) || freshnessIncomplete.value)
const nextAction = computed<LearningNextAction | null>(() => {
  if (!snapshot.value || snapshotUnavailable.value || recommendationDismissed.value) return null
  return snapshot.value.next_action ?? null
})
const actionTitle = computed(() => {
  switch (nextAction.value?.action_kind) {
    case 'resume_plan': return '继续本周计划'
    case 'review_current_node': return '复习当前知识点'
    case 'practice_targeted_questions': return '做一组针对性练习'
    case 'check_prerequisite': return '先补齐必要基础'
    case 'study_assigned_resource': return '完成指定学习资料'
    case 'ask_for_explanation': return '先听一次讲解'
    default: return ''
  }
})
const actionTargetLabel = computed(() => {
  const action = nextAction.value
  const activeStep = snapshot.value?.active_plan?.current_step
  const currentNode = snapshot.value?.current_node
  if (!action) return ''
  if (action.target.resource_topic) return action.target.resource_topic
  if (activeStep && action.target.step_id === activeStep.step_id && activeStep.topic) return activeStep.topic
  if (currentNode && (!action.target.node_id || currentNode.node_id === action.target.node_id)) return currentNode.name
  return '当前学习内容'
})
const actionReasons = computed(() => {
  const reasons = nextAction.value?.reason ?? []
  return reasons.length ? reasons : ['根据当前学习状态生成']
})
const freshnessMessage = computed(() => {
  if (!snapshot.value?.freshness) return '学习数据暂不可用'
  if (snapshot.value.freshness.missing_sources.length) {
    return `学习数据不完整：缺少 ${snapshot.value.freshness.missing_sources.join('、')}`
  }
  return snapshot.value.freshness.stale ? '学习数据已过期，暂不展示建议' : ''
})

const startNextAction = () => {
  const action = nextAction.value
  if (!action) return

  const query: Record<string, string> = {
    courseId: courseId.value,
    actionKind: action.action_kind,
    source: 'learning_snapshot',
  }
  if (action.target.node_id) query.nodeId = action.target.node_id
  if (action.target.step_id !== null && action.target.step_id !== undefined) query.stepId = String(action.target.step_id)

  void router.push({ path: action.entry, query })
}

const dismissNextAction = () => {
  recommendationDismissed.value = true
}

onMounted(() => { void loadSnapshot() })
</script>

<template>
  <section class="analysis-page" :class="{ 'snapshot-unavailable': snapshotLoading || snapshotUnavailable }">
    <div class="analysis-inner">
      <header class="page-header">
        <div><h1>学情分析</h1><p>综合你的对话、练习、计划与知识掌握情况，持续更新学习画像</p></div>
        <button data-test="refresh-learning-status" class="refresh-button" :class="{ spinning: refreshing }" @click="refresh"><RefreshCw :size="16" :stroke-width="1.5" />{{ refreshing ? '正在更新学习状态' : '刷新学习状态' }}</button>
      </header>

      <div v-if="!snapshotLoading && !snapshotUnavailable" class="summary-grid">
        <article class="summary-panel conclusion-panel">
          <div class="panel-title"><span>当前学习</span><small>来自这次快照</small></div>
          <p v-if="snapshot?.current_node" class="conclusion">当前在学「{{ snapshot.current_node.name }}」。</p>
          <p v-else class="conclusion">这份快照里还没有可以写成结论的个人记录。</p>
          <p v-if="snapshot?.active_plan?.title" class="evidence-box">进行中的计划：{{ snapshot.active_plan.title }}</p>
        </article>
        <article class="summary-panel overview-panel"><div class="panel-title"><span>学习统计</span></div><p class="conclusion">时长、正确率和连续学习天数还没有接到你自己的记录上，所以这里不放示例数字。</p></article>
      </div>

      <section class="next-section snapshot-entry" aria-live="polite">
        <div class="section-heading"><span>当前学习入口</span><small>只展示 1 条真实建议</small></div>
        <div v-if="progressStatus" class="snapshot-status success-status">{{ progressStatus }}</div>
        <div v-if="snapshotLoading" class="snapshot-state" data-test="snapshot-loading">
          <strong>正在读取你的学习状态</strong>
          <span>先不展示旧的推荐，等最新快照返回。</span>
        </div>
        <div v-else-if="snapshotUnavailable" class="snapshot-state warning-state">
          <strong>{{ snapshotError ? '暂时无法生成可靠的下一步建议' : '学习数据不完整' }}</strong>
          <span>{{ snapshotError || freshnessMessage }}</span>
          <div class="snapshot-actions">
            <button data-test="refresh-snapshot" class="primary-correction" @click="refresh">重新读取</button>
            <button class="text-button" @click="router.push('/learning-path')">手动选择学习入口 <ArrowRight :size="14" /></button>
          </div>
        </div>
        <article v-else-if="nextAction" class="next-action-card" data-test="next-action-card">
          <div class="next-action-copy">
            <span class="next-action-label">当前建议（1 条）</span>
            <h2>{{ actionTitle }}</h2>
            <p class="next-action-target">目标：{{ actionTargetLabel }}</p>
            <div class="next-action-reasons">
              <span>为什么是它</span>
              <ul><li v-for="reason in actionReasons.slice(0, 2)" :key="reason">{{ reason }}</li></ul>
            </div>
            <small v-if="nextAction.expected_minutes !== null && nextAction.expected_minutes !== undefined" class="next-action-duration">预计 {{ nextAction.expected_minutes }} 分钟</small>
            <small class="next-action-freshness">数据状态：刚刚更新</small>
          </div>
          <div class="next-action-buttons">
            <button data-test="start-next-action" class="primary-correction" @click="startNextAction">开始学习 <ArrowRight :size="15" /></button>
            <button class="text-button" @click="dismissNextAction">{{ nextAction.dismiss_policy === 'snooze' ? '稍后处理' : '换一个方式' }}</button>
          </div>
        </article>
        <div v-else class="snapshot-state empty-state">
          <strong>暂时没有一条明确的下一步</strong>
          <span>{{ recommendationDismissed ? '这条建议已暂时隐藏，本次不会伪造另一条推荐。' : '当前快照没有命中可执行建议。' }}</span>
          <div class="snapshot-actions">
            <span class="manual-entry-label">手动选择学习入口</span>
            <button class="text-button" @click="router.push('/learning-path')">学习计划 <ArrowRight :size="14" /></button>
            <button class="text-button" @click="router.push('/learning-resource-network')">知识图谱 <ArrowRight :size="14" /></button>
          </div>
        </div>
      </section>

      <section class="analysis-panel detail-panel">
        <div class="panel-title"><span>画像和统计</span></div>
        <p class="conclusion">掌握度分布、诊断标签和学习趋势要来自你自己的记录。现在还没有这些数据，所以这里不放另一名学生的例子。</p>
      </section>
    </div>
  </section>
</template>

<style scoped>
.analysis-page{min-height:100vh;padding:44px 52px 70px}.analysis-inner{max-width:1240px;margin:auto}.page-header{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:34px}.page-header h1{margin:0 0 8px;font-family:var(--font-display);font-size:40px;font-weight:500;letter-spacing:-.04em}.page-header p{margin:0;color:var(--muted);font-size:14px}.refresh-button,.text-button{display:inline-flex;align-items:center;gap:7px;border:0;background:transparent;color:var(--muted);cursor:pointer;font-size:12px}.refresh-button:hover,.text-button:hover{color:var(--ink)}.refresh-button.spinning svg{animation:spin .7s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}.summary-grid,.profile-grid,.trend-grid{display:grid;grid-template-columns:1fr 1.18fr;gap:18px;margin-bottom:18px}.summary-panel,.analysis-panel{border:1px solid var(--line);border-radius:var(--radius-panel);background:rgba(255,254,250,.55)}.summary-panel{padding:24px}.panel-title{display:flex;align-items:center;justify-content:space-between;color:var(--ink);font-size:14px}.panel-title small{display:inline-flex;align-items:center;gap:4px;color:var(--soft-muted);font-size:11px}.conclusion{max-width:480px;margin:28px 0 24px;font-family:var(--font-display);font-size:20px;line-height:1.75;letter-spacing:-.02em}.evidence-box{display:grid;gap:7px;margin-top:18px;padding-top:16px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}.evidence-box small{margin-top:4px;color:var(--soft-muted)}.rotated{transform:rotate(-180deg)}.stat-grid{display:grid;grid-template-columns:repeat(3,1fr);margin-top:25px}.stat-item{display:grid;grid-template-columns:auto 1fr;gap:2px 8px;padding:13px 12px;border:0;border-right:1px solid var(--line);background:transparent;text-align:left;cursor:pointer}.stat-item:nth-child(3n){border-right:0}.stat-item svg{grid-row:span 2;color:var(--sage);margin-top:2px}.stat-item span{color:var(--muted);font-size:11px}.stat-item strong{font-size:20px;font-weight:500}.stat-item small{grid-column:2;color:var(--sage);font-size:11px}.profile-panel,.focus-panel{padding:24px}.profile-body{display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:center;margin-top:23px}.radar-wrap{position:relative;height:245px}.radar{position:absolute;left:50%;top:50%;width:180px;height:180px;transform:translate(-50%,-50%)}.radar-ring,.radar-shape{position:absolute;inset:0;clip-path:polygon(50% 0,93% 25%,93% 75%,50% 100%,7% 75%,7% 25%)}.radar-ring{border:1px solid #d6ded2;background:transparent}.ring-one{inset:26px}.ring-two{inset:52px}.ring-three{inset:78px}.radar-shape{inset:32px;background:rgba(127,146,122,.26);border:1px solid var(--sage)}.radar-label{position:absolute;color:var(--muted);font-size:11px;white-space:nowrap}.radar-label.top{top:0;left:50%;transform:translateX(-50%)}.radar-label.right{right:0;top:27%}.radar-label.bottom-right{right:2px;bottom:21%}.radar-label.bottom-left{left:8px;bottom:21%}.radar-label.left{left:0;top:27%}.radar-label.weak{left:50%;bottom:0;transform:translateX(-50%);color:#b87962}.profile-meta{display:grid;gap:18px}.profile-score{display:flex;align-items:baseline;gap:8px}.profile-score strong{font-family:var(--font-display);font-size:36px;font-weight:500}.profile-score span{color:var(--ink);font-size:13px}.profile-score small{color:var(--soft-muted);font-size:11px}.dimension-list{display:grid;grid-template-columns:1fr 1fr;gap:3px}.dimension-list button{display:flex;justify-content:space-between;padding:8px 9px;border:0;border-radius:7px;background:transparent;color:var(--muted);cursor:pointer;font-size:12px}.dimension-list button.selected,.dimension-list button:hover{background:var(--sage-soft);color:var(--ink)}.dimension-list b{font-weight:500}.focus-list{display:grid;gap:16px;margin-top:22px}.focus-item{display:flex;gap:11px;padding-bottom:15px;border-bottom:1px solid var(--line)}.focus-item:last-child{padding-bottom:0;border-bottom:0}.priority-dot{width:8px;height:8px;flex:0 0 auto;margin-top:6px;border-radius:50%}.priority-dot.clay{background:var(--clay)}.priority-dot.sage{background:#6eb293}.priority-dot.warm{background:#d6b07e}.focus-item strong{font-size:13px;font-weight:500}.focus-item p{margin:4px 0 8px;color:var(--muted);font-size:12px}.focus-item button{display:inline-flex;align-items:center;gap:4px;margin-right:13px;padding:0;border:0;background:transparent;color:var(--muted);cursor:pointer;font-size:11px}.focus-item button:hover{color:var(--ink)}.detail-panel{padding:24px;margin-bottom:18px}.dimension-tabs{display:flex;gap:6px;overflow:auto;margin:21px 0 23px;padding-bottom:3px}.dimension-tabs button{flex:0 0 auto;padding:7px 12px;border:0;border-radius:7px;background:transparent;color:var(--muted);cursor:pointer;font-size:12px}.dimension-tabs button.active{background:var(--sage-soft);color:var(--ink)}.detail-content{max-width:850px}.detail-content h3{margin:0 0 9px;font-family:var(--font-display);font-size:23px;font-weight:500}.detail-content p{margin:0;color:var(--muted);font-size:14px}.detail-content h4{margin:23px 0 8px;font-size:12px;font-weight:500}.detail-content ul{display:grid;gap:6px;margin:0;padding-left:17px;color:var(--muted);font-size:12px}.detail-content li small{margin-left:10px;color:var(--soft-muted)}.impact-line{margin-top:19px;padding-top:15px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}.impact-line span{margin-right:20px;color:var(--ink)}.trend-panel,.mastery-panel{padding:24px}.segmented{display:flex;gap:3px;padding:3px;border:1px solid var(--line);border-radius:8px}.segmented button{padding:4px 8px;border:0;border-radius:5px;background:transparent;color:var(--muted);cursor:pointer;font-size:11px}.segmented button.active{background:var(--sage-soft);color:var(--ink)}.chart{position:relative;height:190px;margin-top:23px}.chart-grid{position:absolute;inset:0;display:grid;align-content:space-between}.chart-grid i{display:block;border-top:1px dashed #e6e1d8}.line{position:absolute;height:2px;border-radius:2px;transform-origin:left center}.line-a{left:1%;top:70%;width:95%;background:var(--sage);transform:rotate(-4deg);box-shadow:115px -34px 0 -0.3px var(--sage),235px 5px 0 -0.3px var(--sage),350px -44px 0 -0.3px var(--sage)}.line-b{left:1%;top:76%;width:95%;background:var(--clay);transform:rotate(-9deg);box-shadow:110px 12px 0 -0.3px var(--clay),230px -20px 0 -0.3px var(--clay),355px -56px 0 -0.3px var(--clay)}.chart-axis{position:absolute;bottom:-21px;left:0;right:0;display:flex;justify-content:space-between;color:var(--soft-muted);font-size:10px}.legend{display:flex;gap:18px;margin-top:36px;color:var(--muted);font-size:11px}.legend span{display:inline-flex;align-items:center;gap:5px}.legend i{width:7px;height:7px;border-radius:50%}.sage-dot{background:var(--sage)}.clay-dot{background:var(--clay)}.ink-dot{background:var(--ink)}.mastery-row{display:grid;grid-template-columns:52px 1fr 20px;align-items:center;gap:10px;margin:26px 0 0;color:var(--muted);font-size:12px}.mastery-row div{height:5px;background:#eeeae2;border-radius:10px}.mastery-row i{display:block;height:100%;border-radius:10px;background:var(--sage)}.mastery-row i.mid{background:#a9c2ae}.mastery-row i.weak{background:var(--clay)}.mastery-row b{color:var(--ink);font-weight:500}.weak-topics{display:grid;gap:7px;margin-top:27px;padding-top:16px;border-top:1px solid var(--line);color:var(--muted);font-size:11px}.weak-topics button{display:flex;justify-content:space-between;border:0;background:transparent;color:var(--ink);cursor:pointer;text-align:left;font-size:12px}.weak-topics b{color:var(--clay);font-weight:500}.next-section{margin-top:30px}.section-heading{display:flex;gap:15px;align-items:baseline;margin-bottom:13px}.section-heading span{font-size:14px}.section-heading small{color:var(--soft-muted);font-size:11px}.next-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.next-card{position:relative;display:grid;gap:7px;min-height:143px;padding:18px;border:1px solid var(--line);border-radius:12px;background:transparent;text-align:left;cursor:pointer}.next-card:hover{background:var(--surface-muted)}.next-card span{color:var(--muted);font-size:11px}.next-card strong{font-family:var(--font-display);font-size:17px;font-weight:500}.next-card small{color:var(--muted);font-size:11px}.next-card>svg{position:absolute;right:17px;bottom:17px;color:var(--muted)}.drawer-backdrop{position:fixed;inset:0;z-index:5;background:rgba(36,35,31,.14)}.diagnosis-drawer{position:absolute;top:0;right:0;bottom:0;width:min(390px,90vw);padding:30px 25px;background:var(--page);box-shadow:-12px 0 30px rgba(80,65,48,.08)}.drawer-header{display:flex;justify-content:space-between;align-items:center}.drawer-header h2{margin:0;font-family:var(--font-display);font-size:24px;font-weight:500}.drawer-header button{border:0;background:transparent;cursor:pointer}.drawer-tabs{display:flex;gap:3px;margin:26px 0 18px;overflow:auto}.drawer-tabs button{padding:7px 9px;border:0;border-radius:7px;background:transparent;color:var(--muted);cursor:pointer;white-space:nowrap;font-size:11px}.drawer-tabs button.active{background:var(--sage-soft);color:var(--ink)}.drawer-item{padding:17px 0;border-top:1px solid var(--line)}.drawer-item b{font-size:13px;font-weight:500}.drawer-item p{margin:6px 0 0;color:var(--muted);font-size:12px}@media(max-width:1000px){.analysis-page{padding:30px 24px}.summary-grid,.profile-grid,.trend-grid{grid-template-columns:1fr}.next-grid{grid-template-columns:1fr}.page-header{align-items:flex-start;gap:15px;flex-direction:column}.profile-body{grid-template-columns:1fr 1fr}}@media(max-width:620px){.analysis-page{padding:24px 16px}.stat-grid{grid-template-columns:1fr 1fr}.stat-item:nth-child(3n){border-right:1px solid var(--line)}.stat-item:nth-child(2n){border-right:0}.profile-body{grid-template-columns:1fr}.dimension-tabs{margin-bottom:15px}}
.confidence-row{display:flex;align-items:center;gap:16px;margin-top:18px;padding-top:14px;border-top:1px solid var(--line);color:var(--soft-muted);font-size:11px}.confirmed-mark{color:var(--sage)}.heatmap-title{display:flex;gap:8px;align-items:baseline;margin-top:27px;color:var(--ink);font-size:12px}.heatmap-title small{color:var(--soft-muted);font-size:10px}.heatmap{display:grid;grid-template-columns:repeat(14,1fr);gap:4px;margin-top:11px}.heatmap i{aspect-ratio:1;border-radius:3px;background:#eeeae2}.heatmap .level-1{background:#dce8da}.heatmap .level-2{background:#bed2bc}.heatmap .level-3{background:#95b094}.heatmap .level-4{background:#6f906c}.correction-backdrop{position:fixed;inset:0;z-index:6;display:grid;place-items:center;background:rgba(36,35,31,.14)}.correction-modal{position:relative;width:min(450px,90vw);padding:26px;border:1px solid var(--line);border-radius:15px;background:var(--page);box-shadow:0 18px 50px rgba(70,58,43,.1)}.correction-modal h2{margin:0 0 8px;font-family:var(--font-display);font-size:23px;font-weight:500}.correction-modal p{margin:0;color:var(--muted);font-size:12px}.correction-modal textarea{width:100%;min-height:110px;margin:20px 0;padding:12px;border:1px solid var(--line);border-radius:8px;background:transparent;color:var(--ink);font:inherit;font-size:12px;resize:vertical}.correction-modal footer{display:flex;justify-content:flex-end;gap:10px}.close-correction{position:absolute;top:17px;right:17px;border:0;background:transparent;color:var(--muted);cursor:pointer}.primary-correction{padding:8px 13px;border:1px solid var(--sage);border-radius:8px;background:var(--sage);color:#fff;cursor:pointer;font-size:12px}
.snapshot-entry{padding:20px 0 0;border-top:1px solid var(--line)}.snapshot-state,.next-action-card{border:1px solid var(--line);border-radius:12px;background:rgba(255,254,250,.58)}.snapshot-state{display:grid;gap:8px;padding:22px;color:var(--muted);font-size:12px}.snapshot-state strong{color:var(--ink);font-size:15px;font-weight:500}.snapshot-state span{line-height:1.6}.warning-state{border-color:#dfcfc3;background:#fffaf6}.success-status{margin:-4px 0 13px;color:var(--sage);font-size:12px}.snapshot-actions{display:flex;align-items:center;flex-wrap:wrap;gap:13px;margin-top:5px}.manual-entry-label{color:var(--ink);font-size:12px}.next-action-card{display:flex;justify-content:space-between;gap:28px;padding:24px}.next-action-copy{display:grid;gap:8px;min-width:0}.next-action-label{color:var(--muted);font-size:11px}.next-action-card h2{margin:0;font-family:var(--font-display);font-size:24px;font-weight:500}.next-action-target{margin:0;color:var(--ink);font-size:14px}.next-action-reasons{display:grid;gap:6px;margin-top:5px;color:var(--muted);font-size:12px}.next-action-reasons>span{color:var(--ink);font-size:11px}.next-action-reasons ul{display:grid;gap:4px;margin:0;padding-left:16px}.next-action-duration,.next-action-freshness{color:var(--muted);font-size:11px}.next-action-freshness{color:var(--sage)}.next-action-buttons{display:flex;flex:0 0 auto;align-items:flex-end;flex-direction:column;justify-content:center;gap:13px}.primary-correction{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:10px 14px;border:1px solid var(--sage);border-radius:8px;background:var(--sage);color:#fff;cursor:pointer;font-size:12px}.primary-correction:hover{background:#6f8a6b}@media(max-width:620px){.next-action-card{align-items:stretch;flex-direction:column;gap:18px;padding:18px}.next-action-buttons{align-items:flex-start}}
.snapshot-unavailable .summary-grid,.snapshot-unavailable .profile-grid,.snapshot-unavailable .detail-panel,.snapshot-unavailable .trend-grid{display:none}.snapshot-unavailable .snapshot-entry{margin-top:0}
</style>
