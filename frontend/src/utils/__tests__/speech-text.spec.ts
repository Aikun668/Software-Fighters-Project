import { describe, it, expect } from 'vitest'
import {
  detectSpeechLang,
  pickVoice,
  prepareSpeechText,
  splitSpeechChunks,
} from '../speech-text'

/** 造一个最简 SpeechSynthesisVoice 桩 */
const voice = (lang: string, name = lang): SpeechSynthesisVoice =>
  ({ lang, name, default: false, localService: true, voiceURI: name }) as SpeechSynthesisVoice

describe('prepareSpeechText：把 Markdown 降级为口语文本', () => {
  it('丢弃围栏代码块（逐字念代码是灾难）', () => {
    const md = ['先看这段代码：', '```python', 'def foo(self):', '    return 1', '```', '就是这样。'].join('\n')
    const out = prepareSpeechText(md)
    expect(out).not.toContain('def foo')
    expect(out).not.toContain('return 1')
    expect(out).toContain('先看这段代码')
    expect(out).toContain('就是这样')
  })

  it('丢弃表格与块级公式，保留行内代码的正文', () => {
    const md = ['| 列A | 列B |', '| --- | --- |', '| 1 | 2 |', '公式 $$x^2$$ 结束。', '执行 `git commit` 提交。'].join('\n')
    const out = prepareSpeechText(md)
    expect(out).not.toContain('列A')
    expect(out).not.toContain('x^2')
    // 行内代码只去掉反引号，内容要念出来
    expect(out).toContain('git commit')
    expect(out).not.toContain('`')
  })

  it('链接保留可见文字，强调标记与标题井号被去掉', () => {
    const md = '## 标题\n参考 [官方文档](https://example.com) 里的 **重点** 说明。'
    const out = prepareSpeechText(md)
    expect(out).toBe('标题\n参考 官方文档 里的 重点 说明。')
  })

  it('图片整体丢弃（alt 多为装饰文本）', () => {
    const out = prepareSpeechText('如图 ![架构图](a.png) 所示。')
    expect(out).not.toContain('架构图')
    expect(out).not.toContain('a.png')
    expect(out).toContain('如图')
  })

  it('空文本返回空串，不抛错', () => {
    expect(prepareSpeechText('')).toBe('')
    expect(prepareSpeechText('   \n  ')).toBe('')
  })
})

describe('splitSpeechChunks：按句子切块规避 Chrome 截断', () => {
  it('短文本不切块', () => {
    const text = '这是一个短回答。'
    expect(splitSpeechChunks(text)).toEqual([text])
  })

  it('长文本切成多块，每块不超上限', () => {
    const sentence = '这是一句用来测试分块的句子，长度适中。'
    const text = sentence.repeat(12)
    const chunks = splitSpeechChunks(text, 60)
    expect(chunks.length).toBeGreaterThan(1)
    for (const chunk of chunks) {
      expect(chunk.length).toBeLessThanOrEqual(60)
    }
    // 切块不丢内容（去掉空白后应还原）
    expect(chunks.join('').replace(/\s/g, '')).toBe(text.replace(/\s/g, ''))
  })

  it('优先在句末断开，不把一句话拦腰切断', () => {
    const text = '第一句话在这里。第二句话在这里。第三句话在这里。'
    const chunks = splitSpeechChunks(text, 26)
    // 每块都应该以句号收尾（说明断点落在句子边界）
    for (const chunk of chunks.slice(0, -1)) {
      expect(chunk.endsWith('。')).toBe(true)
    }
  })

  it('单句超长时硬切，保证每块都能播完', () => {
    const text = 'a'.repeat(250)
    const chunks = splitSpeechChunks(text, 100)
    expect(chunks).toHaveLength(3)
    expect(chunks.every((c) => c.length <= 100)).toBe(true)
  })

  it('空文本返回空数组', () => {
    expect(splitSpeechChunks('   ')).toEqual([])
  })
})

describe('detectSpeechLang：中英混排选音色', () => {
  it('中文为主判为 zh-CN', () => {
    expect(detectSpeechLang('这是一个中文回答。')).toBe('zh-CN')
  })

  it('中英混排（含少量英文术语）仍判为 zh-CN', () => {
    expect(detectSpeechLang('这里用了 Transformer 这个模型来解释注意力机制。')).toBe('zh-CN')
  })

  it('纯英文判为 en-US', () => {
    expect(detectSpeechLang('This is an English answer about gradients.')).toBe('en-US')
  })

  it('空文本退化为 en-US', () => {
    expect(detectSpeechLang('')).toBe('en-US')
  })
})

describe('pickVoice：挑选可用音色', () => {
  const voices = [voice('en-US'), voice('zh-TW'), voice('zh-CN'), voice('ja-JP')]

  it('优先精确匹配语言', () => {
    expect(pickVoice(voices, 'zh-CN')?.lang).toBe('zh-CN')
  })

  it('无精确匹配时退到同语系', () => {
    const onlyTw = [voice('zh-TW'), voice('en-GB')]
    expect(pickVoice(onlyTw, 'zh-CN')?.lang).toBe('zh-TW')
  })

  it('音色列表为空时返回 null，交给浏览器默认音色', () => {
    expect(pickVoice([], 'zh-CN')).toBeNull()
  })

  it('没有同语系音色时返回 null', () => {
    expect(pickVoice([voice('ja-JP')], 'zh-CN')).toBeNull()
  })
})
