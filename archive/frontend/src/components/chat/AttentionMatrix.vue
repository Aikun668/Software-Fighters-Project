<script setup lang="ts">
/**
 * 注意力可访问关系矩阵（MVP）。
 *
 * 只展示 Mask 决定的可访问关系；不支持 weights，颜色不代表真实 Attention 权重（D-007）。
 * 因果模式下行色由浅到深为位置示意（靠后的 Query 能看到的上文越多），还原参考设计。
 */
import { computed, ref, watch } from 'vue'

type AttentionMode = 'causal' | 'bidirectional'

const props = defineProps<{
  tokenCount: number
  mode: AttentionMode
  queryLabels?: string[]
  keyLabels?: string[]
}>()

const MIN_TOKENS = 3
const MAX_TOKENS = 8

const clampTokens = (value: number) =>
  Math.min(MAX_TOKENS, Math.max(MIN_TOKENS, Math.round(value)))

const tokenCount = ref(clampTokens(props.tokenCount))
const mode = ref<AttentionMode>(props.mode)
const selected = ref<{ q: number; k: number } | null>(null)

watch(
  () => props.tokenCount,
  (value) => {
    tokenCount.value = clampTokens(value)
  },
)
watch(
  () => props.mode,
  (value) => {
    mode.value = value
  },
)

const indices = computed(() => Array.from({ length: tokenCount.value }, (_, i) => i))

const queryName = (i: number) => props.queryLabels?.[i] ?? `Q${i + 1}`
const keyName = (j: number) => props.keyLabels?.[j] ?? `K${j + 1}`

const isAllowed = (q: number, k: number) =>
  mode.value === 'bidirectional' || k <= q

const allowedTotal = computed(() => {
  const n = tokenCount.value
  return mode.value === 'bidirectional' ? n * n : (n * (n + 1)) / 2
})
const maskedTotal = computed(() => tokenCount.value * tokenCount.value - allowedTotal.value)

const activeSelection = computed(() => {
  const s = selected.value
  if (!s || s.q >= tokenCount.value || s.k >= tokenCount.value) return null
  return isAllowed(s.q, s.k) ? s : null
})

interface MatrixCell {
  q: number
  k: number
  allowed: boolean
  selected: boolean
  inSelectedRow: boolean
  label: string
  /** 行深浅：位置示意（非权重），仅因果模式的可访问格携带 */
  depthStyle?: Record<string, string>
}

const buildCell = (q: number, k: number): MatrixCell => {
  const allowed = isAllowed(q, k)
  const stateText = allowed ? '可访问' : '被 Mask 屏蔽，不可访问'
  const current = activeSelection.value
  return {
    q,
    k,
    allowed,
    selected: current?.q === q && current?.k === k,
    inSelectedRow: allowed && current?.q === q && current?.k !== k,
    label: `${queryName(q)} → ${keyName(k)}：${stateText}`,
    depthStyle:
      allowed && mode.value === 'causal'
        ? { '--attn-depth': (q / Math.max(1, tokenCount.value - 1)).toFixed(3) }
        : undefined,
  }
}

const rows = computed(() =>
  indices.value.map((q) => ({
    q,
    label: queryName(q),
    cells: indices.value.map((k) => buildCell(q, k)),
  })),
)

const choose = (q: number, k: number) => {
  if (!isAllowed(q, k)) return
  selected.value = { q, k }
}

const cellClass = (cell: MatrixCell) => ({
  'attn-cell--allowed': cell.allowed,
  'attn-cell--masked': !cell.allowed,
  'attn-cell--selected': cell.selected,
  'attn-cell--row': cell.inSelectedRow,
})

const modeLabel = computed(() => (mode.value === 'causal' ? '因果' : '双向'))

const explanation = computed(() => {
  const s = activeSelection.value
  if (!s) return null
  const q = queryName(s.q)
  const k = keyName(s.k)
  const reason =
    mode.value === 'causal'
      ? `因果 Mask 只允许 Query 访问当前位置及之前的 Key（${k} 不晚于 ${q}）。`
      : '双向模式下每个 Query 都可以访问所有 Key。'
  return { title: `${q} → ${k}`, reason }
})
</script>

