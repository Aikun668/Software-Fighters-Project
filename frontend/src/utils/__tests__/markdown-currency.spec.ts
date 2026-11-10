import { describe, it, expect } from 'vitest'
import { renderChatMarkdown, escapeCurrencyDollars } from '../markdown'

/**
 * 「美元金额 vs 行内公式」消歧合同。
 *
 * 背景：后端要求行内公式用 `$...$`，但本产品正文同时大量出现美元金额
 * （`$0.02`、`$0.0348/M`）。若直接开 `singleDollarTextMath`，相邻两个
 * 金额会被当作一段公式吞掉（`闲时 $0.02，高峰 $0.04` → 公式）。
 *
 * 消歧规则（保守优先）：
 *   - 像公式（含 LaTeX 命令/上下标/分组，或 + - * = < > 运算符）→ 渲染成公式；
 *   - 像货币（纯数字/千分位/带单位）→ 保留字面 `$`，不得被吞；
 *   - 代码围栏/行内代码内的 `$` 一律不得转义或渲染。
 *
 * 有意的取舍：`$0.02$` 这种"纯数字公式"会被判为货币而保持字面 ——
 * 宁可让这类写法不退化为公式，也不能把货币文本吞进公式（后者破坏正文语义）。
 */
describe('美元金额不得被误判为公式', () => {
  it('单个美元金额保持字面（不被当公式）', () => {
    const html = renderChatMarkdown('价格是 $0.02 元')
    expect(html).not.toContain('katex')
    expect(html).toContain('$0.02')
  })

  it('相邻两个美元金额不得被吞成一段公式（真实回归场景）', () => {
    const html = renderChatMarkdown('闲时 $0.02，高峰 $0.04')
    expect(html).not.toContain('katex')
    expect(html).toContain('$0.02')
    expect(html).toContain('$0.04')
    expect(html).toContain('闲时')
    expect(html).toContain('高峰')
  })

  it('货币与人民币混排不被吞', () => {
    const html = renderChatMarkdown('官方 ¥0.02，第三方 $0.003')
    expect(html).not.toContain('katex')
    expect(html).toContain('$0.003')
  })

  it('带 /M 单位的美元单价不被吞（每百万 tokens 写法）', () => {
    const html = renderChatMarkdown('输入 $0.0348/M，输出 $0.1392/M')
    expect(html).not.toContain('katex')
    expect(html).toContain('$0.0348/M')
    expect(html).toContain('$0.1392/M')
  })

  it('普通句子里的多个 $ 不被吞', () => {
    const html = renderChatMarkdown('花了 $100 买了书，还剩 $50')
    expect(html).not.toContain('katex')
    expect(html).toContain('$100')
    expect(html).toContain('$50')
  })

  it('纯数字包裹（$0.02$）按取舍保持字面，不退化为公式', () => {
    const html = renderChatMarkdown('单价 $0.02$ 元')
    expect(html).not.toContain('katex')
    expect(html).toContain('0.02')
  })
})

describe('真实公式仍然渲染', () => {
  it('LaTeX 命令式行内公式渲染', () => {
    const html = renderChatMarkdown('勾股定理 $a^2+b^2=c^2$ 成立')
    expect(html).toContain('katex')
    expect(html).not.toContain('$a^2')
  })

  it('带 LaTeX 命令的行内公式渲染', () => {
    const html = renderChatMarkdown('单价为 $\\frac{0.04}{2}$ 元')
    expect(html).toContain('katex')
  })

  it('简单运算符行内公式渲染', () => {
    const html = renderChatMarkdown('结果是 $1 + 2$ 吗')
    expect(html).toContain('katex')
  })

  it('块级公式渲染', () => {
    const html = renderChatMarkdown('$$\\frac{a}{b}$$')
    expect(html).toContain('katex-display')
  })

  it('货币与公式在同一段共存，互不干扰', () => {
    const html = renderChatMarkdown('缓存命中 $0.02 元，计算式 $\\frac{1}{2}$ 如下')
    expect(html).toContain('$0.02')     // 货币保留字面
    expect(html).toContain('katex')     // 公式渲染
  })
})

describe('代码块内的 $ 不得被转义或当公式', () => {
  it('行内代码里的 $HOME 保持原样', () => {
    const html = renderChatMarkdown('命令 `echo $HOME` 输出路径')
    expect(html).not.toContain('katex')
    expect(html).toContain('$HOME')
    expect(html).not.toContain('\\$HOME')
  })

  it('代码围栏里的 $ 保持原样', () => {
    const html = renderChatMarkdown('```bash\necho $PATH\nexport A=$B\n```')
    expect(html).not.toContain('katex')
    expect(html).toContain('$PATH')
    expect(html).toContain('$B')
  })
})

describe('escapeCurrencyDollars 纯函数', () => {
  it('成对货币按字面转义', () => {
    // 两个 $ 配对、内容为纯数字 → 判为货币 → 转义
    expect(escapeCurrencyDollars('$0.02$ 与 $0.04$')).toContain('\\$0.02\\$')
  })

  it('单个 $ 不构成配对，保持原样', () => {
    expect(escapeCurrencyDollars('价格是 $0.02 元')).toBe('价格是 $0.02 元')
  })

  it('公式原样保留', () => {
    expect(escapeCurrencyDollars('$a^2$')).toBe('$a^2$')
  })

  it('空输入安全', () => {
    expect(escapeCurrencyDollars('')).toBe('')
  })
})
