/**
 * T004 合同：`renderChatMarkdown` 渲染前剥离**合法**的 ```ui-block 围栏。
 *
 * 背景：后端只在最终正文下发前抽取围栏转成 visualization 事件，token 流式
 * 期间与 partial 帧被跳过时正文会有围栏残留（T006 确认的结构性问题），
 * 渲染层剥离一劳永逸。
 *
 * 关键约束（与后端 visualization_blocks.py 的"失败不吞正文"一致）：
 * - 只剥离"JSON 可解析 + schema 校验 + 类型/版本已注册 + props 合法"的围栏
 *   ——恰好等于后端会为之发事件的围栏；
 * - 非法围栏（JSON 坏 / 校验不过 / 类型未注册）**原样保留**，用户至少看到
 *   一段 JSON 代码块，不会凭空丢内容；
 * - 普通代码块（其他 info string）完全不受影响。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { renderChatMarkdown, stripValidUiBlockFences } from '../markdown'
import { dispatchUiBlock } from '@/components/chat/ui-blocks/registry'

const VALID_FENCE =
  '```ui-block\n{"type":"attention_matrix","version":1,"props":{"tokenCount":5,"mode":"causal"}}\n```'

const fenceWith = (body: string) => '```ui-block\n' + body + '\n```'

describe('stripValidUiBlockFences：合法围栏剥离', () => {
  it('合法 attention_matrix v1 围栏被整体剥离，前后文保留', () => {
    const text = `先讲概念。\n\n${VALID_FENCE}\n\n再讲应用。`
    const stripped = stripValidUiBlockFences(text)

    expect(stripped).not.toContain('ui-block')
    expect(stripped).not.toContain('attention_matrix')
    expect(stripped).toContain('先讲概念。')
    expect(stripped).toContain('再讲应用。')
  })

  it('带 labels 的合法围栏也被剥离（校验覆盖可选字段）', () => {
    const fence = fenceWith(
      '{"type":"attention_matrix","version":1,"props":{"tokenCount":3,"mode":"bidirectional","queryLabels":["a","b","c"]}}',
    )
    expect(stripValidUiBlockFences(`正文\n\n${fence}\n\n结尾`)).not.toContain('attention_matrix')
  })

  it('合法 conv_window v1 围栏被剥离（含省略 stride 与显式 stride 两种）', () => {
    const noStride = fenceWith(
      '{"type":"conv_window","version":1,"props":{"inputRows":5,"inputCols":5,"kernelSize":3}}',
    )
    const withStride = fenceWith(
      '{"type":"conv_window","version":1,"props":{"inputRows":6,"inputCols":8,"kernelSize":2,"stride":2}}',
    )
    const stripped = stripValidUiBlockFences(`正文\n\n${noStride}\n\n中间\n\n${withStride}\n\n结尾`)
    expect(stripped).not.toContain('conv_window')
    expect(stripped).not.toContain('ui-block')
    expect(stripped).toContain('正文')
    expect(stripped).toContain('结尾')
  })

  it('多个围栏全部处理：合法的剥离、非法的保留', () => {
    const bad = fenceWith('{"type":"attention_matrix","version":1,"props":{"tokenCount":5,"mode":"causal","weights":[[1]]}}')
    const text = `开头\n\n${VALID_FENCE}\n\n中间\n\n${bad}\n\n结尾`
    const stripped = stripValidUiBlockFences(text)

    expect(stripped).toContain('开头')
    expect(stripped).toContain('中间')
    expect(stripped).toContain('结尾')
    // 合法的没了、非法的（含 weights）原样保留
    expect(stripped.match(/```ui-block/g)).toHaveLength(1)
    expect(stripped).toContain('weights')
  })
})

describe('stripValidUiBlockFences：非法围栏必须原样保留（失败不吞正文）', () => {
  it('JSON 解析失败的围栏保留', () => {
    const text = `正文\n\n${fenceWith('{oops 不是 JSON')}\n\n结尾`
    expect(stripValidUiBlockFences(text)).toBe(text)
  })

  it('props 含 weights（D-007）的围栏保留', () => {
    const fence = fenceWith(
      '{"type":"attention_matrix","version":1,"props":{"tokenCount":5,"mode":"causal","weights":[[1]]}}',
    )
    const text = `正文\n\n${fence}\n\n结尾`
    expect(stripValidUiBlockFences(text)).toBe(text)
  })

  it('未注册类型的围栏保留（后端同样不会为它发事件）', () => {
    const fence = fenceWith('{"type":"pie_chart","version":1,"props":{"slices":3}}')
    const text = `正文\n\n${fence}\n\n结尾`
    expect(stripValidUiBlockFences(text)).toBe(text)
  })

  it('未注册版本的围栏保留', () => {
    const fence = fenceWith('{"type":"attention_matrix","version":2,"props":{"tokenCount":5,"mode":"causal"}}')
    const text = `正文\n\n${fence}\n\n结尾`
    expect(stripValidUiBlockFences(text)).toBe(text)
  })

  it('envelope 非法（含未知字段）的围栏保留', () => {
    const fence = fenceWith(
      '{"type":"attention_matrix","version":1,"props":{"tokenCount":5,"mode":"causal"},"extra":1}',
    )
    const text = `正文\n\n${fence}\n\n结尾`
    expect(stripValidUiBlockFences(text)).toBe(text)
  })
})

describe('stripValidUiBlockFences：无围栏与普通代码块', () => {
  it('无围栏文本原样返回', () => {
    const text = '# 标题\n\n普通段落 $x^2$ 与 **加粗**。'
    expect(stripValidUiBlockFences(text)).toBe(text)
  })

  it('普通代码块（无 info string）不受影响', () => {
    const text = '```\nminio server /data\n```'
    expect(stripValidUiBlockFences(text)).toBe(text)
  })

  it('普通代码块（其他 info string）不受影响', () => {
    const text = '```python\nprint("hi")\n```'
    expect(stripValidUiBlockFences(text)).toBe(text)
  })

  it('info string 多了后缀的围栏不算 ui-block（口径：恰为 ui-block）', () => {
    const text = '```ui-block-extra\n{"type":"attention_matrix","version":1,"props":{}}\n```'
    expect(stripValidUiBlockFences(text)).toBe(text)
  })

  it('空字符串原样返回', () => {
    expect(stripValidUiBlockFences('')).toBe('')
  })
})

describe('renderChatMarkdown：围栏剥离接入渲染入口', () => {
  it('合法围栏不渲染成代码块，正文照常渲染', () => {
    const html = renderChatMarkdown(`## 注意力机制\n\n${VALID_FENCE}\n\n见上图。`)

    expect(html).toContain('<h2>注意力机制</h2>')
    expect(html).toContain('见上图。')
    expect(html).not.toContain('attention_matrix')
    expect(html).not.toContain('ui-block')
  })

  it('非法围栏保留为普通代码块（不吞正文）', () => {
    const fence = fenceWith('not-json')
    const html = renderChatMarkdown(`正文前\n\n${fence}\n\n正文后`)

    expect(html).toContain('正文前')
    expect(html).toContain('正文后')
    // 围栏内容作为代码块可见
    expect(html).toContain('not-json')
  })
})

/**
 * 三端同步守卫（D-014）：同一批契约 fixtures 分别过三个注册表，结论必须一致——
 * 1. 后端 parse_ui_block（test_ui_block_contract.py）
 * 2. 前端 registry（contract.spec.ts 的 dispatchUiBlock）
 * 3. 渲染层兜底剥离（本文件的 stripValidUiBlockFences）
 *
 * 不变量：block 校验 ok=true ⇒ 包进围栏必被渲染层剥离（否则正文残留裸 JSON）；
 * ok=false ⇒ 围栏保留。历史上 conv_window 曾漏注册渲染层映射导致裸 JSON
 * 留在正文（2026-10-20 真机事故），此守卫防止再次漂移。
 */
describe('三端同步守卫：fixtures 驱动的渲染层剥离', () => {
  const fixturePath = resolve(
    process.cwd(),
    '../ai-service/tests/fixtures/ui_block_contract.json',
  )
  const fixtures: { name: string; ok: boolean; block: unknown }[] = JSON.parse(
    readFileSync(fixturePath, 'utf-8'),
  ).fixtures

  it.each(fixtures)('$name：剥离结论与 registry/后端一致', ({ ok, block }) => {
    // registry 结论必须先对齐（与 contract.spec.ts 同一断言，双保险）
    expect(dispatchUiBlock(block).ok).toBe(ok)

    const text = `正文前。\n\n${fenceWith(JSON.stringify(block))}\n\n正文后。`
    const stripped = stripValidUiBlockFences(text)
    if (ok) {
      expect(stripped).not.toContain('```ui-block')
      expect(stripped).toContain('正文前。')
      expect(stripped).toContain('正文后。')
    } else {
      expect(stripped).toContain('```ui-block')
    }
  })
})
