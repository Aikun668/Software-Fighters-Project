/**
 * TTS 文本预处理与分块（纯函数，无浏览器依赖）。
 *
 * 两个职责：
 * 1. `prepareSpeechText` —— 把 Markdown/公式噪声剥成适合朗读的口语文本。
 *    代码块、表格、LaTeX 一律丢弃：逐字念 `def foo(self):` 或 `\frac{a}{b}`
 *    是灾难，宁可漏念也不要念错。
 * 2. `splitSpeechChunks` —— 按句子边界切块。
 *    Chrome 的 speechSynthesis 对单条 utterance 有约 15 秒的静默截断缺陷，
 *    长回答必须切成多条排队播完，否则会念到一半突然停住。
 */

/**
 * 围栏代码块（``` 或 ~~~），连同语言标注一起丢弃。
 *
 * 结尾分支必须写成 `(?![\s\S])`（= 输入末尾）而**不能**用 `$`：
 * 本正则带 `m` 标志，`$` 会在每一行行尾成立，惰性量词会立刻在开围栏那一行的
 * 行尾收尾，只删掉 ```` ```python ```` 而把函数体留在正文里被念出来。
 */
const FENCED_CODE = /^[ \t]*(?:`{3,}|~{3,})[^\n]*\n[\s\S]*?(?:^[ \t]*(?:`{3,}|~{3,})[ \t]*$|(?![\s\S]))/gm
/** 块级公式 $$...$$：浏览器 TTS 念不出 LaTeX，整块丢弃 */
const DISPLAY_MATH = /\$\$[\s\S]*?\$\$/g
/** 行内公式 $...$：同上，但只在成对出现时丢弃，避免误伤含 $ 的普通文本 */
const INLINE_MATH = /\$[^$\n]{1,200}\$/g
/** 表格整行（| a | b |）：逐格念出来毫无意义 */
const TABLE_ROW = /^[ \t]*\|.*\|[ \t]*$/gm
/** 图片 ![alt](url)：alt 通常是被丢掉的装饰文本，整体丢弃 */
const IMAGE = /!\[[^\]]*\]\([^)]*\)/g
/** 链接 [文字](url)：只保留可见文字 */
const LINK = /\[([^\]]*)\]\([^)]*\)/g
/** 行内代码 `code`：保留内容，去掉反引号（`git commit` 念出来是有用的） */
const INLINE_CODE = /`([^`]+)`/g
/** 标题行首的 # */
const HEADING = /^[ \t]{0,3}#{1,6}[ \t]+/gm
/** 引用行首的 > */
const BLOCKQUOTE = /^[ \t]{0,3}>[ \t]?/gm
/** 列表项标记：-、*、+、1.、2) */
const LIST_MARKER = /^[ \t]{0,3}(?:[-*+]|\d+[.)])[ \t]+/gm
/** 水平分割线 --- / *** / ___ */
const HR = /^[ \t]{0,3}(?:[-*_][ \t]*){3,}$/gm
/** 强调标记 **粗** / *斜* / ~~删~~ / __粗__ */
const EMPHASIS = /(\*{1,3}|_{1,3}|~~)(\S(?:.*?\S)?)\1/g
/** 裸 HTML 标签 */
const HTML_TAG = /<[^>]+>/g
/** 连续空格 / 过多空行 */
const WHITESPACE = /[ \t]+/g
const BLANK_LINES = /\n{3,}/g

/** 句子结束符：中英标点 + 换行。保留标点本身，交给 TTS 处理停顿 */
const SENTENCE_BOUNDARY = /(?<=[。！？；!?;.\n])/

/** 单块字符上限。中文约 4~5 字/秒，120 字 ≈ 25 秒；英文约 15 字符/秒，远低于截断线 */
export const SPEECH_CHUNK_MAX_CHARS = 120

/**
 * 把 Markdown 正文降级为适合朗读的纯口语文本。
 * 刻意做成有损变换：目标是「念得自然」，不是「渲染准确」。
 */
export function prepareSpeechText(raw: string): string {
  if (!raw) return ''
  let out = raw
  out = out.replace(FENCED_CODE, ' ')
  out = out.replace(DISPLAY_MATH, ' ')
  out = out.replace(TABLE_ROW, ' ')
  out = out.replace(IMAGE, ' ')
  out = out.replace(LINK, '$1')
  out = out.replace(INLINE_CODE, '$1')
  out = out.replace(INLINE_MATH, ' ')
  out = out.replace(HEADING, '')
  out = out.replace(BLOCKQUOTE, '')
  out = out.replace(HR, ' ')
  out = out.replace(LIST_MARKER, '')
  out = out.replace(EMPHASIS, '$2')
  out = out.replace(HTML_TAG, '')
  out = out.replace(WHITESPACE, ' ')
  out = out.replace(BLANK_LINES, '\n\n')
  return out.trim()
}

/**
 * 按句子边界把长文本切成多条 utterance。
 *
 * 贪心合并：尽量把完整的句子拼进同一块，直到超过 `maxChars` 才断开。
 * 这样既避开 Chrome 的截断缺陷，又不会把一句话拦腰切断破坏语调。
 */
export function splitSpeechChunks(text: string, maxChars: number = SPEECH_CHUNK_MAX_CHARS): string[] {
  const normalized = text.trim()
  if (!normalized) return []
  if (normalized.length <= maxChars) return [normalized]

  const sentences = normalized
    .split(SENTENCE_BOUNDARY)
    .map((s) => s.trim())
    .filter(Boolean)

  const chunks: string[] = []
  let current = ''

  for (const sentence of sentences) {
    // 单句本身就超限（无标点的长串）：硬切，保证每块都能顺利播完
    if (sentence.length > maxChars) {
      if (current) {
        chunks.push(current)
        current = ''
      }
      for (let i = 0; i < sentence.length; i += maxChars) {
        chunks.push(sentence.slice(i, i + maxChars))
      }
      continue
    }
    if (current && current.length + sentence.length > maxChars) {
      chunks.push(current)
      current = sentence
      continue
    }
    current += sentence
  }

  if (current) chunks.push(current)
  return chunks
}

/** 判断文本主体语言，用于挑选中/英文音色。CJK 占比高即视为中文 */
export function detectSpeechLang(text: string): 'zh-CN' | 'en-US' {
  const cjk = text.match(/[\u4e00-\u9fff\u3400-\u4dbf]/g)?.length ?? 0
  const latin = text.match(/[A-Za-z]/g)?.length ?? 0
  // 只要出现成规模的中文就按中文念；纯英文才用英文音色
  return cjk >= 4 || cjk > latin ? 'zh-CN' : 'en-US'
}

/**
 * 从中/英文候选里挑一个可用音色。
 * 优先精确匹配 `lang`，否则退到同语系（zh*、en*），都没有则返回 null
 * 交给浏览器用默认音色。
 */
export function pickVoice(
  voices: SpeechSynthesisVoice[],
  lang: 'zh-CN' | 'en-US',
): SpeechSynthesisVoice | null {
  if (!voices.length) return null
  const prefix = lang.slice(0, 2).toLowerCase()
  return (
    voices.find((v) => v.lang?.toLowerCase() === lang.toLowerCase()) ??
    voices.find((v) => v.lang?.toLowerCase().startsWith(prefix)) ??
    null
  )
}
