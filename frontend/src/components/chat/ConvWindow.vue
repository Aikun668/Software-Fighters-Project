<script setup lang="ts">
/**
 * 卷积滑窗演示（conv_window v1，D-014）。
 *
 * 只演示卷积核在输入网格上的滑动位置关系（可点输出格 / 拖动滑块切换窗口）；
 * 不展示任何特征值数值——颜色只表示"当前窗口覆盖关系"，不是计算结果。
 */
import { computed, ref, watch } from 'vue'

const props = defineProps<{
  inputRows: number
  inputCols: number
  kernelSize: number
  stride: number
}>()

const clampInt = (value: number, lo: number, hi: number) =>
  Math.min(hi, Math.max(lo, Math.round(value)))

/** props 经 registry 校验后恒为合法值；此处仍做防御性钳制（与 AttentionMatrix 一致） */
const dims = computed(() => {
  const rows = clampInt(props.inputRows, 3, 8)
  const cols = clampInt(props.inputCols, 3, 8)
  const kernel = Math.min(clampInt(props.kernelSize, 2, 5), rows, cols)
  const stride = clampInt(props.stride, 1, 2)
  const outRows = Math.floor((rows - kernel) / stride) + 1
  const outCols = Math.floor((cols - kernel) / stride) + 1
  return { rows, cols, kernel, stride, outRows, outCols }
})

/** 当前窗口序号（0..outRows*outCols-1），按行优先映射到输出特征图坐标 */
const step = ref(0)
watch(dims, () => {
  step.value = 0
})

const steps = computed(() => dims.value.outRows * dims.value.outCols)

const pos = computed(() => ({
  or: Math.floor(step.value / dims.value.outCols),
  oc: step.value % dims.value.outCols,
}))

const origin = computed(() => ({
  r: pos.value.or * dims.value.stride,
  c: pos.value.oc * dims.value.stride,
}))

const inWindow = (r: number, c: number) => {
  const { r: wr, c: wc } = origin.value
  return r >= wr && r < wr + dims.value.kernel && c >= wc && c < wc + dims.value.kernel
}

const isCurrentOutput = (i: number, j: number) =>
  i === pos.value.or && j === pos.value.oc

const choose = (i: number, j: number) => {
  step.value = i * dims.value.outCols + j
}

interface Cell {
  r: number
  c: number
  inWindow: boolean
}

const inputCells = computed<Cell[]>(() => {
  const { rows, cols } = dims.value
  return Array.from({ length: rows * cols }, (_, i) => {
    const r = Math.floor(i / cols)
    const c = i % cols
    return { r, c, inWindow: inWindow(r, c) }
  })
})

const outputCells = computed(() => {
  const { outRows, outCols } = dims.value
  return Array.from({ length: outRows * outCols }, (_, i) => ({
    i: Math.floor(i / outCols),
    j: i % outCols,
  }))
})

const inputCellClass = (cell: Cell) => ({ 'conv-in-cell--window': cell.inWindow })

const windowDesc = computed(() => {
  const { kernel, stride, outRows, outCols } = dims.value
  const { or, oc } = pos.value
  const r0 = or * stride + 1
  const c0 = oc * stride + 1
  return {
    title: `输出特征图 [${or + 1}, ${oc + 1}]`,
    reason:
      `卷积核（${kernel}×${kernel}，步长 ${stride}）当前覆盖输入第 ${r0}–${r0 + kernel - 1} 行、` +
      `第 ${c0}–${c0 + kernel - 1} 列。共 ${outRows}×${outCols} = ${outRows * outCols} 个位置。`,
  }
})
</script>

