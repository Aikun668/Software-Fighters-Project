import { describe, it, expect } from 'vitest'
import { setLearningDraft, consumeLearningDraft } from '../learningDraft'
describe('private learning draft handoff', () => {
  it('consumes the latest in-memory draft only once', () => {
    const handle = setLearningDraft('private source')
    expect(consumeLearningDraft(handle)).toBe('private source')
    expect(consumeLearningDraft(handle)).toBe('')
    setLearningDraft('old'); const latest = setLearningDraft('new')
    expect(consumeLearningDraft(handle)).toBe('')
    expect(consumeLearningDraft('wrong')).toBe('')
    expect(consumeLearningDraft(latest)).toBe('new')
  })
  it('uses cryptographic random bytes when randomUUID is unavailable on an HTTP gateway', () => {
    const original = crypto.randomUUID
    Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: undefined })
    try {
      const handle = setLearningDraft('http gateway context')
      expect(handle).toMatch(/^[0-9a-f]{32}$/)
      expect(consumeLearningDraft(handle)).toBe('http gateway context')
    } finally { Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: original }) }
  })

})
