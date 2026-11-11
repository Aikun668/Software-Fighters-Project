import { describe, it, expect } from 'vitest'
import { setLearningDraft, consumeLearningDraft, clearLearningDraft } from '../learningDraft'
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
  it('keeps map and plan drafts apart instead of letting the later one clobber the earlier', () => {
    clearLearningDraft()
    const fromMap = setLearningDraft('地图续学正文')
    const fromPlan = setLearningDraft('计划续学正文')
    expect(consumeLearningDraft(fromPlan)).toBe('计划续学正文')
    expect(consumeLearningDraft(fromMap)).toBe('地图续学正文')
    expect(consumeLearningDraft(fromPlan)).toBe('')
  })
  it('bounds the number of pending drafts so a stale one cannot pile up', () => {
    clearLearningDraft()
    const handles = Array.from({ length: 6 }, (_, index) => setLearningDraft(`draft-${index}`))
    expect(consumeLearningDraft(handles[0])).toBe('')
    expect(consumeLearningDraft(handles[5])).toBe('draft-5')
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
