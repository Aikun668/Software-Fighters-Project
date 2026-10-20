/**
 * 对话正文 Markdown 统一渲染（含数学公式 KaTeX）。
 *
 * 背景（本轮定位到的缺陷）：后端 `tutor_agent/system.yaml` 明确要求模型
 * 「回答中有公式时使用 $...$ 或 $$...$$ 包裹」，但前端此前只有 `marked`，
 * 没有任何数学渲染能力 —— LaTeX 被当作普通文本原样输出，用户看到的是
 * `\frac{369{,}667{,}905}{10^6}` 这种源码而不是公式。
 *
 * 本模块是对话正文渲染的**单一入口**，供 ChatThread / AITutor / ProfileChat 复用，
 * 避免三处各写一份 `marked.parse(...)` 各自漂移（历史上就是三份重复实现）。
 *
 * 两个必须守住的红线：
 * 1. **DOMPurify 清洗**：正文来自大模型，`marked` 默认放行原始 HTML，
 *    不洗就是 XSS 通道（`<img src=x onerror=...>`）。KaTeX 产出也要过清洗。
 * 2. **朗读文本保持原文**：渲染只作用于展示，`MessageActions` 拿到的仍是
 *    Markdown 原文（LaTeX 由 `speech-text.ts` 负责丢弃，不能被渲染影响）。
 */

import { Marked } from 'marked'
import type { TokenizerAndRendererExtension, TokenizerThis } from 'marked'
import markedKatex from 'marked-katex-extension'
import DOMPurify from 'dompurify'
import {
  parseUiBlockEnvelope,
  validateAttentionMatrixProps,
} from '@/components/chat/ui-blocks/schema'

/**
 * CJK 紧邻加粗的放宽规则（T001）。
 *
 * 问题：CommonMark 的右翼判定规定「闭合 `**` 前是标点时，其后必须是空白或标点」。
 * 于是 `**注意：**这是重点`（闭合前是全角冒号，后面紧跟汉字）会判定失败，
 * `**` 原样输出。中文正文没有空格，这种写法非常常见。
 *
 * 做法：注册一个 inline 扩展，抢在内置 strong 之前匹配 `**…**`，
 * 只要求「开头 `**` 后紧跟非空白、闭合 `**` 前是非空白、且不被第三个 `*` 紧贴」，
 * 不再做左右翼判定。内容仍走 inline 解析，因此嵌套的 `*em*`、`` `code` `` 不受影响。
 *
 * 不匹配跨行（`[^\n]`），避免残缺的 `**` 把后续段落整段吞掉（流式场景）。
 */
const STRONG_RE = /^\*\*(?=\S)((?:(?!\*\*)[^\n])*?\S)\*\*(?!\*)/
const relaxedStrongExtension: TokenizerAndRendererExtension = {
  name: 'strong',
  level: 'inline',
  start(src: string): number {
    return src.indexOf('**')
  },
  tokenizer(this: TokenizerThis, src: string) {
    const match = STRONG_RE.exec(src)
    if (!match) return undefined
    const inner = match[1] ?? ''
    return {
      type: 'strong',
      raw: match[0],
      text: inner,
      tokens: this.lexer.inlineTokens(inner),
    }
  },
}

/**
 * 专用 Marked 实例（不用全局 `marked`）：扩展只注册在本地实例上，
 * 避免污染其他直接 import { marked } 的调用点（如 CourseDetail）。
 *
 * `throwOnError: false`：模型偶尔输出残缺 LaTeX（流式中途尤甚），
 * 不能让一个坏公式整段渲染抛异常 —— 出错的公式退化为红色原文，
 * 其余正文照常渲染。
 * `singleDollarTextMath: true`：支持行内 `$x^2$`（后端 prompt 约定的写法）。
 *   注意：该选项是 marked-katex-extension 的运行时开关，其类型声明
 *   （MarkedKatexOptions）尚未收录，故此处显式断言类型，避免 TS 报未知属性。
 *   ⚠️ 该开关的代价：孤立 `$` 会被当公式定界符。本产品正文大量出现**美元金额**
 *   （`$0.02`、`$0.0348/M`），故必须先经 `escapeCurrencyDollars` 预处理，
 *   否则 `闲时 $0.02，高峰 $0.04` 会被吞成一段公式。
 */
const marked = new Marked(
  markedKatex({
    throwOnError: false,
    singleDollarTextMath: true,
    nonStandard: true,
  } as Parameters<typeof markedKatex>[0] & { singleDollarTextMath?: boolean }),
  { extensions: [relaxedStrongExtension] },
)


