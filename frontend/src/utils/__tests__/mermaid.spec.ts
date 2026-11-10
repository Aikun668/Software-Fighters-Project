import { describe, expect, it, vi } from 'vitest'

/**
 * mermaid 代码块渲染（FINAL 用户需求：AI 返回的 mindmap 渲染不出来）。
 *
 * mermaid 本体在 jsdom 里渲染 SVG 依赖布局，太重且不稳定；
 * 这里 mock 掉 mermaid 本体，验证「替换行为」：识别 mermaid 块、幂等、非 mermaid 跳过。
 */
const mermaidRenderMock = vi.fn(async (_id: string, code: string) => ({
  svg: `<svg data-code="${encodeURIComponent(code.slice(0, 12))}"></svg>`,
  bindFunction: undefined,
}))

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: (...args: [string, string]) => mermaidRenderMock(...args),
  },
}))

import { renderMermaidBlocks } from '../../utils/mermaid'

const mount = (html: string) => {
  const div = document.createElement('div')
  div.innerHTML = html
  return div
}

describe('renderMermaidBlocks', () => {
  it('把 language-mermaid 代码块替换成 SVG', async () => {
    const el = mount('<pre><code class="language-mermaid">mindmap\n  root((主题))</code></pre>')
    await renderMermaidBlocks(el)
    expect(el.querySelector('.mermaid-figure')).not.toBeNull()
    expect(el.querySelector('pre')).toBeNull()
    expect(mermaidRenderMock).toHaveBeenCalled()
  })

  it('幂等：已渲染的块不再二次处理', async () => {
    const el = mount('<pre><code class="language-mermaid">flowchart TD</code></pre>')
    await renderMermaidBlocks(el)
    const count = el.querySelectorAll('.mermaid-figure').length
    await renderMermaidBlocks(el)
    expect(el.querySelectorAll('.mermaid-figure')).toHaveLength(count)
  })

  it('非 mermaid 语言块不处理', async () => {
    const el = mount('<pre><code class="language-python">print(1)</code></pre>')
    await renderMermaidBlocks(el)
    expect(el.querySelector('pre')).not.toBeNull()
    expect(el.querySelector('.mermaid-figure')).toBeNull()
  })

  it('容器为空/无匹配时安全返回', async () => {
    await expect(renderMermaidBlocks(null)).resolves.toBeUndefined()
    const empty = document.createElement('div')
    await expect(renderMermaidBlocks(empty)).resolves.toBeUndefined()
  })
})
