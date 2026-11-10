import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StructuredDiagram from '../StructuredDiagram.vue'
import { exampleDiagram, legacyDiagram } from '../fixtures/diagram-example'

describe('StructuredDiagram', () => {
  it('renders nodes and edges for a valid diagram', () => {
    const wrapper = mount(StructuredDiagram, { props: { diagram: exampleDiagram } })
    expect(wrapper.findAll('.node-group')).toHaveLength(exampleDiagram.nodes.length)
    expect(wrapper.findAll('.edge-line')).toHaveLength(exampleDiagram.edges.length)
    expect(wrapper.find('.diagram-empty').exists()).toBe(false)
  })

  it('shows detail on click and hides on second click', async () => {
    const wrapper = mount(StructuredDiagram, { props: { diagram: exampleDiagram } })
    const firstNode = wrapper.find('.node-group')
    await firstNode.trigger('click')
    expect(wrapper.find('.diagram-detail').exists()).toBe(true)
    expect(wrapper.find('.detail-label').text()).toBe(exampleDiagram.nodes[0]?.label)
    await firstNode.trigger('click')
    expect(wrapper.find('.diagram-detail').exists()).toBe(false)
  })

  it('opens detail via keyboard Enter', async () => {
    const wrapper = mount(StructuredDiagram, { props: { diagram: exampleDiagram } })
    const firstNode = wrapper.find('.node-group')
    await firstNode.trigger('keydown', { key: 'Enter' })
    expect(wrapper.find('.diagram-detail').exists()).toBe(true)
  })

  it('shows empty state for invalid/legacy schema', () => {
    const wrapper = mount(StructuredDiagram, { props: { diagram: legacyDiagram } })
    expect(wrapper.find('.diagram-empty').exists()).toBe(true)
    expect(wrapper.find('.diagram-svg').exists()).toBe(false)
  })
})
