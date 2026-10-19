import { describe, it, expect } from 'vitest'
import { renderChatMarkdown } from '../markdown'

/**
 * T001 回归合同：行内公式 `$n$` 与 CJK 紧邻加粗 `**…**` 必须渲染，
 * 不得以源码字符出现；流式残缺态不得炸整段正文，补全后必须重新渲染。
 */
describe('行内单字母公式 $n$ 必须渲染（假设1：货币转义误伤）', () => {
  it('单个 $n$ 渲染成公式', () => {
    const html = renderChatMarkdown('设 $n$ 为样本数')
    expect(html).toContain('katex')
    expect(html).not.toContain('$n$')
  })

  it('$k$ 与 $p$ 混排（真实回归：第二个 $ 残留）', () => {
    const html = renderChatMarkdown('令 $k$ 表示层数，$p$ 为概率')
    expect(html).toContain('katex')
    expect(html).not.toContain('$k$')
    expect(html).not.toContain('$p$')
  })

  it('$n$ 与 $m$ 并列', () => {
    const html = renderChatMarkdown('设 $n$ 和 $m$ 的和')
    expect(html.match(/class="katex"/g)?.length).toBe(2)
  })

  it('下标公式 $x_i$ 与 $x_{i+1}$ 仍渲染（守卫）', () => {
    const html = renderChatMarkdown('输入 $x_i$ 与 $x_{i+1}$ 的关系')
    expect(html.match(/class="katex"/g)?.length).toBe(2)
  })

  it('单字母公式与货币共存：货币保留字面，字母公式渲染', () => {
    const html = renderChatMarkdown('价格 $0.02，设 $n$ 个')
    expect(html).toContain('$0.02')
    expect(html.match(/class="katex"/g)?.length).toBe(1)
  })

  it('含空格的英文货币不得被误判为公式', () => {
    const html = renderChatMarkdown('闲时 $0.02 and 高峰 $0.04')
    expect(html).not.toContain('katex')
    expect(html).toContain('$0.02')
  })

  it('两个货币之间夹着加粗时，加粗不得被吞进公式（假设3：* 误判为运算符）', () => {
    const html = renderChatMarkdown('单价 $0.02 **注意** 费用 $0.04')
    expect(html).not.toContain('katex')
    expect(html).toContain('<strong>注意</strong>')
    expect(html).toContain('$0.02')
    expect(html).toContain('$0.04')
  })
})

describe('CJK 紧邻加粗必须渲染（假设2：CommonMark 左右翼判定）', () => {
  it('闭合 ** 前为中文全角冒号时仍加粗', () => {
    const html = renderChatMarkdown('**注意：**这是重点')
    expect(html).toContain('<strong>注意：</strong>这是重点')
    expect(html).not.toContain('**')
  })

  it('闭合 ** 前为句号时仍加粗', () => {
    const html = renderChatMarkdown('**重点。**这是结论')
    expect(html).toContain('<strong>重点。</strong>这是结论')
  })

  it('中文夹 **token** 仍加粗（守卫）', () => {
    expect(renderChatMarkdown('中文**token**中文')).toContain('<strong>token</strong>')
  })

  it('全角括号内加粗（守卫）', () => {
    expect(renderChatMarkdown('（**token**）是关键')).toContain('<strong>token</strong>')
  })

  it('加粗内容含 XSS 载荷仍被清洗', () => {
    const html = renderChatMarkdown('**<img src=x onerror="alert(1)">**正文')
    expect(html).not.toContain('onerror')
  })

  it('代码块中的 ** 不被加粗', () => {
    const html = renderChatMarkdown('`a**b**c` 文本')
    expect(html).not.toContain('<strong>b</strong>')
  })
})

describe('流式残缺态 → 完成态重渲染（假设4）', () => {
  it('残缺加粗不加粗，补全后加粗', () => {
    const partial = renderChatMarkdown('结论 **token 还没闭')
    expect(partial).not.toContain('<strong>')
    const full = renderChatMarkdown('结论 **token 还没闭合**')
    expect(full).toContain('<strong>token 还没闭合</strong>')
  })

  it('残缺公式不抛异常，已完整的公式照常渲染', () => {
    const html = renderChatMarkdown('设 $n$ 为样本，计算 $\\frac{1}{')
    expect(html).toContain('katex')
    expect(html).toContain('计算')
  })

  it('流式逐段增长：每个前缀都不抛异常', () => {
    const full = '设 $n$ 为 **样本数**，公式 $x_i$ 成立。'
    for (let i = 1; i <= full.length; i++) {
      expect(() => renderChatMarkdown(full.slice(0, i))).not.toThrow()
    }
    expect(renderChatMarkdown(full)).toContain('<strong>样本数</strong>')
  })
})
