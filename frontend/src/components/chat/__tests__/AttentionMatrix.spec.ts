import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AttentionMatrix from '../AttentionMatrix.vue'

const mountMatrix = (props: Record<string, unknown> = {}) =>
  mount(AttentionMatrix, {
    props: { tokenCount: 5, mode: 'causal', ...props },
    attachTo: document.body,
  })

const allCells = (wrapper: ReturnType<typeof mountMatrix>) => wrapper.findAll('.attn-cell')
const allowedCells = (wrapper: ReturnType<typeof mountMatrix>) =>
  wrapper.findAll('.attn-cell--allowed')
const maskedCells = (wrapper: ReturnType<typeof mountMatrix>) =>
  wrapper.findAll('.attn-cell--masked')

const findCell = (wrapper: ReturnType<typeof mountMatrix>, q: number, k: number) =>
  wrapper.find(`.attn-cell[data-q="${q}"][data-k="${k}"]`)

const modeButton = (wrapper: ReturnType<typeof mountMatrix>, text: string) =>
  wrapper.findAll('.attn-matrix__modes button').find((b) => b.text() === text)!

describe('AttentionMatrix', () => {
  it('默认 5 token 因果：25 格，15 个可访问，10 个灰色', () => {
    const wrapper = mountMatrix()

    expect(allCells(wrapper)).toHaveLength(25)
    expect(allowedCells(wrapper)).toHaveLength(15)
    expect(maskedCells(wrapper)).toHaveLength(10)
    wrapper.unmount()
  })

  it('切到双向后 25 格全部可访问，切回因果恢复 15 个', async () => {
    const wrapper = mountMatrix()

    await modeButton(wrapper, '双向').trigger('click')
    expect(allowedCells(wrapper)).toHaveLength(25)

    await modeButton(wrapper, '因果').trigger('click')
    expect(allowedCells(wrapper)).toHaveLength(15)
    wrapper.unmount()
  })

  it('拖到 8 token 因果：64 格，36 个可访问', async () => {
    const wrapper = mountMatrix()

    await wrapper.find('input[type="range"]').setValue('8')

    expect(allCells(wrapper)).toHaveLength(64)
    expect(allowedCells(wrapper)).toHaveLength(36)
    wrapper.unmount()
  })

  it('Q5/K3 可点击并显示可访问状态；Q2/K5 在因果模式下禁用且点击无效', async () => {
    const wrapper = mountMatrix()

    const allowed = findCell(wrapper, 5, 3)
    expect(allowed.attributes('disabled')).toBeUndefined()
    await allowed.trigger('click')
    expect(wrapper.find('.attn-matrix__detail').text()).toContain('Q5 → K3：可访问')

    const masked = findCell(wrapper, 2, 5)
    expect(masked.attributes('disabled')).toBeDefined()
    await masked.trigger('click')
    expect(wrapper.find('.attn-matrix__detail').text()).not.toContain('Q2 → K5')
    wrapper.unmount()
  })

  it('不出现强弱/概率文字与热力着色，图例说明位置示意语义', () => {
    const wrapper = mountMatrix()

    const text = wrapper.text()
    expect(text).not.toMatch(/概率|强弱|%/)
    expect(wrapper.find('.attn-cell--heat').exists()).toBe(false)
    expect(text).toContain('位置示意')
    expect(text).toContain('不代表真实 Attention 权重')
    wrapper.unmount()
  })

  it('因果模式下行色按 Query 位置渐变，被 Mask 的格子无渐变', async () => {
    const wrapper = mountMatrix()

    expect(findCell(wrapper, 1, 1).attributes('style') ?? '').toMatch(/--attn-depth:\s*0\.000/)
    expect(findCell(wrapper, 5, 1).attributes('style') ?? '').toMatch(/--attn-depth:\s*1\.000/)
    expect(findCell(wrapper, 2, 5).attributes('style')).toBeUndefined()

    await modeButton(wrapper, '双向').trigger('click')
    expect(findCell(wrapper, 5, 5).attributes('style')).toBeUndefined()
    wrapper.unmount()
  })

  it('格子带 aria-label 且为可聚焦的按钮', () => {
    const wrapper = mountMatrix()

    const cells = allCells(wrapper)
    cells.forEach((cell) => {
      expect(cell.element.tagName).toBe('BUTTON')
      expect(cell.attributes('aria-label')).toBeTruthy()
    })
    expect(findCell(wrapper, 5, 3).attributes('aria-label')).toContain('Q5 → K3')
    wrapper.unmount()
  })

  it('提供 weights 时被忽略：不出现热力着色与百分比文字（D-007）', () => {
    const weights = [
      [1, 0, 0],
      [0.5, 0.5, 0],
      [0.2, 0.3, 0.5],
    ]
    const wrapper = mountMatrix({ tokenCount: 3, weights })

    expect(wrapper.findAll('.attn-cell--heat')).toHaveLength(0)
    expect(wrapper.text()).not.toMatch(/相对权重|%/)
    expect(findCell(wrapper, 1, 1).attributes('aria-label')).not.toContain('相对权重')
    wrapper.unmount()
  })
})