<template>
  <section class="attn-matrix" aria-labelledby="attn-matrix-title">
    <header class="attn-matrix__header">
      <h3 id="attn-matrix-title" class="attn-matrix__title">注意力可访问关系</h3>
      <p class="attn-matrix__hint">左轴为 Query，顶轴为 Key。</p>
    </header>

    <div class="attn-matrix__controls">
      <label class="attn-matrix__slider">
        <span>Token 数 {{ tokenCount }}</span>
        <input
          v-model.number="tokenCount"
          type="range"
          :min="MIN_TOKENS"
          :max="MAX_TOKENS"
          step="1"
        />
      </label>
      <div class="attn-matrix__modes" role="group" aria-label="注意力模式">
        <button
          type="button"
          :aria-pressed="mode === 'causal'"
          :class="{ 'is-active': mode === 'causal' }"
          @click="mode = 'causal'"
        >
          因果
        </button>
        <button
          type="button"
          :aria-pressed="mode === 'bidirectional'"
          :class="{ 'is-active': mode === 'bidirectional' }"
          @click="mode = 'bidirectional'"
        >
          双向
        </button>
      </div>
    </div>

    <div class="attn-matrix__body">
      <div class="attn-matrix__grid-wrap">
        <div
          class="attn-matrix__grid"
          :style="{ '--attn-n': tokenCount }"
          role="group"
          :aria-label="`${tokenCount} 个 token 的${modeLabel}可访问关系矩阵`"
        >
          <span class="attn-matrix__corner" aria-hidden="true" />
          <span
            v-for="k in indices"
            :key="`key-${k}`"
            class="attn-matrix__axis"
            aria-hidden="true"
          >
            {{ keyName(k) }}
          </span>
          <template v-for="row in rows" :key="`row-${row.q}`">
            <span class="attn-matrix__axis" aria-hidden="true">{{ row.label }}</span>
            <button
              v-for="cell in row.cells"
              :key="`cell-${cell.q}-${cell.k}`"
              type="button"
              class="attn-cell"
              :class="cellClass(cell)"
              :style="cell.depthStyle"
              :disabled="!cell.allowed"
              :aria-label="cell.label"
              :aria-pressed="cell.selected"
              :title="cell.label"
              :data-q="cell.q + 1"
              :data-k="cell.k + 1"
              @click="choose(cell.q, cell.k)"
            />
          </template>
        </div>
      </div>

      <aside class="attn-matrix__detail" aria-live="polite">
        <template v-if="explanation">
          <p class="attn-matrix__detail-title">{{ explanation.title }}：可访问</p>
          <p>{{ explanation.reason }}</p>
        </template>
        <p v-else class="attn-matrix__detail-hint">点击一个可访问的格子，查看它的关系。</p>
      </aside>
    </div>

    <footer class="attn-matrix__footer">
      <p class="attn-matrix__legend">颜色表示 Mask/可访问关系；因果模式下行色越深代表能看到的上文越多（位置示意），不代表真实 Attention 权重。</p>
      <p class="attn-matrix__stats">
        可访问 {{ allowedTotal }} · 灰色 {{ maskedTotal }} · 共 {{ tokenCount * tokenCount }} 格
      </p>
    </footer>
  </section>
</template>

<style scoped>
.attn-matrix {
  --viz-blue: #80aec8;
  --viz-blue-strong: #447f9f;
  --viz-blue-pale: #ecf4f8;
  --viz-cell: #cde2ee;
  --viz-disabled: #f0f0ed;
  --text-primary: #27343a;
  --text-secondary: #77817f;
  --border-subtle: #e8e5de;
  --surface-card: #fffefc;

  background: var(--surface-card);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 24px;
  color: var(--text-primary);
  max-width: 900px;
}

.attn-matrix__title {
  margin: 0;
  font-size: 20px;
}

.attn-matrix__hint,
.attn-matrix__legend,
.attn-matrix__stats,
.attn-matrix__detail-hint {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.attn-matrix__controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px;
  margin: 16px 0;
}

.attn-matrix__slider {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.attn-matrix__modes button {
  border: 1px solid var(--border-subtle);
  background: var(--surface-card);
  color: var(--text-primary);
  border-radius: 999px;
  padding: 6px 14px;
  cursor: pointer;
}

.attn-matrix__modes button.is-active {
  background: var(--viz-blue-pale);
  border-color: var(--viz-blue);
}

.attn-matrix__body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 240px);
  gap: 24px;
  align-items: start;
}

.attn-matrix__grid {
  display: grid;
  grid-template-columns: auto repeat(var(--attn-n), minmax(0, 1fr));
  gap: 4px;
  align-items: center;
  max-width: 480px;
}

.attn-matrix__axis {
  font-size: 12px;
  color: var(--text-secondary);
  text-align: center;
}

.attn-cell {
  aspect-ratio: 1 / 1;
  min-width: 0;
  width: 100%;
  border: 1px solid transparent;
  border-radius: 6px;
  padding: 0;
  cursor: pointer;
}

.attn-cell--allowed {
  /* 行深浅：--attn-depth 由 0 → 1，浅雾蓝渐入中雾蓝（位置示意，非权重） */
  background: color-mix(in srgb, var(--viz-cell), var(--viz-blue) calc(var(--attn-depth, 0) * 55%));
}

.attn-cell--row {
  background: var(--viz-blue);
}

.attn-cell--selected {
  position: relative;
  background: var(--viz-blue-strong);
  border-color: var(--viz-blue-strong);
}

.attn-cell--selected::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #fff;
  transform: translate(-50%, -50%);
}

.attn-cell--masked {
  background: var(--viz-disabled);
  cursor: not-allowed;
}

.attn-cell:focus-visible {
  outline: 2px solid var(--viz-blue-strong);
  outline-offset: 2px;
}

.attn-matrix__detail {
  font-size: 14px;
  line-height: 1.6;
}

.attn-matrix__detail-title {
  margin: 0 0 4px;
  font-weight: 600;
}

.attn-matrix__footer {
  margin-top: 16px;
}

@media (max-width: 739px) {
  .attn-matrix {
    padding: 16px;
  }

  .attn-matrix__body {
    grid-template-columns: minmax(0, 1fr);
  }

  .attn-matrix__grid {
    gap: 2px;
  }
}
</style>