/** 含 LaTeX 结构（命令/上下标/分组）→ 判定为公式 */
const LATEX_HINT_RE = /[\\^_{}]/
/**
 * 含数学运算符 → 判定为公式（用于 `$x + y$` 这类无 LaTeX 命令的写法）。
 *
 * 刻意**不含 `/`**：`$0.0348/M`、`$1/2` 是货币单价写法（每百万 tokens），
 * 把 `/` 当运算符会让整段金额被吞成公式（实测踩到）。
 * 也不含 `%`：`$50%` 这类比例文本同样是普通文本。
 * 刻意**不含 `*`**：Markdown 加粗的 `**` 会落在两个 `$` 之间，
 * 若把 `*` 当运算符，`$0.02 **注意** $0.04` 会被吞成公式、加粗失效（实测踩到）。
 * 需要乘号的公式请用 `\times` / `\cdot`（LaTeX 写法，由 LATEX_HINT_RE 判定）。
 */
const MATH_OP_RE = /[+\-=<>]/

/**
 * 单个符号变量（`$n$`、`$k$`、`$p$`）→ 判定为公式。
 *
 * 只接受「单个字母，可带 1–2 位字母数字」且两侧无其它字符，
 * 因此 `$0.02 and 高峰 $` 这类含空格/数字/中文的货币文本不会命中。
 * 实测：仅靠 LATEX_HINT_RE / MATH_OP_RE 时，`$n$` 会被当货币，
 * 结果是 `$n$` 以源码字符出现，且第二个 `$` 残留成孤立货币符。
 */
const BARE_SYMBOL_RE = /^[A-Za-z][A-Za-z0-9]{0,2}$/

/**
 * 单对 `$...$` 的内容是否"像公式"。
 *
 * 判据刻意保守：只有出现 LaTeX 结构、数学运算符或单个符号变量才算公式。
 * 货币金额（`0.02`、`0.0348/M`、`100 买了书，还剩 `）不含这些符号 → 判为货币，转义掉。
 * 取舍：宁可让少数"纯数字公式"（`$0.02$`）保持字面可读，
 * 也不能把货币文本误吞进公式（后者会破坏正文语义）。
 */
const looksLikeMath = (inner: string): boolean =>
  LATEX_HINT_RE.test(inner) ||
  MATH_OP_RE.test(inner) ||
  BARE_SYMBOL_RE.test(inner.trim())

/**
 * 逐字符扫描并转义"货币美元"。
 *
 * 为什么不能用 `/\$([^$]+)\$/g` 一把梭：那样会把「孤立的货币 $」与「后续真公式的
 * 开头 $」错配成一对，吃掉真公式的定界符。实测反例：
 *   `缓存命中 $0.02 元，计算式 $\frac{1}{2}$ 如下`
 * 贪婪配对会得到 inner=`0.02 元，计算式 `（判为货币）→ 连公式开头的 `$` 一起转义，
 * 于是 `\frac{1}{2}` 失去开定界符、公式不再渲染。
 *
 * 正确策略（就近闭合 + 分类处置）：
 * - 找同行最近的 `$` 作为候选闭合；
 * - inner 像公式 → 保留该对，跳过闭合符；
 * - inner 像货币 → **只转义当前这个 `$`**，从下一个字符继续（不消费候选闭合符，
 *   它可能是下一个真公式的开定界符）；
 * - 同行没有闭合 `$`（孤立 `$`）→ 原样保留（KaTeX 也不会把它当公式起点）。
 */
const escapeCurrencyInText = (text: string): string => {
  let out = ''
  let i = 0
  while (i < text.length) {
    const ch = text[i]
    if (ch !== '$') {
      out += ch
      i++
      continue
    }
    const close = text.indexOf('$', i + 1)
    const lineEnd = text.indexOf('\n', i + 1)
    const hasClose = close !== -1 && (lineEnd === -1 || close < lineEnd)
    if (!hasClose) {
      // 孤立 $：不构成公式，保持原样
      out += '$'
      i++
      continue
    }
    const inner = text.slice(i + 1, close)
    // 空内容（`$$`）按公式处理，保留
    if (inner === '' || looksLikeMath(inner)) {
      out += '$' + inner + '$'
      i = close + 1
    } else {
      // 货币：只转义当前 $，继续扫描（候选闭合符留给后续判定）
      out += '\\$'
      i++
    }
  }
  return out
}

/**
 * 预处理：把"货币美元"转义为 `\$`，避免被 KaTeX 当公式定界符吞掉。
 *
 * 处理顺序（保证不误伤公式与代码）：
 * 1. 先摘出块级公式 `$$...$$` 用占位符保护（它们一定是公式）；
 * 2. 代码围栏 ``` 与行内代码 `x` 原样跳过（`echo $HOME` 不能被转义）；
 * 3. 其余正文按 `$...$` 配对判定：像公式则保留，否则转义。
 *
 * 这是 `singleDollarTextMath: true` 的必要配套 —— 本产品正文里
 * 美元金额与行内公式共用 `$`，不区分就会互相污染。
 */
