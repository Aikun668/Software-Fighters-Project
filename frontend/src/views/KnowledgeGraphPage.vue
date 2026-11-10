<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getLearningMap, decideSuggestion, getContinuation, type LearningMap, type LearningSource } from '@/api/learningMap'
import { setLearningDraft } from '@/utils/learningDraft'
import { resolveErrorMessage } from '@/utils/request'
const router = useRouter()
const tab = ref<'map' | 'events' | 'suggestions'>('map')
const actionError = ref(''), continuing = ref(false), deciding = ref('')
let active = true, continuationRequest = 0
onBeforeUnmount(() => { active = false; continuationRequest++ })
const eventLabel = (type: string) => ({goal:'学习目标',question:'提出问题',practice_request:'练习请求',practice_self_report:'练习自述（未验证）'}[type] ?? type)
const graph = ref<LearningMap>({ nodes: [], edges: [] })
const loading = ref(false), error = ref(''), search = ref(''), selected = ref(''), local = ref(false), zoom = ref(1)
const positions = ref<Record<string, { x: number; y: number }>>({})
const current = computed(() => graph.value.nodes.find(n => n.id === selected.value))
const connected = computed(() => new Set(graph.value.edges.filter(e => e.source === selected.value || e.target === selected.value).flatMap(e => [e.source, e.target])))
const visibleNodes = computed(() => graph.value.nodes.filter(n => (!local.value || n.id === selected.value || connected.value.has(n.id)) && n.title.toLowerCase().includes(search.value.toLowerCase())))
const visibleEdges = computed(() => { const ids = new Set(visibleNodes.value.map(n => n.id)); return graph.value.edges.filter(e => ids.has(e.source) && ids.has(e.target)) })
const relations = computed(() => graph.value.edges.filter(e => e.source === selected.value || e.target === selected.value))
const canvasHeight = computed(() => Math.max(560, Math.ceil(visibleNodes.value.length / 5) * 110 + 60))
const relationLabel = (relation: string) => ({ depends_on: '需要先学', prerequisite: '需要先学', extends: '扩展自', related: '明确关联', user_confirmed: '你确认的探索关联（非事实依赖）' }[relation] ?? relation)
const title = (id: string) => graph.value.nodes.find(n => n.id === id)?.title ?? id
const point = (id: string) => positions.value[id] ?? { x: 450, y: 280 }
async function load() {
  continuationRequest++; continuing.value = false
  loading.value = true; error.value = ''
  try {
    const result = await getLearningMap()
    if (result.meta?.unavailable) throw new Error('记忆状态暂不可用，为保护已忘记的内容，地图暂不展示。请稍后重试。')
    graph.value = result
    if (!result.nodes.some(n => n.id === selected.value)) { selected.value = ''; local.value = false }

  } catch (e) { error.value = resolveErrorMessage(e); graph.value = { nodes: [], edges: [] }; selected.value = ''; local.value = false }
  finally { loading.value = false }
}
function openSource(source: LearningSource) { void router.push({ path: '/question-nav-chat', query: { conversationId: String(source.conversationId), sourceMessageId: String(source.messageId) } }) }
async function continueLearning() {
  if (!current.value || continuing.value) return
  const id = current.value.id, request = ++continuationRequest
  continuing.value = true; actionError.value = ''
  try {
    const result = await getContinuation(id)
    if (!active || request !== continuationRequest || selected.value !== id) return
    if (!result.draft?.trim()) throw new Error('当前没有可用的节点上下文，请刷新地图。')
    const handle = setLearningDraft(result.draft)
    await router.push({ path: '/question-nav-chat', query: { learningContext: handle } })
  } catch (e) { if (active && request === continuationRequest) actionError.value = resolveErrorMessage(e) }
  finally { if (active && request === continuationRequest) continuing.value = false }
}
async function decide(id: string, decision: 'accepted' | 'rejected') {
  if (deciding.value || loading.value) return
  deciding.value = id; actionError.value = ''
  try { await decideSuggestion(id, decision); if (active) await load() }
  catch (e) { if (active) actionError.value = resolveErrorMessage(e) }
  finally { if (active) deciding.value = '' }
}

