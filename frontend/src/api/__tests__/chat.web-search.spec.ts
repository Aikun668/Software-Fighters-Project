import { describe, expect, it, vi } from 'vitest'
import { parseSSEStream, sendMessageStream } from '../chat'
import { renderChatMarkdown } from '@/utils/markdown'

const stream = (events: Record<string, unknown>[]) => new ReadableStream({
  start(controller) {
    controller.enqueue(new TextEncoder().encode(events.map(e => `data: ${JSON.stringify(e)}\n\n`).join('')))
    controller.close()
  },
})

describe('正式聊天前端：联网搜索兼容契约', () => {
  it('搜索证据不混入正文，token与partial收尾不重复，保留Java会话ID', async () => {
    const text = '查询结果。[1](https://www.python.org/downloads/)'
    const data = vi.fn(), done = vi.fn()
    await parseSSEStream(stream([
      { type: 'content', data: { search_evidence: { queries: ['公开查询'], sources: [{ snippet: '不可混入正文的摘要' }] } } },
      { type: 'token', content: text },
      { type: 'content', data: { response: text, partial: true } },
      { type: 'done', conversation_id: 42 },
    ]), data, done)
    expect(data.mock.calls.map(c => c[0]).join('')).toBe(text)
    expect(done).toHaveBeenCalledExactlyOnceWith(42)
    expect(renderChatMarkdown(text)).toContain('href="https://www.python.org/downloads/"')
  })
  it('搜索失败说明作为正文显示，不伪造来源或吞掉澄清', async () => {
    const data = vi.fn(), done = vi.fn()
    await parseSSEStream(stream([
      { type: 'inquiry', message: '你指哪场活动？请提供名称或链接。' },
      { type: 'done', conversation_id: 43 },
    ]), data, done)
    expect(data.mock.calls.map(c => c[0]).join('')).toContain('哪场活动')
    expect(done).toHaveBeenCalledExactlyOnceWith(43)
  })
  it('保留原Java聊天URL、鉴权及历史，不改成Python直连', async () => {
    localStorage.setItem('token', 'test-only-token')
    const fetchMock = vi.fn().mockResolvedValue(new Response(stream([]), { headers: { 'Content-Type': 'text/event-stream' } }))
    vi.stubGlobal('fetch', fetchMock)
    try {
      const body = { message: '最近有什么AI大会', conversation_id: 7, messages: [{ role: 'user' as const, content: '只看线上' }] }
      await sendMessageStream(body)
      const [url, options] = fetchMock.mock.calls[0]!
      expect(String(url)).toBe(`${import.meta.env.VITE_API_BASE_URL || '/api'}/chat`)
      expect(options.headers.Authorization).toBe('Bearer test-only-token')
      expect(JSON.parse(options.body)).toEqual(body)
    } finally {
      vi.unstubAllGlobals()
      localStorage.removeItem('token')
    }
  })
})

describe('SSE terminal states', () => {
  it('reports incomplete EOF rather than successful completion', async () => {
    const done = vi.fn(), error = vi.fn(), data = vi.fn()
    await parseSSEStream(stream([{ type: 'token', content: 'half answer' }]), data, done, error)
    expect(data).toHaveBeenCalledExactlyOnceWith('half answer', 'chat')
    expect(done).not.toHaveBeenCalled()
    expect(error).toHaveBeenCalledTimes(1)
  })
  it('explicit error remains one terminal callback', async () => {
    const done = vi.fn(), error = vi.fn()
    await parseSSEStream(stream([{ type: 'error', message: 'failed' }, { type: 'done' }]), vi.fn(), done, error)
    expect(done).not.toHaveBeenCalled()
    expect(error).toHaveBeenCalledTimes(1)
  })
  it('preserves AbortError identity for caller cancellation handling', async () => {
    const aborted = new DOMException('cancelled', 'AbortError')
    const done = vi.fn(), error = vi.fn()
    await parseSSEStream(new ReadableStream({ start(controller) { controller.error(aborted) } }), vi.fn(), done, error)
    expect(done).not.toHaveBeenCalled()
    expect(error).toHaveBeenCalledExactlyOnceWith(aborted)
  })
})
