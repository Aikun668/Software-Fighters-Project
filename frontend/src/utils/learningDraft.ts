// One-use handoff only. Source excerpts must never enter URLs or browser storage.
// 地图续学和计划续学会各自生成一份草稿：这里按 handle 分槽保存，避免后一份把前一份顶掉。
const pending = new Map<string, string>()
const MAX_PENDING = 4
function newHandle(): string {
  return typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('')
}
export function setLearningDraft(text: string): string {
  const handle = newHandle()
  pending.set(handle, text)
  while (pending.size > MAX_PENDING) {
    const oldest = pending.keys().next().value
    if (oldest === undefined) break
    pending.delete(oldest)
  }
  return handle
}
export function consumeLearningDraft(handle?: string): string {
  if (!pending.size || !handle) return ''
  const text = pending.get(handle)
  if (text === undefined) return ''
  pending.delete(handle)
  return text
}
export function clearLearningDraft(): void { pending.clear() }
