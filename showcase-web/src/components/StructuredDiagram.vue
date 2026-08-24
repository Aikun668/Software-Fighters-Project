<script setup lang="ts">
import { computed, ref } from 'vue'

import type { DiagramEdge, DiagramNode, DiagramSchema } from '@/types/resource'

const props = defineProps<{
  diagram: DiagramSchema | null | undefined
}>()

const WIDTH = 800
const HEIGHT = 440
const MARGIN = 70
const NODE_R = 28
const selectedId = ref<string | null>(null)

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
}

const isValid = computed(() => {
  const diagram = props.diagram
  if (!diagram || diagram.schema_version !== 'v1') return false
  if (!Array.isArray(diagram.nodes) || diagram.nodes.length < 2) return false
  if (!Array.isArray(diagram.edges) || diagram.edges.length < 1) return false
  const ids = new Set(diagram.nodes.map((node) => node.id))
  return diagram.nodes.every((node) => (
    typeof node.id === 'string'
    && Boolean(node.id)
    && typeof node.label === 'string'
    && typeof node.detail === 'string'
    && Number.isFinite(node.layer)
  )) && diagram.edges.every((edge) => (
    ids.has(edge.source) && ids.has(edge.target) && edge.source !== edge.target
  ))
})

const validDiagram = computed(() => (isValid.value ? props.diagram! : null))

const placedNodes = computed<PlacedNode[]>(() => {
  if (!validDiagram.value) return []
  const byLayer = new Map<number, DiagramNode[]>()
  for (const node of validDiagram.value.nodes) {
    const nodes = byLayer.get(node.layer) ?? []
    nodes.push(node)
    byLayer.set(node.layer, nodes)
  }
  const layers = [...byLayer.entries()].sort(([left], [right]) => left - right)
  const result: PlacedNode[] = []
  layers.forEach(([, nodes], layerIndex) => {
    const x = MARGIN + ((WIDTH - 2 * MARGIN) * layerIndex) / Math.max(1, layers.length - 1)
    nodes.forEach((node, nodeIndex) => {
      const y = MARGIN + ((HEIGHT - 2 * MARGIN) * nodeIndex) / Math.max(1, nodes.length - 1)
      result.push({ node, x, y })
    })
  })
  return result
})

const positions = computed(() => new Map(
  placedNodes.value.map(({ node, x, y }) => [node.id, { x, y }]),
))

const placedEdges = computed<PlacedEdge[]>(() => {
  if (!validDiagram.value) return []
  const seen = new Set<string>()
  const result: PlacedEdge[] = []
  for (const edge of validDiagram.value.edges as DiagramEdge[]) {
    const source = positions.value.get(edge.source)
    const target = positions.value.get(edge.target)
    if (!source || !target) continue
    const key = `${edge.source}->${edge.target}`
    if (seen.has(key)) continue
    seen.add(key)
    result.push({ key, x1: source.x, y1: source.y, x2: target.x, y2: target.y })
  }
  return result
})

const selectedNode = computed(() => {
  if (!validDiagram.value || !selectedId.value) return null
  return validDiagram.value.nodes.find((node) => node.id === selectedId.value) ?? null
})

function toggleNode(id: string): void {
  selectedId.value = selectedId.value === id ? null : id
}
</script>

<template>
  <div class="structured-diagram">
    <div v-if="!validDiagram" class="diagram-empty" role="status">
      旧格式暂不支持交互预览
    </div>
    <template v-else>
      <div class="diagram-header">
        <h3>{{ validDiagram.title }}</h3>
        <p>{{ validDiagram.summary }}</p>
      </div>
      <svg class="diagram-svg" :viewBox="`0 0 ${WIDTH} ${HEIGHT}`" role="img" :aria-label="validDiagram.title">
        <defs>
          <marker id="showcase-arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#7f8da2" />
          </marker>
        </defs>
        <line
          v-for="edge in placedEdges"
          :key="edge.key"
          :x1="edge.x1"
          :y1="edge.y1"
          :x2="edge.x2"
          :y2="edge.y2"
          class="diagram-edge"
          marker-end="url(#showcase-arrow)"
        />
        <g
          v-for="placed in placedNodes"
          :key="placed.node.id"
          class="diagram-node"
          :class="{ selected: selectedId === placed.node.id }"
          role="button"
          tabindex="0"
          :aria-label="placed.node.label"
          @click="toggleNode(placed.node.id)"
          @keydown.enter.prevent="toggleNode(placed.node.id)"
          @keydown.space.prevent="toggleNode(placed.node.id)"
        >
          <circle :cx="placed.x" :cy="placed.y" :r="NODE_R" class="node-circle" />
          <text :x="placed.x" :y="placed.y + NODE_R + 18" class="node-label" text-anchor="middle">
            {{ placed.node.label }}
          </text>
        </g>
      </svg>
      <div v-if="selectedNode" class="diagram-detail" role="note">
        <strong>{{ selectedNode.label }}</strong>
        <p>{{ selectedNode.detail }}</p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.structured-diagram {
  width: 100%;
}
.diagram-empty {
  border: 1px dashed #cbd5e1;
  border-radius: 10px;
  padding: 28px;
  color: #768396;
  text-align: center;
}
.diagram-header h3 {
  margin: 0;
  color: #263446;
  font-size: 17px;
}
.diagram-header p {
  margin: 6px 0 14px;
  color: #718095;
  font-size: 13px;
  line-height: 1.6;
}
.diagram-svg {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 12px;
  background: #f6f8fb;
}
.diagram-edge {
  stroke: #8997a9;
  stroke-width: 2;
}
.diagram-node {
  cursor: pointer;
  outline: none;
}
.node-circle {
  fill: #b9d2f7;
  stroke: #2864c7;
  stroke-width: 2;
  transition: fill 0.15s ease;
}
.diagram-node:hover .node-circle,
.diagram-node:focus .node-circle,
.diagram-node.selected .node-circle {
  fill: #7ba8e8;
}
.node-label {
  fill: #344258;
  font-size: 13px;
}
.diagram-detail {
  margin-top: 12px;
  border-left: 3px solid #4d82d8;
  border-radius: 0 9px 9px 0;
  padding: 12px 14px;
  background: #f1f6ff;
  color: #344258;
}
.diagram-detail p {
  margin: 5px 0 0;
  color: #617083;
  font-size: 13px;
  line-height: 1.6;
}
</style>
