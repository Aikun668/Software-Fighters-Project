import type { DonePayload, ResourceRequest, SseEvent } from '@/types/resource'

type EventHandler = (event: SseEvent) => void

function parseFrame(frame: string, onEvent: EventHandler): DonePayload | null {
  let donePayload: DonePayload | null = null

  for (const line of frame.split(/\r?\n/)) {
    if (!line.startsWith('data:')) continue
    const rawData = line.slice('data:'.length).trim()
    if (!rawData) continue

    let event: SseEvent
    try {
      event = JSON.parse(rawData) as SseEvent
    } catch {
      throw new Error('资源生成数据格式错误')
    }

    onEvent(event)
    if (event.type === 'done') {
      donePayload = (event.data ?? null) as DonePayload | null
    }
  }

  return donePayload
}

export async function generateResource(
  request: ResourceRequest,
  onEvent: EventHandler,
  signal?: AbortSignal,
): Promise<DonePayload> {
  const response = await fetch('/ai-api/resources/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      topic: request.topic.trim(),
      resource_type: request.resource_type,
      user_id: 1,
      student_profile: {},
    }),
    signal,
  })

  if (!response.ok || !response.body) {
    throw new Error('资源生成服务暂不可用')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let donePayload: DonePayload | null = null

  while (true) {
    const read = await reader.read()
    buffer += decoder.decode(read.value ?? new Uint8Array(), { stream: !read.done })

    const frames = buffer.split(/\r?\n\r?\n/)
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      donePayload = parseFrame(frame, onEvent) ?? donePayload
    }

    if (read.done) break
  }

  buffer += decoder.decode()
  if (buffer.trim()) {
    donePayload = parseFrame(buffer, onEvent) ?? donePayload
  }

  if (!donePayload) {
    throw new Error('生成过程未正常结束')
  }

  return donePayload
}
