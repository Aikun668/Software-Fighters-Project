// One-use handoff only. Source excerpts must never enter URLs or browser storage.
let pending: { handle: string; text: string } | undefined
export function setLearningDraft(text: string): string {
  const handle = typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('')
  pending = { handle, text }
  return handle
}
export function consumeLearningDraft(handle?: string): string {
  if (!pending || !handle || pending.handle !== handle) return ''
  const text = pending.text
  pending = undefined
  return text
}
export function clearLearningDraft(): void { pending = undefined }