function drag(event: PointerEvent, id: string) {
  const target = event.currentTarget as SVGElement; const svg = target.ownerSVGElement
  if (!svg) return
  target.setPointerCapture(event.pointerId)
  const move = (e: PointerEvent) => { const matrix = svg.getScreenCTM(); if (!matrix) return; const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(matrix.inverse()); positions.value[id] = { x: (p.x - 450) / zoom.value + 450, y: (p.y - 280) / zoom.value + 280 } }
  const end = () => { target.removeEventListener('pointermove', move); target.removeEventListener('pointerup', end); target.removeEventListener('pointercancel', end) }
  target.addEventListener('pointermove', move); target.addEventListener('pointerup', end); target.addEventListener('pointercancel', end)
}
watch(visibleNodes, nodes => {
  positions.value = Object.fromEntries(nodes.map((n, i) => [n.id, { x: 80 + (i % 5) * 180, y: 85 + Math.floor(i / 5) * 110 }]))
})
onMounted(load)
</script>

<template>
  <section class="graph-page"><div class="graph-inner">
    <header><div><span class="eyebrow">你的学习留下的线索</span><h1>知识地图</h1><p>从已保存的对话与记忆中整理，只连接有明确依据的关系。</p></div><button data-testid="refresh" :disabled="loading" @click="load">{{ loading ? '读取中…' : '刷新地图' }}</button></header>
    <nav class="view-tabs" aria-label="地图视图"><button :class="{active:tab==='map'}" @click="tab='map'">知识地图</button><button data-testid="tab-events" :class="{active:tab==='events'}" @click="tab='events'">学习轨迹</button><button data-testid="tab-suggestions" :class="{active:tab==='suggestions'}" @click="tab='suggestions'">关联建议</button></nav>
    <p v-if="actionError" role="alert" class="notice">{{ actionError }}</p>
    <div v-show="tab === 'map'" class="tools"><input v-model="search" aria-label="搜索知识节点" placeholder="搜索节点…" /><button :class="{ active: !local }" @click="local = false">全局</button><button data-testid="local" :disabled="!current" :class="{ active: local }" @click="local = true">局部 · 一跳</button><button aria-label="缩小" @click="zoom = Math.max(.5, zoom - .15)">−</button><button aria-label="放大" @click="zoom = Math.min(2, zoom + .15)">＋</button><button @click="zoom = 1">重置缩放</button></div>
    <p v-if="graph.meta?.truncated" class="notice">达到读取或展示上限，部分记录未包含。</p>
    <div v-show="tab === 'map'" class="graph-layout"><section class="canvas-panel" aria-label="学习知识地图">
      <div class="canvas-toolbar">{{ visibleNodes.length }} 个节点 · {{ visibleEdges.length }} 条关联 <span>孤立节点同样保留</span></div>
      <div v-if="loading" class="empty" role="status">正在读取学习记录…</div>
      <div v-else-if="error" class="empty" role="alert"><h2>地图暂时无法读取</h2><p>{{ error }}</p><p>未使用示例数据替代你的记录。</p></div>
      <div v-else-if="!graph.nodes.length" class="empty"><h2>还没有学习节点</h2><p>在聊天中明确说出正在学习的知识点，保存后回来刷新。</p><button @click="router.push('/question-nav-chat')">开始对话</button></div>
      <div v-else-if="!visibleNodes.length" class="empty">没有符合搜索条件的节点</div>
      <div v-else class="map-scroll"><svg :viewBox="`0 0 900 ${canvasHeight}`" :style="{height: `${canvasHeight}px`}" class="map" aria-label="节点与关系"><defs><marker id="relation-arrow" viewBox="0 0 10 10" refX="20" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#839c79" /></marker></defs><g :transform="`translate(450 280) scale(${zoom}) translate(-450 -280)`">
        <g v-for="edge in visibleEdges" :key="edge.id"><line :class="{ exploratory: edge.relation === 'user_confirmed' }" :marker-end="edge.relation === 'user_confirmed' ? undefined : 'url(#relation-arrow)'" :x1="point(edge.source).x" :y1="point(edge.source).y" :x2="point(edge.target).x" :y2="point(edge.target).y" /><title>{{ title(edge.source) }} → {{ title(edge.target) }}：{{ relationLabel(edge.relation) }}；{{ edge.evidence.quote }}</title></g>
        <g v-for="node in visibleNodes" :key="node.id" :data-node="node.id" class="node" :class="{ selected: selected === node.id }" :transform="`translate(${point(node.id).x} ${point(node.id).y})`" role="button" tabindex="0" :aria-label="node.title" @click="selected = node.id" @keydown.enter="selected = node.id" @keydown.space.prevent="selected = node.id" @pointerdown="drag($event, node.id)"><circle r="12"/><text y="34" text-anchor="middle">{{ node.title.length > 11 ? node.title.slice(0,11) + '…' : node.title }}</text><title>{{ node.title }}</title></g>
      </g></svg></div>
      <footer>点击节点查看来源 · 拖动节点调整位置 · 小屏可横向滚动 · 位置远近不代表知识关系</footer>
    </section>
    <aside v-if="current"><div class="panel-head"><span class="eyebrow">学习线索</span><button aria-label="关闭详情" @click="selected = ''; local = false">×</button></div><h2>{{ current.title }}</h2><p v-if="current.summary">{{ current.summary }}</p><button class="primary" data-testid="continue" :disabled="continuing || loading" @click="continueLearning">{{ continuing ? '核对来源中…' : '继续学这个 →' }}</button><p class="hint">将问题放入新对话输入框，由你确认发送。</p><h3>来源记录 · {{ current.sources.length }}</h3><article v-for="(source,index) in current.sources" :key="`${source.messageId}-${index}`"><blockquote>{{ source.quote }}</blockquote><small v-if="source.createdAt">{{ source.createdAt }}</small><button data-testid="source" @click="openSource(source)">查看来源对话 ↗</button></article><h3>节点关联 · {{ relations.length }}</h3><p v-if="!relations.length">暂无明确关系，保留为独立节点。</p><article v-for="edge in relations" :key="edge.id"><button @click="selected = edge.source === selected ? edge.target : edge.source">{{ title(edge.source) }} → {{ title(edge.target) }}</button><small>{{ relationLabel(edge.relation) }}</small><blockquote>{{ edge.evidence.quote }}</blockquote><button @click="openSource(edge.evidence)">查看关系依据 ↗</button></article></aside>
    <aside v-else class="empty"><h2>选择一个知识节点</h2><p>查看原始对话和明确关联，或从这里继续学习。</p></aside></div>
    <section v-if="tab !== 'map'" class="records-panel">
      <p v-if="loading" role="status">正在读取学习记录…</p><p v-else-if="error" role="alert">{{ error }}</p>
      <template v-else-if="tab === 'events'"><h2>学习轨迹</h2><p class="hint">记录你提出的目标、问题和练习线索，不等同于已经掌握或完成。</p><p v-if="!graph.events?.length">暂无有据可查的学习轨迹。</p><article v-for="event in graph.events" :key="event.id" class="record"><small>{{ eventLabel(event.type) }} · {{ event.occurredAt || '时间未记录' }}</small><h3>{{ event.title }}</h3><div class="chips"><button v-for="id in event.nodeIds" :key="id" @click="selected=id; local=true; tab='map'">{{ title(id) }}</button></div><div v-for="(source,i) in event.sources" :key="i"><blockquote>{{ source.quote }}</blockquote><button @click="openSource(source)">查看来源对话 ↗</button></div></article></template>
      <template v-else><h2>关联建议</h2><p class="hint">这些是待探索的联系，不是已证实的知识关系。确认后以虚线显示，不作为事实依赖。</p><p v-if="!graph.suggestions?.length">暂时没有关联建议。</p><article v-for="item in graph.suggestions" :key="item.id" class="record"><h3>{{ title(item.source) }} ↔ {{ title(item.target) }}</h3><p>{{ item.reason }}</p><div v-for="(source,i) in item.sources" :key="i"><blockquote>{{ source.quote }}</blockquote><button @click="openSource(source)">查看建议来源 ↗</button></div><div v-if="item.status === 'pending'" class="decision-actions"><button :data-testid="`accept-${item.id}`" :disabled="!!deciding" @click="decide(item.id,'accepted')">{{ deciding===item.id ? '保存中…' : '确认探索关联' }}</button><button :data-testid="`reject-${item.id}`" :disabled="!!deciding" @click="decide(item.id,'rejected')">暂不关联</button></div><div v-else><small>{{ item.status === 'accepted' ? '已确认的探索关联' : '已拒绝此建议' }}</small><button :data-testid="`change-${item.id}`" :disabled="!!deciding" @click="decide(item.id, item.status === 'accepted' ? 'rejected' : 'accepted')">{{ deciding === item.id ? '保存中…' : item.status === 'accepted' ? '撤回关联' : '重新确认' }}</button></div></article></template>
    </section>
  </div></section>