<template>
  <section class="conv-window" aria-labelledby="conv-window-title">
    <header class="conv-window__header">
      <h3 id="conv-window-title" class="conv-window__title">卷积核滑动窗口</h3>
      <p class="conv-window__hint">
        输入 {{ dims.rows }}×{{ dims.cols }} · 卷积核 {{ dims.kernel }}×{{ dims.kernel }} · 步长 {{ dims.stride }}
      </p>
    </header>

    <div class="conv-window__controls">
      <label class="conv-window__slider">
        <span>窗口位置 {{ step + 1 }} / {{ steps }}</span>
        <input
          v-model.number="step"
          type="range"
          min="0"
          :max="steps - 1"
          step="1"
          aria-label="切换卷积核窗口位置"
        />
      </label>
    </div>

    <div class="conv-window__body">
      <div class="conv-window__panel">
        <p class="conv-window__panel-label">输入</p>
        <div
          class="conv-in-grid"
          :style="{ '--conv-cols': dims.cols }"
          role="group"
          :aria-label="`输入网格 ${dims.rows} 行 ${dims.cols} 列`"
        >
          <span
            v-for="cell in inputCells"
            :key="`in-${cell.r}-${cell.c}`"
            class="conv-in-cell"
            :class="inputCellClass(cell)"
            :data-r="cell.r + 1"
            :data-c="cell.c + 1"
            :aria-label="`输入格子 第 ${cell.r + 1} 行 第 ${cell.c + 1} 列${cell.inWindow ? '（当前窗口内）' : ''}`"
          />
        </div>
      </div>

      <div class="conv-window__panel">
        <p class="conv-window__panel-label">输出特征图 {{ dims.outRows }}×{{ dims.outCols }}</p>
        <div
          class="conv-out-grid"
          :style="{ '--conv-out-cols': dims.outCols }"
          role="group"
          aria-label="输出特征图，点击格子跳转对应窗口"
        >
          <button
            v-for="cell in outputCells"
            :key="`out-${cell.i}-${cell.j}`"
            type="button"
            class="conv-out-cell"
            :class="{ 'conv-out-cell--current': isCurrentOutput(cell.i, cell.j) }"
            :aria-pressed="isCurrentOutput(cell.i, cell.j)"
            :aria-label="`输出特征图格子 第 ${cell.i + 1} 行 第 ${cell.j + 1} 列`"
            @click="choose(cell.i, cell.j)"
          />
        </div>
      </div>

      <aside class="conv-window__detail" aria-live="polite">
        <p class="conv-window__detail-title">{{ windowDesc.title }}</p>
        <p>{{ windowDesc.reason }}</p>
      </aside>
    </div>

    <footer class="conv-window__footer">
      <p class="conv-window__legend">
        颜色只表示当前卷积核窗口的覆盖位置，不代表任何特征值或计算结果；点击右侧输出格子或拖动滑块可切换窗口。
      </p>
    </footer>
  </section>
</template>

<style scoped>
.conv-window {
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

.conv-window__title {
  margin: 0;
  font-size: 20px;
}

.conv-window__hint,
.conv-window__legend,
.conv-window__panel-label {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.conv-window__controls {
  margin: 16px 0;
}

.conv-window__slider {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.conv-window__body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 240px);
  gap: 24px;
  align-items: start;
}

.conv-in-grid,
.conv-out-grid {
  display: grid;
  grid-template-columns: repeat(var(--conv-cols, 5), minmax(0, 1fr));
  gap: 4px;
  max-width: 280px;
}

.conv-out-grid {
  grid-template-columns: repeat(var(--conv-out-cols, 3), minmax(0, 1fr));
  max-width: 220px;
}

.conv-in-cell {
  aspect-ratio: 1 / 1;
  width: 100%;
  min-width: 0;
  border: 1px solid transparent;
  border-radius: 6px;
  background: var(--viz-cell);
}

.conv-in-cell--window {
  background: var(--viz-blue);
  border-color: var(--viz-blue-strong);
}

.conv-out-cell {
  aspect-ratio: 1 / 1;
  width: 100%;
  min-width: 0;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  padding: 0;
  background: var(--viz-disabled);
  cursor: pointer;
}

.conv-out-cell--current {
  position: relative;
  background: var(--viz-blue-strong);
  border-color: var(--viz-blue-strong);
}

.conv-out-cell--current::after {
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

.conv-out-cell:focus-visible {
  outline: 2px solid var(--viz-blue-strong);
  outline-offset: 2px;
}

.conv-window__detail {
  font-size: 14px;
  line-height: 1.6;
}

.conv-window__detail-title {
  margin: 0 0 4px;
  font-weight: 600;
}

.conv-window__footer {
  margin-top: 16px;
}

@media (max-width: 739px) {
  .conv-window {
    padding: 16px;
  }

  .conv-window__body {
    grid-template-columns: minmax(0, 1fr);
  }

  .conv-in-grid,
  .conv-out-grid {
    gap: 2px;
  }
}
</style>
