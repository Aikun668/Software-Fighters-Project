import { describe, it, expect } from 'vitest'
import {
  parseUiBlockEnvelope,
  validateAttentionMatrixProps,
  ATTENTION_TOKEN_MAX,
  ATTENTION_TOKEN_MIN,
} from '../schema'

const validProps = (overrides: Record<string, unknown> = {}) => ({
  tokenCount: 5,
  mode: 'causal',
  ...overrides,
})

describe('parseUiBlockEnvelope', () => {
  it.each([
    ['null', null],
    ['array', [{ type: 'attention_matrix', version: 1, props: {} }]],
    ['string', 'attention_matrix'],
    ['number', 42],
  ])('rejects top-level %s without throwing', (_label, input) => {
    const result = parseUiBlockEnvelope(input)
    expect(result.ok).toBe(false)
  })

  it('rejects a block missing props', () => {
    const result = parseUiBlockEnvelope({ type: 'attention_matrix', version: 1 })
    expect(result).toEqual({ ok: false, error: '缺少 props' })
  })

  it('rejects an empty or non-string type', () => {
    expect(parseUiBlockEnvelope({ type: '', version: 1, props: {} }).ok).toBe(false)
    expect(parseUiBlockEnvelope({ type: 1, version: 1, props: {} }).ok).toBe(false)
  })

  it('rejects a non-integer version', () => {
    expect(parseUiBlockEnvelope({ type: 'x', version: '1', props: {} }).ok).toBe(false)
    expect(parseUiBlockEnvelope({ type: 'x', version: 1.5, props: {} }).ok).toBe(false)
  })

  it('rejects unknown envelope fields', () => {
    const result = parseUiBlockEnvelope({ type: 'x', version: 1, props: {}, html: '<b>' })
    expect(result.ok).toBe(false)
  })
})

describe('validateAttentionMatrixProps', () => {
  it('accepts valid causal props', () => {
    expect(validateAttentionMatrixProps(validProps())).toEqual({
      ok: true,
      value: { tokenCount: 5, mode: 'causal' },
    })
  })

  it('accepts bidirectional mode and both label arrays of matching length', () => {
    const labels = ['a', 'b', 'c']
    const result = validateAttentionMatrixProps(
      validProps({ tokenCount: 3, mode: 'bidirectional', queryLabels: labels, keyLabels: labels }),
    )
    expect(result).toEqual({
      ok: true,
      value: { tokenCount: 3, mode: 'bidirectional', queryLabels: labels, keyLabels: labels },
    })
  })

  it('returns a copy of label arrays, not the input reference', () => {
    const labels = ['a', 'b', 'c']
    const result = validateAttentionMatrixProps(validProps({ tokenCount: 3, queryLabels: labels }))
    expect(result.ok && result.value.queryLabels).not.toBe(labels)
  })

  it.each([ATTENTION_TOKEN_MIN, ATTENTION_TOKEN_MAX])('accepts boundary tokenCount %i', (n) => {
    expect(validateAttentionMatrixProps(validProps({ tokenCount: n })).ok).toBe(true)
  })

  it.each([2, 9, 5.5, '5', null, undefined])('rejects tokenCount %s', (tokenCount) => {
    const result = validateAttentionMatrixProps(validProps({ tokenCount }))
    expect(result.ok).toBe(false)
  })

  it.each(['full', 'Causal', '', null])('rejects mode %s', (mode) => {
    expect(validateAttentionMatrixProps(validProps({ mode })).ok).toBe(false)
  })

  it('rejects props containing weights (D-007)', () => {
    const result = validateAttentionMatrixProps(
      validProps({ weights: [[0.1, 0.9, 0, 0, 0]] }),
    )
    expect(result.ok).toBe(false)
    expect(!result.ok && result.error).toContain('weights')
  })

  it('rejects queryLabels whose length differs from tokenCount', () => {
    const result = validateAttentionMatrixProps(validProps({ queryLabels: ['a', 'b'] }))
    expect(result.ok).toBe(false)
    expect(!result.ok && result.error).toContain('queryLabels')
  })

  it('rejects keyLabels whose length differs from tokenCount', () => {
    expect(validateAttentionMatrixProps(validProps({ keyLabels: ['a'] })).ok).toBe(false)
  })

  it('rejects label arrays that contain non-strings', () => {
    expect(
      validateAttentionMatrixProps(validProps({ queryLabels: ['a', 1, 'c', 'd', 'e'] })).ok,
    ).toBe(false)
  })

  it('rejects unknown prop keys', () => {
    expect(validateAttentionMatrixProps(validProps({ color: 'red' })).ok).toBe(false)
  })

  it.each([null, [], 'props'])('rejects non-object props %j', (props) => {
    expect(validateAttentionMatrixProps(props).ok).toBe(false)
  })
})