export const escapeCurrencyDollars = (content: string): string => {
  if (!content) return content
  const SENTINEL = '\uE000'
  const display: string[] = []
  let work = content.replace(/\$\$[\s\S]*?\$\$/g, (m) => {
    display.push(m)
    return `${SENTINEL}${display.length - 1}${SENTINEL}`
  })
  work = work
    .split(/(```[\s\S]*?```)/g)
    .map((part) =>
      part.startsWith('```')
        ? part
        : part
            .split(/(`[^`]*`)/g)
            .map((seg) => (seg.startsWith('`') ? seg : escapeCurrencyInText(seg)))
            .join(''),
    )
    .join('')
  return work.replace(
    new RegExp(`${SENTINEL}(\\d+)${SENTINEL}`, 'g'),
    (_, i: string) => display[Number(i)] ?? '',
  )
}

/**
 * 剥离正文里**合法**的 ```ui-block 围栏（T004，渲染层兜底）。
 *
 * 背景：后端只在**最终正文下发前**抽取围栏转成 visualization SSE 事件，
 * 但 token 流式期间、以及 partial 收尾帧被跳过时，正文里仍会出现围栏
 * 残留（T006 确认的结构性问题）。渲染层剥离一劳永逸。
 *
 * 口径与后端 `visualization_blocks.py` / `visualization.py` 严格一致，否则会丢内容：
 * - 识别：3-backtick、info string 恰为 `ui-block`（允许两侧空白）、开/闭围栏独立成行；
 * - 剥离条件：JSON 可解析 + envelope 校验（schema.ts）+ 类型/版本已注册 + props 校验通过
 *   ——恰好等于"后端会为之发出 visualization 事件"的围栏；
 * - **失败不吞正文**：JSON 非法或校验不过的围栏**原样保留**（后端同样不发事件、
 *   围栏留在正文里，用户至少能看到一段 JSON 代码块，不会凭空消失）。
 * - 闭围栏后的一个换行（及至多一个空行）随围栏一起剥掉，剥离后前后文之间
 *   恰保留一个空行分隔（围栏通常独占一段）。
 *
 * 注意：类型→版本→校验器的映射必须与 `ui-blocks/registry.ts` 的 REGISTRY 保持
 * 同步（registry 新增类型时这里也要注册，否则该类型围栏会被误判为非法而残留；
 * 反之这里多注册会误剥离）。此映射只引 schema.ts 的纯函数，不引入 Vue 组件。
 */
const UI_BLOCK_FENCE_RE = /^```[ \t]*ui-block[ \t]*\n([\s\S]*?)^```[ \t]*(?:\n\n?|$)/gm

/** (type, version) → props 校验器。与 registry.ts 的 REGISTRY 同步维护。 */
const UI_BLOCK_PROP_VALIDATORS: Record<
  string,
  Record<number, (props: unknown) => { ok: boolean }>
> = {
  attention_matrix: { 1: validateAttentionMatrixProps },
}

export const stripValidUiBlockFences = (content: string): string => {
  if (!content) return content
  return content.replace(UI_BLOCK_FENCE_RE, (fence, body: string) => {
    let candidate: unknown
    try {
      candidate = JSON.parse(body)
    } catch {
      return fence // JSON 非法：围栏原样保留
    }
    const envelope = parseUiBlockEnvelope(candidate)
    if (!envelope.ok) return fence
    const { type, version, props } = envelope.value
    const validator = UI_BLOCK_PROP_VALIDATORS[type]?.[version]
    if (!validator) return fence // 类型/版本未注册：后端不会发事件，围栏保留
    return validator(props).ok ? '' : fence // props 校验不过：围栏保留
  })
}

/**
 * 把助手正文渲染成可安全注入的 HTML（Markdown + 数学公式 + 表格/删除线）。
 *
 * @param content Markdown 原文（含 `$...$` / `$$...$$`）
 * @returns 经 DOMPurify 清洗、可直接 `v-html` 的 HTML
 */
export const renderChatMarkdown = (content: string): string => {
  if (!content) return ''
  const html = marked.parse(stripValidUiBlockFences(escapeCurrencyDollars(content)), {
    breaks: true,
    gfm: true,
  }) as string
  return DOMPurify.sanitize(html)
}

/** 供测试与调用方复用：渲染但不清洗（排查"是渲染问题还是清洗问题"时用） */
export const renderChatMarkdownRaw = (content: string): string =>
  content
    ? (marked.parse(stripValidUiBlockFences(escapeCurrencyDollars(content)), {
        breaks: true,
        gfm: true,
      }) as string)
    : ''
