<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, BarChart3, Check, ChevronDown, CircleHelp, Clock3, RefreshCw, Target, TrendingUp, X } from '@lucide/vue'
import { getLearningSnapshot, type LearningNextAction, type LearningSnapshot } from '@/api/learningSnapshot'
import { resolveErrorMessage } from '@/utils/request'

const router = useRouter()
const route = useRoute()
const snapshot = ref<LearningSnapshot | null>(null)
const snapshotLoading = ref(true)
const snapshotError = ref('')
const refreshing = ref(false)
const recommendationDismissed = ref(false)
const evidenceOpen = ref(false)
const diagnosesOpen = ref(false)
const correctionOpen = ref(false)
const correctionSent = ref(false)
const selectedDimension = ref('知识基础')
const range = ref('近7天')
const courseId = computed(() => {
  const value = route.query.courseId
  return typeof value === 'string' && value.trim() ? value : 'ai_intro'
})
const progressStatus = computed(() => {
  const value = route.query.progressStatus
  return typeof value === 'string' ? value : ''
})
const dimensions = [
  { label: '知识基础', score: 72, text: '掌握了机器学习基础，深度学习正在形成体系。', status: '已确认' },
  { label: '学习方式', score: 78, text: '你更容易通过结构图、示例和亲手实践理解知识。', status: '已确认' },
  { label: '学习目标', score: 86, text: '目标明确，正在向 AI 工程方向持续收敛。', status: '已确认' },
  { label: '薄弱环节', score: 54, text: '矩阵运算与反向传播仍是当前主要阻塞点。', status: '分析中' },
  { label: '学习节奏', score: 68, text: '晚间学习完成率更高，当前节奏基本稳定。', status: '已确认' },
  { label: '兴趣方向', score: 82, text: '对深度学习、NLP 与可视化方向保持持续兴趣。', status: '已确认' },
]
const selected = computed(() => dimensions.find(item => item.label === selectedDimension.value) || dimensions[0]!)
const statItems = [
  { label: '学习时长', value: '8.5h', change: '↑ 1.2h', icon: Clock3, path: '#trend' },
  { label: '完成任务', value: '12/15', change: '↑ 3项', icon: Check, path: '/learning-path' },
  { label: '练习正确率', value: '76%', change: '↑ 6%', icon: Target, path: '/exercise' },
  { label: '掌握知识点', value: '23个', change: '↑ 2个', icon: TrendingUp, path: '/learning-resource-network' },
  { label: '连续学习', value: '6天', change: '最长 9天', icon: BarChart3, path: '#trend' },
  { label: '画像完整度', value: '83%', change: '已覆盖 5/6 维', icon: CircleHelp, path: '#profile' },
]

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
const go = (path: string) => path.startsWith('#') ? document.querySelector(path)?.scrollIntoView({ behavior: 'smooth' }) : router.push(path)
const heatmap = [1,2,2,3,4,3,1,0,2,3,4,4,2,1,0,1,3,4,3,2,1,0,1,2,4,4,3,2,1,0,1,2,3,4,3,2,1,0,1,3,4,3,2,1]

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
          <div class="panel-title"><span>AI 学情总结</span><small>更新于 14:32</small></div>
          <p class="conclusion">你是一名目标明确、偏视觉实践型的学习者。近期深度学习基础提升明显，但线性代数仍是当前主要阻碍。</p>
          <button class="text-button" @click="evidenceOpen = !evidenceOpen">{{ evidenceOpen ? '收起分析依据' : '查看分析依据' }} <ChevronDown :size="15" :class="{ rotated: evidenceOpen }" /></button>
          <div v-if="evidenceOpen" class="evidence-box"><div v-for="item in ['最近 7 天完成 12 个任务','Transformer 掌握度从 61% 升至 73%','矩阵运算相关练习正确率仅 48%','4 次主动请求使用图示或代码案例']" :key="item">· {{ item }}</div><small>数据来源：计划 · 练习 · 图谱 · 对话</small></div>
        </article>
        <article class="summary-panel overview-panel"><div class="panel-title"><span>本周学习概览</span><small>较上周</small></div><div class="stat-grid"><button v-for="item in statItems" :key="item.label" class="stat-item" @click="go(item.path)"><component :is="item.icon" :size="16" :stroke-width="1.35" /><span>{{ item.label }}</span><strong>{{ item.value }}</strong><small>{{ item.change }}</small></button></div></article>
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

      <div id="profile" class="profile-grid">
        <article class="analysis-panel profile-panel"><div class="panel-title"><span>我的学习画像</span><small>基于 26 次有效学习行为</small></div><div class="profile-body"><div class="radar-wrap"><div class="radar"><span class="radar-ring ring-one" /><span class="radar-ring ring-two" /><span class="radar-ring ring-three" /><div class="radar-shape" /></div><span class="radar-label top">知识基础 72</span><span class="radar-label right">学习目标 86</span><span class="radar-label bottom-right">学习节奏 68</span><span class="radar-label bottom-left">兴趣方向 82</span><span class="radar-label left">认知风格 78</span><span class="radar-label weak">薄弱点 54</span></div><div class="profile-meta"><div class="profile-score"><strong>83%</strong><span>画像完整度</span><small>已确认 5/6 维</small></div><div class="dimension-list"><button v-for="item in dimensions" :key="item.label" :class="{ selected: selectedDimension === item.label }" @click="selectedDimension = item.label"><span>{{ item.label }}</span><b>{{ item.score }}</b></button></div></div></div></article>
        <article class="analysis-panel focus-panel"><div class="panel-title"><span>当前最值得关注</span><button class="text-button" @click="diagnosesOpen = true">查看全部诊断 <ArrowRight :size="14" /></button></div><div class="focus-list"><div class="focus-item"><span class="priority-dot clay" /><div><strong>线性代数基础薄弱</strong><p>已连续影响矩阵运算、反向传播等 3 个知识点</p><div><button @click="router.push('/learning-resource-network')">查看知识图谱</button><button @click="router.push('/exercise')">专项练习</button></div></div></div><div class="focus-item"><span class="priority-dot sage" /><div><strong>Transformer 正在进步</strong><p>最近掌握度提升 12%，建议继续巩固</p><button @click="router.push('/question-nav-chat')">继续学习 <ArrowRight :size="13" /></button></div></div><div class="focus-item"><span class="priority-dot warm" /><div><strong>本周计划有 3 项延期</strong><p>任务节奏出现轻微波动</p><button @click="router.push('/learning-path')">调整学习计划 <ArrowRight :size="13" /></button></div></div></div></article>
      </div>

      <section class="analysis-panel detail-panel"><div class="panel-title"><span>画像详情</span><small>{{ selected.status }} <Check v-if="selected.status === '已确认'" :size="14" /></small></div><div class="dimension-tabs"><button v-for="item in dimensions" :key="item.label" :class="{ active: selectedDimension === item.label }" @click="selectedDimension = item.label">{{ item.label }}</button></div><div class="detail-content"><h3>{{ selected.label }}：{{ selected.score >= 75 ? '视觉实践型' : '正在形成' }}</h3><p>{{ selected.text }}</p><h4>判断依据</h4><ul><li>你多次主动请求生成结构图和可视化解释 <small>来源：对话</small></li><li>带代码示例的内容完成率比纯理论内容高 18% <small>来源：资源</small></li><li>最近 4 次练习中，实践题正确率高于概念题 <small>来源：练习</small></li></ul><div class="impact-line"><span>对系统的影响</span>资源优先推荐图解与案例 · 对话优先提供示例 · 计划增加实践任务</div><div class="confidence-row"><span>可信度：{{ selected.status === '已确认' ? '高' : '中' }}</span><button v-if="selected.status !== '已确认'" class="text-button" @click="correctionOpen = true">这不太准确？提交修正</button><span v-else class="confirmed-mark">✓ 已由你的学习行为确认</span></div></div></section>

      <div id="trend" class="trend-grid"><article class="analysis-panel trend-panel"><div class="panel-title"><span>学习趋势</span><div class="segmented"><button v-for="item in ['近7天','近30天','本学期']" :key="item" :class="{ active: range === item }" @click="range = item">{{ item }}</button></div></div><div class="chart"><div class="chart-grid"><i /><i /><i /><i /><i /></div><div class="line line-a" /><div class="line line-b" /><div class="chart-axis"><span>7/08</span><span>7/10</span><span>7/12</span><span>7/14</span></div></div><div class="legend"><span><i class="sage-dot" />平均掌握度</span><span><i class="clay-dot" />练习正确率</span><span><i class="ink-dot" />学习时长</span></div><div class="heatmap-title">学习热力图 <small>近 6 周</small></div><div class="heatmap"><i v-for="(level,index) in heatmap" :key="index" :class="`level-${level}`" :title="`${level} 次学习`" /></div></article><article class="analysis-panel mastery-panel"><div class="panel-title"><span>知识掌握分布</span><button class="text-button" @click="router.push('/learning-resource-network')">前往知识图谱 <ArrowRight :size="14" /></button></div><div class="mastery-row"><span>已掌握</span><div><i style="width: 64%" /></div><b>8</b></div><div class="mastery-row"><span>学习中</span><div><i class="mid" style="width: 80%" /></div><b>10</b></div><div class="mastery-row"><span>薄弱</span><div><i class="weak" style="width: 42%" /></div><b>5</b></div><div class="weak-topics"><span>最薄弱知识点</span><button @click="router.push('/learning-resource-network')">矩阵运算 <b>42%</b></button><button @click="router.push('/learning-resource-network')">反向传播 <b>48%</b></button></div></article></div>

    </div>
    <div v-if="diagnosesOpen" class="drawer-backdrop" @click.self="diagnosesOpen = false"><aside class="diagnosis-drawer"><div class="drawer-header"><h2>全部学情诊断</h2><button @click="diagnosesOpen = false"><X :size="19" /></button></div><div class="drawer-tabs"><button class="active">全部</button><button>需关注</button><button>正在进步</button><button>计划风险</button></div><div class="drawer-item"><b>线性代数基础薄弱</b><p>近 3 次练习正确率 48%，影响 3 个后续知识点。</p></div><div class="drawer-item"><b>Transformer 掌握度提升</b><p>知识图谱 mastery 从 61% 上升到 73%。</p></div><div class="drawer-item"><b>晚间学习完成率更高</b><p>最近一周 4 次晚间学习均完成了主要任务。</p></div></aside></div>
    <div v-if="correctionOpen" class="correction-backdrop" @click.self="correctionOpen = false"><section class="correction-modal"><button class="close-correction" @click="correctionOpen = false"><X :size="18" /></button><h2>修正学习画像</h2><p>告诉我们哪里不准确，后续分析会优先参考你的反馈。</p><textarea placeholder="例如：我其实更喜欢先阅读理论，再做练习" /><footer><button class="text-button" @click="correctionOpen = false">取消</button><button class="primary-correction" @click="correctionSent = true; correctionOpen = false">{{ correctionSent ? '已提交' : '提交反馈' }}</button></footer></section></div>
  </section>
