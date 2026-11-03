import { describe, it, expect } from 'vitest'
import { renderChatMarkdown } from '../markdown'

/**
 * 对话正文数学公式渲染合同。
 *
 * 背景：后端 prompt 要求模型用 `$...$` / `$$...$$` 输出公式，但前端此前只有
 * `marked`，LaTeX 被当纯文本原样吐出（用户看到 `\frac{...}{10^6}` 源码）。
 * 本轮接入 KaTeX，这组用例锁住：
 *   1. 行内 `$...$` 与块级 `$$...$$` 都真的渲染成公式（不再裸露 LaTeX）；
 *   2. 普通 Markdown 能力不退化（标题/加粗/列表/表格/代码块）；
 *   3. XSS 清洗仍然生效（KaTeX 接入不得成为新的注入通道）；
 *   4. 残缺 LaTeX 不炸掉整段正文。
 */
describe('renderChatMarkdown · 数学公式渲染', () => {
  it('把块级 $$...$$ 渲染成 KaTeX 公式，而不是裸露 LaTeX 源码', () => {
    const html = renderChatMarkdown('$$\\frac{369}{10^6}\\times 0.5$$')
    // KaTeX 块级结构存在
    expect(html).toContain('katex-display')
    expect(html).toContain('class="katex"')
    // 定界符被消费 —— 不再是裸露的 $$...$$ 文本
    // （注意：KaTeX 的 katex-mathml 内会保留原始 LaTeX 供无障碍回退，
    //   那是预期行为，故此处只断言定界符与 MathML 结构，不断言不含 \frac）
    expect(html).not.toContain('$$')
  })

  it('把行内 $...$ 渲染成公式', () => {
    const html = renderChatMarkdown('勾股定理 $a^2 + b^2 = c^2$ 成立')
    expect(html).toContain('katex')
    expect(html).not.toContain('$a^2')
  })

  it('渲染用户实际遇到的费用计算式（含千分位花括号写法）', () => {
    const md = [
      '$$\\frac{369{,}667{,}905}{10^6}\\times 0.5 + \\frac{4{,}489{,}894}{10^6}\\times 2.0$$',
      '$$= 184.83 + 8.98 = \\boxed{193.81 \\text{ 元}}$$',
    ].join('\n\n')
    const html = renderChatMarkdown(md)
    expect(html).toContain('katex-display')
    // 两个块级公式都被渲染，定界符全部被消费
    expect(html).not.toContain('$$')
    // 金额数字确实进入渲染结果（可见部分）
    expect(html).toContain('369')
    expect(html).toContain('193.81')
  })

  it('同一段正文里公式与普通文本共存', () => {
    const html = renderChatMarkdown('**结论**：设 $x = 0.02$ 元。\n\n- 第一项\n- 第二项')
    expect(html).toContain('katex')
    expect(html).toContain('<strong>结论</strong>')
    expect(html).toContain('<li>')
  })
})

describe('renderChatMarkdown · 普通 Markdown 不退化', () => {
  it('标题转 <h1>', () => {
    expect(renderChatMarkdown('# MinIO 是什么？')).toContain('<h1')
  })

  it('加粗转 <strong>', () => {
    expect(renderChatMarkdown('**高性能**对象存储')).toContain('<strong>高性能</strong>')
  })

  it('代码块保留', () => {
    const html = renderChatMarkdown('```\nminio server /data\n```')
    expect(html).toContain('<pre>')
    expect(html).toContain('minio server /data')
  })

  it('GFM 表格保留', () => {
    const html = renderChatMarkdown('| a | b |\n| --- | --- |\n| 1 | 2 |')
    expect(html).toContain('<table>')
    expect(html).toContain('<th>a</th>')
  })
})

describe('renderChatMarkdown · XSS 防护仍然生效', () => {
  it('剥掉 <script>', () => {
    const html = renderChatMarkdown('安全内容<script>alert(1)</script>')
    expect(html).not.toContain('<script')
    expect(html).not.toContain('alert(1)')
  })

  it('剥掉 <img onerror>', () => {
    const html = renderChatMarkdown('<img src=x onerror="alert(1)">正文')
    expect(html).not.toContain('onerror')
  })

  it('剥掉 javascript: 伪协议', () => {
    const html = renderChatMarkdown('[点我](javascript:alert(1))')
    expect(html).not.toContain('javascript:')
  })
})

describe('renderChatMarkdown · 健壮性', () => {
  it('空输入返回空串', () => {
    expect(renderChatMarkdown('')).toBe('')
  })

  it('残缺 LaTeX 只标记该公式，不炸掉整段正文', () => {
    const html = renderChatMarkdown('前面的正文 $\\frac{1}{$ 后面的正文')
    expect(html).toContain('前面的正文')
    expect(html).toContain('后面的正文')
  })
})
