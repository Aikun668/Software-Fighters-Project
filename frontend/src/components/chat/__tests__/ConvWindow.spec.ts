import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ConvWindow from '../ConvWindow.vue'

const mountWindow = (props: Record<string, unknown> = {}) =>
  mount(ConvWindow, {
    props: { inputRows: 5, inputCols: 5, kernelSize: 3, stride: 1, ...props },
    attachTo: document.body,
  })

const inputCells = (wrapper: ReturnType<typeof mountWindow>) => wrapper.findAll('.conv-in-cell')
const windowCells = (wrapper: ReturnType<typeof mountWindow>) =>
  wrapper.findAll('.conv-in-cell--window')
const outputCells = (wrapper: ReturnType<typeof mountWindow>) => wrapper.findAll('.conv-out-cell')
const currentOutput = (wrapper: ReturnType<typeof mountWindow>) =>
  wrapper.findAll('.conv-out-cell--current')

describe('ConvWindow', () => {
  it('默认 5×5 输入、3×3 卷积核、步长 1：25 个输入格，9 个窗口格，3×3 输出', () => {
    const wrapper = mountWindow()

    expect(inputCells(wrapper)).toHaveLength(25)
    expect(windowCells(wrapper)).toHaveLength(9)
    expect(outputCells(wrapper)).toHaveLength(9)
    expect(currentOutput(wrapper)).toHaveLength(1)
    wrapper.unmount()
  })

  it('头部显示维度信息，输出面板标注特征图尺寸', () => {
    const wrapper = mountWindow()

    expect(wrapper.find('.conv-window__hint').text()).toContain('输入 5×5')
    expect(wrapper.find('.conv-window__hint').text()).toContain('卷积核 3×3')
    expect(wrapper.find('.conv-window__hint').text()).toContain('步长 1')
    expect(wrapper.findAll('.conv-window__panel-label')[1].text()).toContain('输出特征图 3×3')
    wrapper.unmount()
  })

  it('点击输出格子切换窗口：覆盖格数恒等于卷积核面积，说明面板同步更新', async () => {
    const wrapper = mountWindow()

    // 点击输出 (3, 3)（右下角）→ 窗口起点 (2, 2)，仍是 3×3=9 格
    const target = outputCells(wrapper)[2 * 3 + 2]
    await target.trigger('click')
    expect(currentOutput(wrapper)).toHaveLength(1)
    expect(windowCells(wrapper)).toHaveLength(9)
    expect(wrapper.find('.conv-window__detail').text()).toContain('输出特征图 [3, 3]')
    expect(wrapper.find('.conv-window__detail').text()).toContain('第 3–5 行')

    // 回到左上角输出 (1, 1) → 窗口起点 (0, 0)，覆盖第 1–3 行
    await outputCells(wrapper)[0].trigger('click')
    expect(wrapper.find('.conv-window__detail').text()).toContain('第 1–3 行')
    wrapper.unmount()
  })

  it('拖动滑块切换窗口位置，位置计数同步', async () => {
    const wrapper = mountWindow()

    await wrapper.find('input[type="range"]').setValue('4')
    expect(wrapper.find('.conv-window__slider').text()).toContain('5 / 9')
    expect(windowCells(wrapper)).toHaveLength(9)
    wrapper.unmount()
  })

  it('步长 2 时输出尺寸收缩：6×6 输入、2×2 核 → 3×3 输出且窗口面积恒为 4', () => {
    const wrapper = mountWindow({ inputRows: 6, inputCols: 6, kernelSize: 2, stride: 2 })

    expect(inputCells(wrapper)).toHaveLength(36)
    expect(outputCells(wrapper)).toHaveLength(9)
    expect(windowCells(wrapper)).toHaveLength(4)
    wrapper.unmount()
  })

  it('输出格子为可聚焦按钮且带 aria-label，当前格有 aria-pressed', () => {
    const wrapper = mountWindow()

    outputCells(wrapper).forEach((cell) => {
      expect(cell.element.tagName).toBe('BUTTON')
      expect(cell.attributes('aria-label')).toBeTruthy()
    })
    expect(currentOutput(wrapper)[0].attributes('aria-pressed')).toBe('true')
    wrapper.unmount()
  })

  it('不展示任何数值结果：颜色只表示窗口覆盖，图例明示语义（D-007 精神）', () => {
    const wrapper = mountWindow()

    const text = wrapper.text()
    expect(text).not.toMatch(/概率|%/)
    expect(text).toContain('不代表任何特征值或计算结果')
    // 输入/输出格子均不渲染数字内容，只有位置语义
    inputCells(wrapper).forEach((cell) => expect(cell.text()).toBe(''))
    outputCells(wrapper).forEach((cell) => expect(cell.text()).toBe(''))
    wrapper.unmount()
  })
})
