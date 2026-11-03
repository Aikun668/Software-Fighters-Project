import { describe, expect, it } from 'vitest'
import { resolveErrorMessage } from '@/utils/request'

describe('resolveErrorMessage', () => {
  it('读取 Error 实例的 message', () => {
    expect(resolveErrorMessage(new Error('boom'))).toBe('boom')
  })

  it('读取拦截器 reject 的普通对象信封的 message（真实 500 响应体）', () => {
    const rejected = { code: 500, message: '服务器内部错误' }
    expect(resolveErrorMessage(rejected)).toBe('服务器内部错误')
    expect(String(rejected)).toBe('[object Object]')
  })

  it('字符串异常原样返回', () => {
    expect(resolveErrorMessage('网络异常')).toBe('网络异常')
  })

  it('无 message 的对象回退到 String', () => {
    expect(resolveErrorMessage({ code: 500 })).toBe('[object Object]')
  })

  it('null / undefined 不抛异常', () => {
    expect(resolveErrorMessage(null)).toBe('null')
    expect(resolveErrorMessage(undefined)).toBe('undefined')
  })
})
