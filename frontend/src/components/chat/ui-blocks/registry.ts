/**
 * UI block 的 renderer registry：把 `type + version` 分发到已注册的组件。
 *
 * 只做校验与分发，不接入任何 view / ChatThread；后端 visualization 事件属于后续任务。
 */
import type { Component } from 'vue'
import AttentionMatrix from '../AttentionMatrix.vue'
import ConvWindow from '../ConvWindow.vue'
import {
  parseUiBlockEnvelope,
  validateAttentionMatrixProps,
  validateConvWindowProps,
  type ValidationResult,
} from './schema'

export type BlockPropsValidator = (props: unknown) => ValidationResult<object>

export interface RegistryEntry {
  component: Component
  validateProps: BlockPropsValidator
}

// 用 Map 而非普通对象，避免 type 为 "constructor" 等名字时命中 Object.prototype。
// 新增类型：schema.ts 写校验器 + 新组件 + 这里登记一行，并同步后端
// visualization.py 的 _BLOCK_PARSERS 与 tests/fixtures/ui_block_contract.json。
const REGISTRY = new Map<string, Map<number, RegistryEntry>>([
  [
    'attention_matrix',
    new Map<number, RegistryEntry>([
      [1, { component: AttentionMatrix, validateProps: validateAttentionMatrixProps }],
    ]),
  ],
  [
    'conv_window',
    new Map<number, RegistryEntry>([
      [1, { component: ConvWindow, validateProps: validateConvWindowProps }],
    ]),
  ],
])

export type DispatchResult =
  | { ok: true; component: Component; props: object }
  | { ok: false; error: string }

/** 校验未知 JSON 形式的 UI block，成功时返回组件与规范化后的 props。 */
export const dispatchUiBlock = (input: unknown): DispatchResult => {
  const envelope = parseUiBlockEnvelope(input)
  if (!envelope.ok) return envelope

  const { type, version, props } = envelope.value
  const versions = REGISTRY.get(type)
  if (!versions) return { ok: false, error: `未注册的 UI block 类型 "${type}"` }

  const entry = versions.get(version)
  if (!entry) {
    return { ok: false, error: `类型 "${type}" 不支持 version ${version}` }
  }

  const checked = entry.validateProps(props)
  if (!checked.ok) return checked

  return { ok: true, component: entry.component, props: checked.value }
}
