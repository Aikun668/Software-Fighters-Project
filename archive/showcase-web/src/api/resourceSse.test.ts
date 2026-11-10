import { afterEach, describe, expect, it, vi } from 'vitest'

import { generateResource } from './resourceSse'
import type { ResourceRequest, SseEvent } from '@/types/resource'

const request: ResourceRequest = {
  topic: 'Transformer 自注意力',
  resource_type: 'document',
}

function mockFetchWithChunks(chunks: string[], ok = true): void {
  const encoded = chunks.map((chunk) => new TextEncoder().encode(chunk))
  let index = 0
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index >= encoded.length) {
        controller.close()
        return
      }
      controller.enqueue(encoded[index])
      index += 1
    },
  })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok, status: ok ? 200 : 503, body }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('generateResource', () => {
  it('parses an SSE event split across stream chunks', async () => {
    mockFetchWithChunks([
      'data: {"type":"stage_start","stage":"generate"',
      ',"message":"正在生成"}\n\n',
      'data: {"type":"done","data":{"content_blocks":[],"review_status":"pass",',
      '"repair_attempted":false,"fallback_used":false,"final_status":"success"}}\n\n',
    ])
    const events: SseEvent[] = []

    const result = await generateResource(request, (event) => events.push(event))

    expect(events[0]).toMatchObject({ type: 'stage_start', stage: 'generate' })
    expect(result.final_status).toBe('success')
    expect(fetch).toHaveBeenCalledWith('/ai-api/resources/generate', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        topic: request.topic,
        resource_type: request.resource_type,
        user_id: 1,
        student_profile: {},
      }),
    }))
  })

  it('throws when the stream ends before a done event', async () => {
    mockFetchWithChunks(['data: {"type":"stage_start","stage":"plan"}\n\n'])

    await expect(generateResource(request, () => undefined))
      .rejects.toThrow('生成过程未正常结束')
  })

  it('throws a user-readable error for a non-success response', async () => {
    mockFetchWithChunks([], false)

    await expect(generateResource(request, () => undefined))
      .rejects.toThrow('资源生成服务暂不可用')
  })

  it('throws when an SSE data line is invalid JSON', async () => {
    mockFetchWithChunks(['data: not-json\n\n'])

    await expect(generateResource(request, () => undefined))
      .rejects.toThrow('资源生成数据格式错误')
  })
})
