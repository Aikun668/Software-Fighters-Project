import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { copyTextToClipboard } from '@/utils/clipboard'

/**
 * 复制工具的降级合同。
 *
 * 环境差异是这组用例存在的理由：
 *   - https / localhost 下走 `navigator.clipboard`；
 *   - http + 局域网 IP（学生机演示场景）下该 API 根本不存在，必须退到 execCommand；
 *   - 用户拒绝权限时 writeText 会 reject，同样要退，而不是判失败。
 */

const defineClipboard = (value: unknown) => {
  Object.defineProperty(navigator, 'clipboard', { value, configurable: true })
}

/** 用一次性的 execCommand 桩替换全局，返回调用计数与临时节点快照 */
const stubExecCommand = (result: boolean) => {
  const calls: string[] = []
  const execCommand = vi.fn((command: string) => {
    calls.push(command)
    return result
  })
  Object.defineProperty(document, 'execCommand', { value: execCommand, configurable: true })
  return { execCommand, calls }
}

const bodyTextareas = () => Array.from(document.querySelectorAll('body > textarea'))

beforeEach(() => {
  defineClipboard(undefined)
  Object.defineProperty(document, 'execCommand', { value: undefined, configurable: true })
})

afterEach(() => {
  defineClipboard(undefined)
  Object.defineProperty(document, 'execCommand', { value: undefined, configurable: true })
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

describe('copyTextToClipboard：优先走 Clipboard API', () => {
  it('writeText 可用时直接写入并返回 true', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    defineClipboard({ writeText })

    await expect(copyTextToClipboard('# 标题\n**加粗**内容')).resolves.toBe(true)
    // 复制的是原始 Markdown：粘贴到文档里还应保留 `#` 与 `**`
    expect(writeText).toHaveBeenCalledWith('# 标题\n**加粗**内容')
  })

  it('writeText 被拒绝时退到 execCommand，而不是直接判失败', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('NotAllowedError'))
    defineClipboard({ writeText })
    const { execCommand } = stubExecCommand(true)

    await expect(copyTextToClipboard('一段回答')).resolves.toBe(true)
    expect(writeText).toHaveBeenCalled()
    expect(execCommand).toHaveBeenCalledWith('copy')
  })
})

describe('copyTextToClipboard：无 Clipboard API 时的降级路径', () => {
  it('navigator.clipboard 不存在（局域网 http）时用 execCommand 成功', async () => {
    defineClipboard(undefined)
    const { execCommand } = stubExecCommand(true)

    await expect(copyTextToClipboard('正文')).resolves.toBe(true)
    expect(execCommand).toHaveBeenCalledWith('copy')
  })

  it('execCommand 返回 false 时判定为失败', async () => {
    stubExecCommand(false)
    await expect(copyTextToClipboard('正文')).resolves.toBe(false)
  })

  it('execCommand 不存在（jsdom 精简环境）时不抛异常，返回 false', async () => {
    await expect(copyTextToClipboard('正文')).resolves.toBe(false)
  })

  it('execCommand 抛异常时也被吞掉，返回 false', async () => {
    Object.defineProperty(document, 'execCommand', {
      value: vi.fn(() => {
        throw new Error('not implemented')
      }),
      configurable: true,
    })
    await expect(copyTextToClipboard('正文')).resolves.toBe(false)
  })
})

describe('copyTextToClipboard：临时节点必须清理', () => {
  it('复制后 body 里不残留 textarea', async () => {
    stubExecCommand(true)
    await copyTextToClipboard('正文')
    expect(bodyTextareas()).toHaveLength(0)
  })

  it('execCommand 抛异常时同样清理临时节点', async () => {
    Object.defineProperty(document, 'execCommand', {
      value: vi.fn(() => {
        throw new Error('boom')
      }),
      configurable: true,
    })
    await copyTextToClipboard('正文')
    expect(bodyTextareas()).toHaveLength(0)
  })

  it('降级路径写入的文本内容与入参一致', async () => {
    defineClipboard(undefined)
    // 临时节点在 execCommand 调用时仍在 body 里，从 appendChild 的入参上取回它的值
    const appended: HTMLTextAreaElement[] = []
    const appendChild = document.body.appendChild.bind(document.body)
    vi.spyOn(document.body, 'appendChild').mockImplementation((node) => {
      if (node instanceof HTMLTextAreaElement) appended.push(node)
      return appendChild(node)
    })
    stubExecCommand(true)

    await expect(copyTextToClipboard('保留 **Markdown** 原文')).resolves.toBe(true)
    expect(appended).toHaveLength(1)
    expect(appended[0].value).toBe('保留 **Markdown** 原文')
  })
})