</template>

<style scoped>
.analysis-page{min-height:100vh;padding:44px 52px 70px}.analysis-inner{max-width:1240px;margin:auto}.page-header{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:34px}.page-header h1{margin:0 0 8px;font-family:var(--font-display);font-size:40px;font-weight:500;letter-spacing:-.04em}.page-header p{margin:0;color:var(--muted);font-size:14px}.refresh-button,.text-button{display:inline-flex;align-items:center;gap:7px;border:0;background:transparent;color:var(--muted);cursor:pointer;font-size:12px}.refresh-button:hover,.text-button:hover{color:var(--ink)}.refresh-button.spinning svg{animation:spin .7s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}.summary-grid,.profile-grid,.trend-grid{display:grid;grid-template-columns:1fr 1.18fr;gap:18px;margin-bottom:18px}.summary-panel,.analysis-panel{border:1px solid var(--line);border-radius:var(--radius-panel);background:rgba(255,254,250,.55)}.summary-panel{padding:24px}.panel-title{display:flex;align-items:center;justify-content:space-between;color:var(--ink);font-size:14px}.panel-title small{display:inline-flex;align-items:center;gap:4px;color:var(--soft-muted);font-size:11px}.conclusion{max-width:480px;margin:28px 0 24px;font-family:var(--font-display);font-size:20px;line-height:1.75;letter-spacing:-.02em}.evidence-box{display:grid;gap:7px;margin-top:18px;padding-top:16px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}.evidence-box small{margin-top:4px;color:var(--soft-muted)}.rotated{transform:rotate(-180deg)}.stat-grid{display:grid;grid-template-columns:repeat(3,1fr);margin-top:25px}.stat-item{display:grid;grid-template-columns:auto 1fr;gap:2px 8px;padding:13px 12px;border:0;border-right:1px solid var(--line);background:transparent;text-align:left;cursor:pointer}.stat-item:nth-child(3n){border-right:0}.stat-item svg{grid-row:span 2;color:var(--sage);margin-top:2px}.stat-item span{color:var(--muted);font-size:11px}.stat-item strong{font-size:20px;font-weight:500}.stat-item small{grid-column:2;color:var(--sage);font-size:11px}.profile-panel,.focus-panel{padding:24px}.profile-body{display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:center;margin-top:23px}.radar-wrap{position:relative;height:245px}.radar{position:absolute;left:50%;top:50%;width:180px;height:180px;transform:translate(-50%,-50%)}.radar-ring,.radar-shape{position:absolute;inset:0;clip-path:polygon(50% 0,93% 25%,93% 75%,50% 100%,7% 75%,7% 25%)}.radar-ring{border:1px solid #d6ded2;background:transparent}.ring-one{inset:26px}.ring-two{inset:52px}.ring-three{inset:78px}.radar-shape{inset:32px;background:rgba(127,146,122,.26);border:1px solid var(--sage)}.radar-label{position:absolute;color:var(--muted);font-size:11px;white-space:nowrap}.radar-label.top{top:0;left:50%;transform:translateX(-50%)}.radar-label.right{right:0;top:27%}.radar-label.bottom-right{right:2px;bottom:21%}.radar-label.bottom-left{left:8px;bottom:21%}.radar-label.left{left:0;top:27%}.radar-label.weak{left:50%;bottom:0;transform:translateX(-50%);color:#b87962}.profile-meta{display:grid;gap:18px}.profile-score{display:flex;align-items:baseline;gap:8px}.profile-score strong{font-family:var(--font-display);font-size:36px;font-weight:500}.profile-score span{color:var(--ink);font-size:13px}.profile-score small{color:var(--soft-muted);font-size:11px}.dimension-list{display:grid;grid-template-columns:1fr 1fr;gap:3px}.dimension-list button{display:flex;justify-content:space-between;padding:8px 9px;border:0;border-radius:7px;background:transparent;color:var(--muted);cursor:pointer;font-size:12px}.dimension-list button.selected,.dimension-list button:hover{background:var(--sage-soft);color:var(--ink)}.dimension-list b{font-weight:500}.focus-list{display:grid;gap:16px;margin-top:22px}.focus-item{display:flex;gap:11px;padding-bottom:15px;border-bottom:1px solid var(--line)}.focus-item:last-child{padding-bottom:0;border-bottom:0}.priority-dot{width:8px;height:8px;flex:0 0 auto;margin-top:6px;border-radius:50%}.priority-dot.clay{background:var(--clay)}.priority-dot.sage{background:#6eb293}.priority-dot.warm{background:#d6b07e}.focus-item strong{font-size:13px;font-weight:500}.focus-item p{margin:4px 0 8px;color:var(--muted);font-size:12px}.focus-item button{display:inline-flex;align-items:center;gap:4px;margin-right:13px;padding:0;border:0;background:transparent;color:var(--muted);cursor:pointer;font-size:11px}.focus-item button:hover{color:var(--ink)}.detail-panel{padding:24px;margin-bottom:18px}.dimension-tabs{display:flex;gap:6px;overflow:auto;margin:21px 0 23px;padding-bottom:3px}.dimension-tabs button{flex:0 0 auto;padding:7px 12px;border:0;border-radius:7px;background:transparent;color:var(--muted);cursor:pointer;font-size:12px}.dimension-tabs button.active{background:var(--sage-soft);color:var(--ink)}.detail-content{max-width:850px}.detail-content h3{margin:0 0 9px;font-family:var(--font-display);font-size:23px;font-weight:500}.detail-content p{margin:0;color:var(--muted);font-size:14px}.detail-content h4{margin:23px 0 8px;font-size:12px;font-weight:500}.detail-content ul{display:grid;gap:6px;margin:0;padding-left:17px;color:var(--muted);font-size:12px}.detail-content li small{margin-left:10px;color:var(--soft-muted)}.impact-line{margin-top:19px;padding-top:15px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}.impact-line span{margin-right:20px;color:var(--ink)}.trend-panel,.mastery-panel{padding:24px}.segmented{display:flex;gap:3px;padding:3px;border:1px solid var(--line);border-radius:8px}.segmented button{padding:4px 8px;border:0;border-radius:5px;background:transparent;color:var(--muted);cursor:pointer;font-size:11px}.segmented button.active{background:var(--sage-soft);color:var(--ink)}.chart{position:relative;height:190px;margin-top:23px}.chart-grid{position:absolute;inset:0;display:grid;align-content:space-between}.chart-grid i{display:block;border-top:1px dashed #e6e1d8}.line{position:absolute;height:2px;border-radius:2px;transform-origin:left center}.line-a{left:1%;top:70%;width:95%;background:var(--sage);transform:rotate(-4deg);box-shadow:115px -34px 0 -0.3px var(--sage),235px 5px 0 -0.3px var(--sage),350px -44px 0 -0.3px var(--sage)}.line-b{left:1%;top:76%;width:95%;background:var(--clay);transform:rotate(-9deg);box-shadow:110px 12px 0 -0.3px var(--clay),230px -20px 0 -0.3px var(--clay),355px -56px 0 -0.3px var(--clay)}.chart-axis{position:absolute;bottom:-21px;left:0;right:0;display:flex;justify-content:space-between;color:var(--soft-muted);font-size:10px}.legend{display:flex;gap:18px;margin-top:36px;color:var(--muted);font-size:11px}.legend span{display:inline-flex;align-items:center;gap:5px}.legend i{width:7px;height:7px;border-radius:50%}.sage-dot{background:var(--sage)}.clay-dot{background:var(--clay)}.ink-dot{background:var(--ink)}.mastery-row{display:grid;grid-template-columns:52px 1fr 20px;align-items:center;gap:10px;margin:26px 0 0;color:var(--muted);font-size:12px}.mastery-row div{height:5px;background:#eeeae2;border-radius:10px}.mastery-row i{display:block;height:100%;border-radius:10px;background:var(--sage)}.mastery-row i.mid{background:#a9c2ae}.mastery-row i.weak{background:var(--clay)}.mastery-row b{color:var(--ink);font-weight:500}.weak-topics{display:grid;gap:7px;margin-top:27px;padding-top:16px;border-top:1px solid var(--line);color:var(--muted);font-size:11px}.weak-topics button{display:flex;justify-content:space-between;border:0;background:transparent;color:var(--ink);cursor:pointer;text-align:left;font-size:12px}.weak-topics b{color:var(--clay);font-weight:500}.next-section{margin-top:30px}.section-heading{display:flex;gap:15px;align-items:baseline;margin-bottom:13px}.section-heading span{font-size:14px}.section-heading small{color:var(--soft-muted);font-size:11px}.next-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.next-card{position:relative;display:grid;gap:7px;min-height:143px;padding:18px;border:1px solid var(--line);border-radius:12px;background:transparent;text-align:left;cursor:pointer}.next-card:hover{background:var(--surface-muted)}.next-card span{color:var(--muted);font-size:11px}.next-card strong{font-family:var(--font-display);font-size:17px;font-weight:500}.next-card small{color:var(--muted);font-size:11px}.next-card>svg{position:absolute;right:17px;bottom:17px;color:var(--muted)}.drawer-backdrop{position:fixed;inset:0;z-index:5;background:rgba(36,35,31,.14)}.diagnosis-drawer{position:absolute;top:0;right:0;bottom:0;width:min(390px,90vw);padding:30px 25px;background:var(--page);box-shadow:-12px 0 30px rgba(80,65,48,.08)}.drawer-header{display:flex;justify-content:space-between;align-items:center}.drawer-header h2{margin:0;font-family:var(--font-display);font-size:24px;font-weight:500}.drawer-header button{border:0;background:transparent;cursor:pointer}.drawer-tabs{display:flex;gap:3px;margin:26px 0 18px;overflow:auto}.drawer-tabs button{padding:7px 9px;border:0;border-radius:7px;background:transparent;color:var(--muted);cursor:pointer;white-space:nowrap;font-size:11px}.drawer-tabs button.active{background:var(--sage-soft);color:var(--ink)}.drawer-item{padding:17px 0;border-top:1px solid var(--line)}.drawer-item b{font-size:13px;font-weight:500}.drawer-item p{margin:6px 0 0;color:var(--muted);font-size:12px}@media(max-width:1000px){.analysis-page{padding:30px 24px}.summary-grid,.profile-grid,.trend-grid{grid-template-columns:1fr}.next-grid{grid-template-columns:1fr}.page-header{align-items:flex-start;gap:15px;flex-direction:column}.profile-body{grid-template-columns:1fr 1fr}}@media(max-width:620px){.analysis-page{padding:24px 16px}.stat-grid{grid-template-columns:1fr 1fr}.stat-item:nth-child(3n){border-right:1px solid var(--line)}.stat-item:nth-child(2n){border-right:0}.profile-body{grid-template-columns:1fr}.dimension-tabs{margin-bottom:15px}}
.confidence-row{display:flex;align-items:center;gap:16px;margin-top:18px;padding-top:14px;border-top:1px solid var(--line);color:var(--soft-muted);font-size:11px}.confirmed-mark{color:var(--sage)}.heatmap-title{display:flex;gap:8px;align-items:baseline;margin-top:27px;color:var(--ink);font-size:12px}.heatmap-title small{color:var(--soft-muted);font-size:10px}.heatmap{display:grid;grid-template-columns:repeat(14,1fr);gap:4px;margin-top:11px}.heatmap i{aspect-ratio:1;border-radius:3px;background:#eeeae2}.heatmap .level-1{background:#dce8da}.heatmap .level-2{background:#bed2bc}.heatmap .level-3{background:#95b094}.heatmap .level-4{background:#6f906c}.correction-backdrop{position:fixed;inset:0;z-index:6;display:grid;place-items:center;background:rgba(36,35,31,.14)}.correction-modal{position:relative;width:min(450px,90vw);padding:26px;border:1px solid var(--line);border-radius:15px;background:var(--page);box-shadow:0 18px 50px rgba(70,58,43,.1)}.correction-modal h2{margin:0 0 8px;font-family:var(--font-display);font-size:23px;font-weight:500}.correction-modal p{margin:0;color:var(--muted);font-size:12px}.correction-modal textarea{width:100%;min-height:110px;margin:20px 0;padding:12px;border:1px solid var(--line);border-radius:8px;background:transparent;color:var(--ink);font:inherit;font-size:12px;resize:vertical}.correction-modal footer{display:flex;justify-content:flex-end;gap:10px}.close-correction{position:absolute;top:17px;right:17px;border:0;background:transparent;color:var(--muted);cursor:pointer}.primary-correction{padding:8px 13px;border:1px solid var(--sage);border-radius:8px;background:var(--sage);color:#fff;cursor:pointer;font-size:12px}
.snapshot-entry{padding:20px 0 0;border-top:1px solid var(--line)}.snapshot-state,.next-action-card{border:1px solid var(--line);border-radius:12px;background:rgba(255,254,250,.58)}.snapshot-state{display:grid;gap:8px;padding:22px;color:var(--muted);font-size:12px}.snapshot-state strong{color:var(--ink);font-size:15px;font-weight:500}.snapshot-state span{line-height:1.6}.warning-state{border-color:#dfcfc3;background:#fffaf6}.success-status{margin:-4px 0 13px;color:var(--sage);font-size:12px}.snapshot-actions{display:flex;align-items:center;flex-wrap:wrap;gap:13px;margin-top:5px}.manual-entry-label{color:var(--ink);font-size:12px}.next-action-card{display:flex;justify-content:space-between;gap:28px;padding:24px}.next-action-copy{display:grid;gap:8px;min-width:0}.next-action-label{color:var(--muted);font-size:11px}.next-action-card h2{margin:0;font-family:var(--font-display);font-size:24px;font-weight:500}.next-action-target{margin:0;color:var(--ink);font-size:14px}.next-action-reasons{display:grid;gap:6px;margin-top:5px;color:var(--muted);font-size:12px}.next-action-reasons>span{color:var(--ink);font-size:11px}.next-action-reasons ul{display:grid;gap:4px;margin:0;padding-left:16px}.next-action-duration,.next-action-freshness{color:var(--muted);font-size:11px}.next-action-freshness{color:var(--sage)}.next-action-buttons{display:flex;flex:0 0 auto;align-items:flex-end;flex-direction:column;justify-content:center;gap:13px}.primary-correction{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:10px 14px;border:1px solid var(--sage);border-radius:8px;background:var(--sage);color:#fff;cursor:pointer;font-size:12px}.primary-correction:hover{background:#6f8a6b}@media(max-width:620px){.next-action-card{align-items:stretch;flex-direction:column;gap:18px;padding:18px}.next-action-buttons{align-items:flex-start}}
.snapshot-unavailable .summary-grid,.snapshot-unavailable .profile-grid,.snapshot-unavailable .detail-panel,.snapshot-unavailable .trend-grid{display:none}.snapshot-unavailable .snapshot-entry{margin-top:0}
</style>
