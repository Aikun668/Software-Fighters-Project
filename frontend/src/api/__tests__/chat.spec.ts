/**
 * `parseSSEStream` 阶段 D 合同：`progress` 帧（执行进度）的解析边界。
 *
 * 关键约束：进度帧**只**驱动进度回调，**绝不可**进入正文（`onData`）——
 * 否则前端会把「正在执行 extract」当成答案正文渲染。
 */
import { describe, expect, it, vi } from 'vitest'

import { parseSSEStream } from '../chat'
import AttentionMatrix from '../../components/chat/AttentionMatrix.vue'

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

/**
 * 收尾 content 帧（partial=true）的渲染边界。
 *
 * 背景（本轮修复）：该帧此前被**无条件跳过**，理由是「token 流已逐字送完，
 * 再渲染会重复」。但后端只有 auto/tutor 路径发 token，出题 / 计划 / 资源等
 * 中心**不发 token**，其收尾帧是唯一正文载体——一律跳过的后果是这些功能
 * 整轮空白，用户看到"后端没有返回任何内容"。
 *
 * 正确语义：**已送出过正文才跳过**（防重复）；否则必须渲染。
 */
describe('parseSSEStream 合同：partial 收尾帧不得吞掉唯一正文', () => {
  const partialFrame = (data: Record<string, unknown>) =>
    frame({ type: 'content', mode: 'exercise', data: { ...data, partial: true } })

  it('无 token 流时，partial 帧必须渲染（出题中心场景）', async () => {
    const onData = vi.fn()

    await parseSSEStream(
      streamOf(
        partialFrame({ response: '已为你生成 2 道练习题。', questions: [] }),
        frame({ type: 'done' }),
      ),
      onData,
      vi.fn(),
    )

    expect(onData).toHaveBeenCalledTimes(1)
    expect(onData.mock.calls[0][0]).toContain('已为你生成 2 道练习题。')
  })

  it('已送出 token 时，partial 帧仍被跳过（防重复，原行为不变）', async () => {
    const onData = vi.fn()

    await parseSSEStream(
      streamOf(
        frame({ type: 'token', content: '完整' }),
        frame({ type: 'token', content: '答案' }),
        partialFrame({ response: '完整答案' }),
        frame({ type: 'done' }),
      ),
      onData,
      vi.fn(),
    )

    expect(onData.mock.calls.map((call) => call[0])).toEqual(['完整', '答案'])
  })

  it('结构化 questions 被渲染成 Markdown（题目 + 选项 + 答案）', async () => {
    const onData = vi.fn()

    await parseSSEStream(
      streamOf(
        partialFrame({
          response: '已为你生成 1 道练习题。',
          questions: [
            {
              question_type: 'choice',
              question: 'He had no choice but to ______ his statement.',
              options: { A: 'retract', B: 'repeal', C: 'refute', D: 'renounce' },
              correct_answer: 'A',
              explanation: 'retract 用于收回说过的话。',
            },
          ],
        }),
        frame({ type: 'done' }),
      ),
      onData,
      vi.fn(),
    )

    const text = onData.mock.calls[0][0] as string
    // 题干与选项
    expect(text).toContain('第 1 题')
    expect(text).toContain('He had no choice but to ______ his statement.')
    expect(text).toContain('**A.** retract')
    expect(text).toContain('**D.** renounce')
    // 答案与解析
    expect(text).toContain('**答案：** A')
    expect(text).toContain('retract 用于收回说过的话。')
  })

  it('简答题（options 为 null）不产生空选项行', async () => {
    const onData = vi.fn()

    await parseSSEStream(
      streamOf(
        partialFrame({
          questions: [
            {
              question_type: 'short_answer',
              question: '请解释 attention residue。',
              options: null,
              correct_answer: '注意力残留。',
            },
          ],
        }),
        frame({ type: 'done' }),
      ),
      onData,
      vi.fn(),
    )

    const text = onData.mock.calls[0][0] as string
    expect(text).toContain('请解释 attention residue。')
    expect(text).toContain('**答案：** 注意力残留。')
    expect(text).not.toContain('null')
    expect(text).not.toContain('undefined')
  })

  it('无结构化产物时回落到 response 纯文本', async () => {
    const onData = vi.fn()

    await parseSSEStream(
      streamOf(partialFrame({ response: '已为你生成学习计划，共 3 步。' }), frame({ type: 'done' })),
      onData,
      vi.fn(),
    )

    expect(onData.mock.calls[0][0]).toBe('已为你生成学习计划，共 3 步。')
  })
})

