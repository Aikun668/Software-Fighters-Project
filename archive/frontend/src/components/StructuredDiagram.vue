<script setup lang="ts">
import { computed, ref } from 'vue'
import type { DiagramEdge, DiagramNode, DiagramSchema } from '@/types/diagram'

const props = defineProps<{
  diagram: DiagramSchema | null | undefined
}>()

const selectedId = ref<string | null>(null)

const WIDTH = 800
const HEIGHT = 480
const MARGIN = 60
const NODE_R = 28

const isValid = computed<boolean>(() => {
  const d = props.diagram
  if (!d || typeof d !== 'object') return false
  if (d.schema_version !== 'v1') return false
  if (!Array.isArray(d.nodes) || d.nodes.length < 2) return false
  if (!Array.isArray(d.edges) || d.edges.length < 1) return false
  return d.nodes.every(
    (n) => !!n && typeof n.id === 'string' && n.id.length > 0 && typeof n.layer === 'number',
  )
})

interface PlacedNode {
  node: DiagramNode
  x: number
  y: number
}
interface PlacedEdge {
  key: string
  x1: number
  y1: number
  x2: number
  y2: number
  label?: string
}

const diagram = computed<DiagramSchema | null>(() => (isValid.value ? (props.diagram ?? null) : null))

const placedNodes = computed<PlacedNode[]>(() => {
  const d = diagram.value
  if (!d) return []
  const byLayer = new Map<number, DiagramNode[]>()
  for (const n of d.nodes) {
    const arr = byLayer.get(n.layer) ?? []
    arr.push(n)
    byLayer.set(n.layer, arr)
  }
  const layerEntries = [...byLayer.entries()].sort((a, b) => a[0] - b[0])
  const placed: PlacedNode[] = []
  layerEntries.forEach(([, nodes], li) => {
    const x = MARGIN + ((WIDTH - 2 * MARGIN) * li) / Math.max(1, layerEntries.length - 1)
    nodes.forEach((n, ni) => {
      const y = MARGIN + ((HEIGHT - 2 * MARGIN) * ni) / Math.max(1, nodes.length - 1)
      placed.push({ node: n, x, y })
    })
  })
  return placed
})

const positionOf = computed<Map<string, { x: number; y: number }>>(() => {
  const m = new Map<string, { x: number; y: number }>()
  for (const p of placedNodes.value) m.set(p.node.id, { x: p.x, y: p.y })
  return m
})

const placedEdges = computed<PlacedEdge[]>(() => {
  const d = diagram.value
  if (!d) return []
  const pos = positionOf.value
  const seen = new Set<string>()
  const out: PlacedEdge[] = []
  for (const e of d.edges as DiagramEdge[]) {
    if (!e || !pos.has(e.source) || !pos.has(e.target) || e.source === e.target) continue
    const key = `${e.source}->${e.target}`
    if (seen.has(key)) continue
    seen.add(key)
    const s = pos.get(e.source)!
    const t = pos.get(e.target)!
    out.push({ key, x1: s.x, y1: s.y, x2: t.x, y2: t.y, label: e.label })
  }
  return out
})

const selectedNode = computed<DiagramNode | null>(() => {
  if (!selectedId.value || !diagram.value) return null
  return diagram.value.nodes.find((n) => n.id === selectedId.value) ?? null
})

function toggle(id: string): void {
  selectedId.value = selectedId.value === id ? null : id
}
</script>

<template>
  <div class="structured-diagram">
    <div v-if="!diagram" class="diagram-empty" role="status">旧格式暂不支持交互预览</div>
    <template v-else>
      <div class="diagram-header">
        <div class="diagram-title">{{ diagram.title }}</div>
        <div class="diagram-summary">{{ diagram.summary }}</div>
      </div>
      <svg
        class="diagram-svg"
        :viewBox="`0 0 ${WIDTH} ${HEIGHT}`"
        role="img"
        :aria-label="diagram.title"
      >
        <defs>
          <marker
            id="sd-arrow"
            markerWidth="10"
            markerHeight="7"
            refX="9"
            refY="3.5"
            orient="auto"
          >
            <polygon points="0 0, 10 3.5, 0 7" fill="#64748b" />
          </marker>
        </defs>
        <line
          v-for="edge in placedEdges"
          :key="edge.key"
          :x1="edge.x1"
          :y1="edge.y1"
          :x2="edge.x2"
          :y2="edge.y2"
          class="edge-line"
          marker-end="url(#sd-arrow)"
        />
        <g
          v-for="placed in placedNodes"
          :key="placed.node.id"
          class="node-group"
          :class="{ selected: selectedId === placed.node.id }"
          tabindex="0"
          role="button"
          :aria-label="placed.node.label"
          @click="toggle(placed.node.id)"
          @keydown.enter.prevent="toggle(placed.node.id)"
          @keydown.space.prevent="toggle(placed.node.id)"
        >
          <circle :cx="placed.x" :cy="placed.y" :r="NODE_R" class="node-circle" />
          <text :x="placed.x" :y="placed.y + NODE_R + 16" class="node-label" text-anchor="middle">
            {{ placed.node.label }}
          </text>
        </g>
      </svg>
      <div v-if="selectedNode" class="diagram-detail" role="note">
        <div class="detail-label">{{ selectedNode.label }}</div>
        <div class="detail-text">{{ selectedNode.detail }}</div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.structured-diagram {
  width: 100%;
  font-family: system-ui, -apple-system, sans-serif;
}
.diagram-empty {
  padding: 24px;
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
  color: #64748b;
  text-align: center;
}
.diagram-header {
  margin-bottom: 8px;
}
.diagram-title {
  font-size: 16px;
  font-weight: 600;
  color: #0f172a;
}
.diagram-summary {
  font-size: 13px;
  color: #64748b;
}
.diagram-svg {
  display: block;
  width: 100%;
  height: auto;
  background: #f8fafc;
  border-radius: 8px;
}
.edge-line {
  stroke: #64748b;
  stroke-width: 2;
}
.node-group {
  cursor: pointer;
  outline: none;
}
.node-circle {
  fill: #38bdf8;
  stroke: #0f172a;
  stroke-width: 2;
  transition: fill 0.15s ease;
}
.node-group:hover .node-circle,
.node-group:focus .node-circle,
.node-group.selected .node-circle {
  fill: #818cf8;
}
.node-label {
  font-size: 13px;
  fill: #0f172a;
}
.diagram-detail {
  margin-top: 8px;
  padding: 12px;
  border-left: 3px solid #38bdf8;
  background: #f1f5f9;
  border-radius: 4px;
}
.detail-label {
  font-weight: 600;
  color: #0f172a;
}
.detail-text {
  margin-top: 4px;
  font-size: 13px;
  color: #475569;
}
</style>
