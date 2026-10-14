/**
 * 端到端回归：用**真实后端 SSE 响应**驱动 parseSSEStream。
 *
 * 帧数据由 `_e2e_capture.py` 抓取（真实调用 AI 服务的出题请求），
 * 存放于仓库外 `_e2e_frames.json`（存在时才跑，避免 CI 因缺文件而失败）。
 *
 * 这组用例锁住的是**真实契约**而非构造数据：出题中心确实不发 token，
 * 正文只能来自收尾 partial 帧。
 */
import { describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { parseSSEStream } from '../chat'

const FRAME_FILE = resolve(__dirname, '../../../../../_e2e_frames.json')
const hasFrames = existsSync(FRAME_FILE)

const streamOfText = (text: string) => {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(text))
      controller.close()
    },
  })
}

describe.runIf(hasFrames)('端到端：真实出题响应必须产出可见正文', () => {
  const chunks: string[] = []

  it('解析真实响应后正文非空，且包含题目与答案', async () => {
    const raw = readFileSync(FRAME_FILE, 'utf-8')
    const onDone = () => {}

    await parseSSEStream(
      streamOfText(raw),
      (delta) => chunks.push(delta),
      onDone,
    )

    const text = chunks.join('')
    // 核心断言：这正是修复前会失败的场景（修复前 text 为空 → 前端显示"后端没有返回任何内容"）
    expect(text.length).toBeGreaterThan(0)
    expect(text).toContain('第 1 题')
    expect(text).toContain('**答案：**')
  })

  it('真实响应里确实没有 token 帧（证明 partial 帧是唯一正文）', () => {
    const raw = readFileSync(FRAME_FILE, 'utf-8')
    const hasToken = raw
      .split('\n\n')
      .some((blk) => blk.trim().startsWith('data:') && blk.includes('"type": "token"'))
    expect(hasToken).toBe(false)
  })
})
