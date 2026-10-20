import { describe, it, expect } from 'vitest'
import AttentionMatrix from '../../AttentionMatrix.vue'
import { dispatchUiBlock } from '../registry'

const block = (overrides: Record<string, unknown> = {}) => ({
  type: 'attention_matrix',
  version: 1,
  props: { tokenCount: 5, mode: 'causal' },
  ...overrides,
})

describe('dispatchUiBlock', () => {
  it('dispatches a valid attention_matrix v1 block to AttentionMatrix', () => {
    const result = dispatchUiBlock(block())
    expect(result).toEqual({
      ok: true,
      component: AttentionMatrix,
      props: { tokenCount: 5, mode: 'causal' },
    })
  })

  it('returns normalized props, dropping nothing the schema allows', () => {
    const result = dispatchUiBlock(
      block({ props: { tokenCount: 3, mode: 'bidirectional', queryLabels: ['a', 'b', 'c'] } }),
    )
    expect(result.ok && result.props).toEqual({
      tokenCount: 3,
      mode: 'bidirectional',
      queryLabels: ['a', 'b', 'c'],
    })
  })

  it('rejects an unknown type with a readable reason', () => {
    const result = dispatchUiBlock(block({ type: 'pie_chart' }))
    expect(result.ok).toBe(false)
    expect(!result.ok && result.error).toContain('pie_chart')
  })

  it('does not resolve inherited object keys as types', () => {
    expect(dispatchUiBlock(block({ type: 'constructor' })).ok).toBe(false)
    expect(dispatchUiBlock(block({ type: '__proto__' })).ok).toBe(false)
  })

  it('rejects an unregistered version', () => {
    const result = dispatchUiBlock(block({ version: 2 }))
    expect(result.ok).toBe(false)
    expect(!result.ok && result.error).toContain('version 2')
  })

  it('surfaces props validation errors', () => {
    const result = dispatchUiBlock(block({ props: { tokenCount: 5, mode: 'causal', weights: [] } }))
    expect(result.ok).toBe(false)
    expect(!result.ok && result.error).toContain('weights')
  })

  it.each([null, [], 'attention_matrix', { type: 'attention_matrix' }])(
    'rejects malformed input %j without throwing',
    (input) => {
      expect(() => dispatchUiBlock(input)).not.toThrow()
      expect(dispatchUiBlock(input).ok).toBe(false)
    },
  )
})
