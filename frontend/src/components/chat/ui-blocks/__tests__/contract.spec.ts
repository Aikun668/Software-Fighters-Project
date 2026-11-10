import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { dispatchUiBlock } from '../registry'

/**
 * 双端契约测试（D-014）：与后端 tests/test_ui_block_contract.py 读同一份
 * fixtures（ai-service/tests/fixtures/ui_block_contract.json），只比对 ok
 * 布尔结论，防止 TS/Python 手写校验镜像漂移。
 * vitest 以 frontend/ 为 cwd，用相对路径跨包取文件。
 */
const fixturePath = resolve(
  process.cwd(),
  '../ai-service/tests/fixtures/ui_block_contract.json',
)
const fixtures: { name: string; ok: boolean; block: unknown }[] = JSON.parse(
  readFileSync(fixturePath, 'utf-8'),
).fixtures

describe('ui-block 双端契约（dispatchUiBlock vs 后端 parse_ui_block）', () => {
  it('fixtures 文件存在且覆盖已注册的每一种类型', () => {
    expect(fixtures.length).toBeGreaterThanOrEqual(10)
    const types = new Set(
      fixtures
        .map((f) => (f.block as { type?: string })?.type)
        .filter((t): t is string => Boolean(t)),
    )
    expect(types).toContain('attention_matrix')
    expect(types).toContain('conv_window')
  })

  it.each(fixtures)('$name：前端结论必须与 fixture 一致', ({ ok, block }) => {
    const result = dispatchUiBlock(block)
    expect(result.ok).toBe(ok)
  })
})