</template>

<style scoped>
.view-tabs{display:flex;gap:8px;margin-bottom:20px}.records-panel{border:1px solid var(--line);border-radius:16px;padding:24px;background:rgba(255,254,250,.55)}.records-panel h2{font-weight:500}.records-panel h3{margin:8px 0;color:var(--ink);font-size:16px}.record{padding:20px 0}.decision-actions,.chips{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0}.decision-actions button{border:1px solid var(--line);padding:8px 12px}.exploratory{stroke-dasharray:6 5;stroke:var(--clay,#b87960)}

.graph-page{min-height:100vh;padding:44px 48px}.graph-inner{max-width:1240px;margin:auto}header{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:25px}h1{margin:8px 0;font-family:var(--font-display);font-size:40px;font-weight:500;letter-spacing:-.04em}p,.eyebrow,.hint{color:var(--muted);font-size:13px;line-height:1.8}.eyebrow{font-size:12px}button,input{border:1px solid var(--line);background:var(--page,#fffef9);color:var(--ink);border-radius:8px;padding:9px 12px;font:inherit;font-size:12px}button{cursor:pointer}button:hover,.active{background:var(--sage-soft,#eaf0e6)}button:disabled{opacity:.45;cursor:default}.tools{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:18px}.tools input{margin-right:auto;min-width:190px}.graph-layout{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:18px}.canvas-panel,aside{border:1px solid var(--line);border-radius:var(--radius-panel,16px);background:rgba(255,254,250,.55);overflow:hidden}.canvas-panel{display:flex;flex-direction:column;min-height:610px}.canvas-toolbar,footer{padding:16px 20px;font-size:11px;color:var(--muted);border-bottom:1px solid var(--line)}.canvas-toolbar span{float:right;color:var(--soft-muted)}footer{margin-top:auto;border:0;border-top:1px solid var(--line);line-height:1.8}.map-scroll{max-height:600px;overflow:auto}.map{width:100%;min-width:700px;flex:1;min-height:400px;touch-action:none}line{stroke:#b9c7b3;stroke-width:1.5}.node{cursor:grab;outline:none}.node circle{fill:var(--sage,#839c79);stroke:#faf9f3;stroke-width:3}.node.selected circle,.node:focus circle{stroke:var(--clay,#b87960);stroke-width:4}.node text{fill:var(--ink);font-size:13px}.empty{display:flex;flex:1;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:35px}.empty h2{font-size:21px;font-weight:500}.empty p{max-width:320px}aside{padding:22px;max-height:760px;overflow:auto}.panel-head{display:flex;align-items:center;justify-content:space-between}.panel-head button{border:0;padding:2px 8px}aside h2{font-size:25px;font-weight:500;overflow-wrap:anywhere}h3{font-size:12px;font-weight:500;margin-top:27px;color:var(--muted)}article{padding:12px 0;border-top:1px solid var(--line);font-size:12px}blockquote{margin:4px 0 10px;white-space:pre-wrap;overflow-wrap:anywhere;color:var(--ink);line-height:1.7}article button{padding:5px 0;border:0;background:transparent;text-align:left;color:var(--sage,#67805c)}small{display:block;color:var(--muted);font-size:10px;margin:6px 0}.primary{width:100%;background:var(--sage-soft,#eaf0e6)}.hint{font-size:11px}.notice{font-size:12px;color:var(--clay)}@media(max-width:1000px){.graph-page{padding:28px 20px}.graph-layout{grid-template-columns:1fr}aside{max-height:none}.canvas-panel{min-height:520px}}@media(max-width:600px){header{align-items:flex-start}h1{font-size:32px}.tools input{width:100%}.canvas-toolbar span{float:none;display:block;margin-top:5px}.graph-page{padding:22px 14px}}
</style>
