import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { DiagramSchema } from '@/types/resource'
import StructuredDiagram from './StructuredDiagram.vue'

const validDiagram: DiagramSchema = {
  schema_version: 'v1',
  title: 'CNN 流程',
  summary: '输入经过卷积和池化得到特征。',
  layout: 'layered',
  nodes: [
    { id: 'input', label: '输入', detail: '原始图像。', layer: 0 },
    { id: 'conv', label: '卷积', detail: '提取局部特征。', layer: 1 },
  ],
  edges: [{ source: 'input', target: 'conv', label: '特征' }],
}

describe('StructuredDiagram', () => {
  it('renders a valid diagram and shows selected node detail', async () => {
    const wrapper = mount(StructuredDiagram, { props: { diagram: validDiagram } })

    await wrapper.find('[role="button"]').trigger('click')

    expect(wrapper.find('svg').exists()).toBe(true)
    expect(wrapper.text()).toContain('原始图像。')
  })

  it('supports keyboard selection for a node', async () => {
    const wrapper = mount(StructuredDiagram, { props: { diagram: validDiagram } })

    await wrapper.find('[role="button"]').trigger('keydown.enter')

    expect(wrapper.text()).toContain('原始图像。')
  })

  it('does not render invalid diagrams as SVG or HTML', () => {
    const wrapper = mount(StructuredDiagram, {
      props: { diagram: { ...validDiagram, schema_version: 'legacy' as 'v1' } },
    })

    expect(wrapper.find('svg').exists()).toBe(false)
    expect(wrapper.text()).toContain('旧格式暂不支持交互预览')
  })
})
