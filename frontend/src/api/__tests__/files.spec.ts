/**
 * 文件上传请求合同。
 *
 * 回归背景：`uploadFile` 曾手写 `Content-Type: multipart/form-data`。
 * 该值不带 `boundary=...`；虽然当前 axios 适配器会替 FormData 剥掉它，
 * 但那是适配器内部行为。这里锁死「不得手写该 Content-Type」，
 * 保证升级 axios 或切换适配器后不会把无 boundary 的头送上线路。
 *
 * 另一个真实缺陷：全局 axios 超时是 10s，20MB 图片在慢网络下会被误判为失败，
 * 因此上传必须显式放宽超时。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'

const { postMock } = vi.hoisted(() => ({ postMock: vi.fn() }))

vi.mock('@/utils/request', () => ({
  default: {
    post: (...args: unknown[]) => postMock(...args),
  },
}))

import { uploadFile } from '../files'

describe('uploadFile 请求合同', () => {
  beforeEach(() => {
    postMock.mockReset()
    postMock.mockResolvedValue({ fileId: 1, url: 'https://x/y.png', fileName: 'images/y.png', originalName: 'y.png' })
  })

  it('把文件放进 FormData 的 file 字段', async () => {
    const file = new File(['abc'], 'y.png', { type: 'image/png' })
    await uploadFile(file)

    const [url, body] = postMock.mock.calls[0] as [string, FormData]
    expect(url).toBe('/file/upload')
    expect(body).toBeInstanceOf(FormData)
    expect((body.get('file') as File).name).toBe('y.png')
  })

  it('不得手写 multipart/form-data，交给浏览器补 boundary', async () => {
    await uploadFile(new File(['abc'], 'y.png', { type: 'image/png' }))

    const config = postMock.mock.calls[0][2] as { headers?: Record<string, unknown> }
    const headers = config?.headers ?? {}
    expect(headers['Content-Type']).toBeUndefined()
    expect(headers['content-type']).toBeUndefined()
  })

  it('上传超时必须宽于全局默认的 10s，避免大图被误判为失败', async () => {
    await uploadFile(new File(['abc'], 'y.png', { type: 'image/png' }))

    const config = postMock.mock.calls[0][2] as { timeout?: number }
    expect(config.timeout).toBeGreaterThan(10_000)
  })

  it('没有文件名/后缀的剪贴板图片原样交给后端按 MIME 兜底', async () => {
    const pasted = new File(['abc'], '', { type: 'image/png' })
    await uploadFile(pasted)

    const body = postMock.mock.calls[0][1] as FormData
    const sent = body.get('file') as File
    expect(sent.type).toBe('image/png')
    expect(sent.name).toBe('')
  })
})
