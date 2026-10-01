/**
 * `parseSSEStream` 阶段 D 合同：`progress` 帧（执行进度）的解析边界。
 *
 * 关键约束：进度帧**只**驱动进度回调，**绝不可**进入正文（`onData`）——
 * 否则前端会把「正在执行 extract」当成答案正文渲染。
 */
import { describe, expect, it, vi } from 'vitest'

import { parseSSEStream } from '../chat'

const streamOf = (...frames: string[]) => {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const frame of frames) controller.enqueue(encoder.encode(frame))
      controller.close()
    },
  })
}

const frame = (payload: Record<string, unknown>) =>
  `data: ${JSON.stringify(payload)}\n\n`

describe('parseSSEStream 阶段 D 合同：progress 帧', () => {
  it('progress 帧走 onProgress，正文仍只来自 token', async () => {
    const onData = vi.fn()
    const onDone = vi.fn()
    const onProgress = vi.fn()

    await parseSSEStream(
      streamOf(
        frame({
          type: 'progress',
          stage: 'extract',
          message: '正在执行 extract',
          data: { node: 'extract', phase: 'started' },
        }),
        frame({ type: 'token', content: '正' }),
        frame({ type: 'token', content: '文' }),
        frame({ type: 'done', data: { summary: 'ok' } }),
      ),
      onData,
      onDone,
      undefined,
      onProgress,
    )

    expect(onProgress).toHaveBeenCalledTimes(1)
    expect(onProgress).toHaveBeenCalledWith({
      stage: 'extract',
      message: '正在执行 extract',
      phase: 'started',
    })
    // 正文帧逐字且顺序不变
    expect(onData.mock.calls.map((call) => call[0])).toEqual(['正', '文'])
    expect(onDone).toHaveBeenCalledTimes(1)
  })

  it('done 帧把 conversation_id 传给完成回调', async () => {
    const onDone = vi.fn()

    await parseSSEStream(
      streamOf(frame({ type: 'done', conversation_id: 22 })),
      vi.fn(),
      onDone,
    )

    expect(onDone).toHaveBeenCalledWith(22)
  })

  it('未传 onProgress 时，progress 帧被静默忽略（不得混入正文）', async () => {
    const onData = vi.fn()

    await parseSSEStream(
      streamOf(
        frame({
          type: 'progress',
          stage: 'merge',
          message: '正在执行 merge',
          data: { phase: 'started' },
        }),
        frame({ type: 'token', content: '答' }),
        frame({ type: 'done' }),
      ),
      onData,
      vi.fn(),
    )

    expect(onData.mock.calls.map((call) => call[0])).toEqual(['答'])
  })
})