/**
 * T004 合同：`visualization` 帧（结构化 UI block）的解析边界。
 *
 * 事件形状（后端 events/types.py 的 to_sse）：`{type:'visualization', data:{type,version,props}}`。
 * 关键约束（与 progress 同理）：
 * - 只驱动 onVisualization 回调，**绝不混入正文**（onData）；
 * - 经 dispatchUiBlock 完整校验：合法 → 上层拿到 {ok:true, component, props}；
 *   非法 → 上层拿到 {ok:false, error}（轻量降级提示），不抛异常、不影响正文。
 */
describe('parseSSEStream T004 合同：visualization 帧', () => {
  const validBlock = { type: 'attention_matrix', version: 1, props: { tokenCount: 5, mode: 'causal' } }

  it('合法 block → onVisualization 收到组件与规范化 props，正文不受影响', async () => {
    const onData = vi.fn()
    const onVisualization = vi.fn()

    await parseSSEStream(
      streamOf(
        frame({ type: 'token', content: '先看图：' }),
        frame({ type: 'visualization', data: validBlock }),
        frame({ type: 'done' }),
      ),
      onData,
      vi.fn(),
      undefined,
      undefined,
      onVisualization,
    )

    expect(onVisualization).toHaveBeenCalledTimes(1)
    expect(onVisualization).toHaveBeenCalledWith({
      ok: true,
      component: AttentionMatrix,
      props: { tokenCount: 5, mode: 'causal' },
    })
    // 正文只来自 token，block 不得混入
    expect(onData.mock.calls.map((call) => call[0])).toEqual(['先看图：'])
  })

  it('非法 block（props 含 weights，D-007）→ 降级结果交给上层，不抛异常', async () => {
    const onData = vi.fn()
    const onVisualization = vi.fn()

    await expect(
      parseSSEStream(
        streamOf(
          frame({
            type: 'visualization',
            data: { ...validBlock, props: { tokenCount: 5, mode: 'causal', weights: [[1]] } },
          }),
          frame({ type: 'done' }),
        ),
        onData,
        vi.fn(),
        undefined,
        undefined,
        onVisualization,
      ),
    ).resolves.toBeUndefined()

    expect(onVisualization).toHaveBeenCalledTimes(1)
    const block = onVisualization.mock.calls[0][0] as { ok: boolean; error?: string }
    expect(block.ok).toBe(false)
    expect(block.error).toContain('weights')
    expect(onData).not.toHaveBeenCalled()
  })

  it('非法 block（未注册类型）→ 降级结果交给上层，正文回调不受影响', async () => {
    const onData = vi.fn()
    const onVisualization = vi.fn()

    await parseSSEStream(
      streamOf(
        frame({ type: 'token', content: '正文' }),
        frame({ type: 'visualization', data: { type: 'pie_chart', version: 1, props: {} } }),
        frame({ type: 'done' }),
      ),
      onData,
      vi.fn(),
      undefined,
      undefined,
      onVisualization,
    )

    const block = onVisualization.mock.calls[0][0] as { ok: boolean; error?: string }
    expect(block.ok).toBe(false)
    expect(block.error).toContain('pie_chart')
    expect(onData.mock.calls.map((call) => call[0])).toEqual(['正文'])
  })

  it('事件残缺（data 缺失）→ 降级为 {ok:false}，流不中断', async () => {
    const onData = vi.fn()
    const onDone = vi.fn()
    const onVisualization = vi.fn()

    await parseSSEStream(
      streamOf(
        frame({ type: 'visualization' }),
        frame({ type: 'token', content: '正文照常' }),
        frame({ type: 'done', conversation_id: 9 }),
      ),
      onData,
      onDone,
      undefined,
      undefined,
      onVisualization,
    )

    const block = onVisualization.mock.calls[0][0] as { ok: boolean }
    expect(block.ok).toBe(false)
    expect(onData.mock.calls.map((call) => call[0])).toEqual(['正文照常'])
    expect(onDone).toHaveBeenCalledWith(9)
  })

  it('未传 onVisualization 时，visualization 帧被静默忽略（不得混入正文）', async () => {
    const onData = vi.fn()

    await parseSSEStream(
      streamOf(
        frame({ type: 'visualization', data: validBlock }),
        frame({ type: 'token', content: '答' }),
        frame({ type: 'done' }),
      ),
      onData,
      vi.fn(),
    )

    expect(onData.mock.calls.map((call) => call[0])).toEqual(['答'])
  })
})
