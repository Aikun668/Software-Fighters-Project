import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import Page from '../KnowledgeGraphPage.vue'
import { consumeLearningDraft, clearLearningDraft } from '@/utils/learningDraft'
const { get, post, push } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), push: vi.fn() }))
vi.mock('@/utils/request', () => ({ default: { get, post }, resolveErrorMessage: (e: Error) => e.message }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))
beforeEach(() => { get.mockReset(); post.mockReset(); push.mockReset(); clearLearningDraft() })
const node = (id: string) => ({ id, title: id, summary: '', sources: [{ conversationId: 12, messageId: 9, quote: `学习${id}`, createdAt: '2026-01-01' }], firstSeen: '', lastSeen: '' })
describe('personal learning map', () => {
  it('renders empty state instead of fabricated knowledge', async () => {
    get.mockResolvedValue({ nodes: [], edges: [] })
    const w = mount(Page); await flushPromises()
    expect(w.text()).toContain('还没有学习节点'); expect(w.text()).not.toContain('78%')
  })
  it('keeps isolated nodes, filters local graph, and opens evidence and a draft', async () => {
    get.mockResolvedValue({ nodes: [node('A'), node('B'), node('C')], edges: [{ id: 'ab', source: 'A', target: 'B', relation: '依赖', evidence: { quote: 'A依赖B', conversationId: 12, messageId: 9 } }] })
    const w = mount(Page); await flushPromises()
    expect(w.findAll('[data-node]').length).toBe(3)
    await w.find('[data-node="A"]').trigger('click')
    expect(w.text()).toContain('学习A')
    await w.find('[data-testid="local"]').trigger('click')
    expect(w.findAll('[data-node]').length).toBe(2)
    get.mockResolvedValueOnce({ draft: '继续学习A，来源证据学习A' })
    await w.find('[data-testid="continue"]').trigger('click'); await flushPromises()
    expect(push).toHaveBeenCalledWith({path:'/question-nav-chat',query:{learningContext:expect.any(String)}})
    expect(JSON.stringify(push.mock.calls)).not.toContain('来源证据')
    expect(consumeLearningDraft(push.mock.calls[0]?.[0].query.learningContext)).toContain('来源证据')
    await w.find('[data-testid="source"]').trigger('click')
    expect(push).toHaveBeenCalledWith({ path: '/question-nav-chat', query: { conversationId: '12', sourceMessageId: '9' } })
  })
  it('shows a failed fetch and retries without demo fallback', async () => {
    get.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ nodes: [], edges: [] })
    const w = mount(Page); await flushPromises()
    expect(w.text()).toContain('offline')
    await w.find('[data-testid="refresh"]').trigger('click'); await flushPromises()
    expect(w.text()).toContain('还没有学习节点')
  })
  it('withholds graph when memory privacy state is unavailable', async () => {
    get.mockResolvedValue({ nodes: [node('private')], edges: [], meta: { unavailable: true } })
    const w = mount(Page); await flushPromises()
    expect(w.text()).toContain('记忆状态暂不可用')
    expect(w.findAll('[data-node]')).toHaveLength(0)
  })

  it('discloses truncated scope and searches without inventing links', async () => {
    get.mockResolvedValue({ nodes: [node('Alpha'), node('Beta')], edges: [], meta: { truncated: true } })
    const w = mount(Page); await flushPromises()
    expect(w.text()).toContain('达到读取或展示上限')
    await w.find('input').setValue('Alpha')
    expect(w.findAll('[data-node]')).toHaveLength(1)
    expect(w.findAll('line')).toHaveLength(0)
    await w.find('input').setValue('none')
    expect(w.text()).toContain('没有符合搜索条件')
  })

  it('shows evidence-backed learning events without invented completion', async () => {
    get.mockResolvedValue({nodes:[node('A')],edges:[],events:[{id:'ev',type:'question',title:'为什么学A',nodeIds:['A'],sources:node('A').sources,occurredAt:'2026-01-01'}]})
    const w = mount(Page); await flushPromises()
    await w.find('[data-testid="tab-events"]').trigger('click')
    expect(w.text()).toContain('为什么学A'); expect(w.text()).toContain('学习A')
    expect(w.text()).not.toContain('已完成')
  })
  it('persists a suggestion decision once while busy and reloads', async () => {
    const suggestion={id:'s',source:'A',target:'B',reason:'探索类比',status:'pending',sources:node('A').sources}
    get.mockResolvedValue({nodes:[node('A'),node('B')],edges:[],suggestions:[suggestion]})
    let finish!: () => void
    post.mockImplementationOnce(() => new Promise<void>(resolve => {finish=resolve}))
    const w = mount(Page); await flushPromises()
    await w.find('[data-testid="tab-suggestions"]').trigger('click')
    await w.find('[data-testid="accept-s"]').trigger('click')
    expect(w.find('[data-testid="reject-s"]').attributes('disabled')).toBeDefined()
    expect(post).toHaveBeenCalledWith('/learning-map/suggestions/s/decision',{decision:'accepted'})
    get.mockResolvedValue({nodes:[node('A'),node('B')],edges:[],suggestions:[{...suggestion,status:'accepted'}]})
    finish(); await flushPromises()
    expect(w.text()).toContain('已确认的探索关联')
  })
  it('does not navigate with stale or failed continuation evidence', async () => {
    push.mockClear(); get.mockResolvedValueOnce({nodes:[node('A')],edges:[]})
    const w = mount(Page); await flushPromises(); await w.find('[data-node="A"]').trigger('click')
    get.mockRejectedValueOnce(new Error('来源已不可读'))
    await w.find('[data-testid="continue"]').trigger('click'); await flushPromises()
    expect(w.text()).toContain('来源已不可读'); expect(push).not.toHaveBeenCalled()
    expect(consumeLearningDraft()).toBe('')
  })

  it('keeps a failed suggestion pending and allows retry', async () => {
    const suggestion={id:'s',source:'A',target:'B',reason:'探索',status:'pending',sources:[]}
    get.mockResolvedValue({nodes:[node('A'),node('B')],edges:[],suggestions:[suggestion]})
    post.mockRejectedValueOnce(new Error('保存失败'))
    const w=mount(Page); await flushPromises(); await w.find('[data-testid="tab-suggestions"]').trigger('click')
    await w.find('[data-testid="reject-s"]').trigger('click'); await flushPromises()
    expect(w.text()).toContain('保存失败')
    expect(w.find('[data-testid="accept-s"]').attributes('disabled')).toBeUndefined()
  })
  it('discards continuation after selection changes and prevents duplicate requests', async () => {
    get.mockResolvedValueOnce({nodes:[node('A'),node('B')],edges:[]})
    const w=mount(Page); await flushPromises(); await w.find('[data-node="A"]').trigger('click')
    let finish!: (value:{draft:string})=>void
    get.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
    await w.find('[data-testid="continue"]').trigger('click')
    expect(w.find('[data-testid="continue"]').attributes('disabled')).toBeDefined()
    await w.find('[data-node="B"]').trigger('click')
    finish({draft:'stale A'}); await flushPromises()
    expect(push).not.toHaveBeenCalled()
    expect(consumeLearningDraft()).toBe('')
  })

  it('allows withdrawing a confirmed association without changing it to a factual edge', async () => {
    const suggestion={id:'s',source:'A',target:'B',reason:'探索',status:'accepted',sources:[]}
    get.mockResolvedValue({nodes:[node('A'),node('B')],edges:[],suggestions:[suggestion]})
    const w=mount(Page); await flushPromises(); await w.find('[data-testid="tab-suggestions"]').trigger('click')
    post.mockResolvedValue({})
    get.mockResolvedValue({nodes:[node('A'),node('B')],edges:[],suggestions:[{...suggestion,status:'rejected'}]})
    await w.find('[data-testid="change-s"]').trigger('click'); await flushPromises()
    expect(post).toHaveBeenCalledWith('/learning-map/suggestions/s/decision',{decision:'rejected'})
    expect(w.text()).toContain('重新确认')
  })

})
