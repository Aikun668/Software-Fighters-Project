import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import Home from '../Home.vue'
import type { Conversation } from '@/api/types'

const { getConversationsMock, pushMock, updateConversationMock, deleteConversationMock, successMock, errorMock } =
  vi.hoisted(() => ({
    getConversationsMock: vi.fn(),
    pushMock: vi.fn(),
    updateConversationMock: vi.fn(),
    deleteConversationMock: vi.fn(),
    successMock: vi.fn(),
    errorMock: vi.fn(),
  }))

vi.mock('@/api/conversations', () => ({
  getConversations: (...args: unknown[]) => getConversationsMock(...args),
  updateConversation: (...args: unknown[]) => updateConversationMock(...args),
  deleteConversation: (...args: unknown[]) => deleteConversationMock(...args),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: (...args: unknown[]) => successMock(...args),
    error: (...args: unknown[]) => errorMock(...args),
  },
}))

/** useRoute() 在每个用例里返回同一个可变对象，便于模拟“当前打开的会话” */
const routeQuery: Record<string, string> = {}

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: (...args: unknown[]) => pushMock(...args) }),
  useRoute: () => ({ path: '/question-nav-chat', query: routeQuery }),
}))

/** 每个用例拿一份新对象：重命名用例会就地改 title，共享常量会污染后续用例 */
const makeConversation = (overrides: Partial<Conversation> = {}): Conversation => ({
  id: 22,
  userId: 1,
  title: '进程学习',
  status: 'active',
  summary: null,
  createdAt: '2026-09-29T10:00:00',
  updatedAt: '2026-09-29T10:05:00',
  ...overrides,
})

const mountPage = () => mount(Home, { global: { stubs: { 'router-view': true } } })

beforeEach(() => {
  getConversationsMock.mockReset()
  pushMock.mockReset()
  updateConversationMock.mockReset()
  deleteConversationMock.mockReset()
  successMock.mockReset()
  errorMock.mockReset()
  getConversationsMock.mockResolvedValue([])
  for (const key of Object.keys(routeQuery)) delete routeQuery[key]
})

describe('Home 全局侧边栏会话入口', () => {
  it('在最左侧现有侧边栏读取并显示真实会话列表', async () => {
    getConversationsMock.mockResolvedValue([makeConversation()])

    const wrapper = mountPage()
    await flushPromises()

    expect(getConversationsMock).toHaveBeenCalledTimes(1)
    expect(wrapper.get('.app-sidebar .conversation-item').text()).toContain('进程学习')
    expect(wrapper.get('.app-sidebar .conversation-item').text()).toContain('2026-09-29 10:05')
  })

  it('点击最左侧会话时只通过路由打开聊天页对应会话', async () => {
    getConversationsMock.mockResolvedValue([makeConversation()])

    const wrapper = mountPage()
    await flushPromises()
    await wrapper.get('.app-sidebar .conversation-item').trigger('click')

    expect(pushMock).toHaveBeenCalledWith({
      path: '/question-nav-chat',
      query: { conversationId: '22' },
    })
  })

  it('点击现有的新建对话按钮回到无会话 ID 的聊天入口', async () => {
    const wrapper = mountPage()
    await wrapper.get('.new-chat').trigger('click')

    expect(pushMock).toHaveBeenCalledWith('/question-nav-chat')
  })

  it('收起侧边栏时保留同一套历史区和主导航结构，展开后可恢复', async () => {
    getConversationsMock.mockResolvedValue([makeConversation()])

    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('.collapse-toggle').trigger('click')

    expect(wrapper.get('.app-shell').classes()).toContain('is-collapsed')
    expect(wrapper.get('.history-section').exists()).toBe(true)
    expect(wrapper.get('.primary-nav').exists()).toBe(true)
    expect(wrapper.get('.history-section').attributes('aria-hidden')).toBe('true')

    await wrapper.get('.collapse-toggle').trigger('click')

    expect(wrapper.get('.app-shell').classes()).not.toContain('is-collapsed')
    expect(wrapper.get('.history-section').attributes('aria-hidden')).toBe('false')
    expect(wrapper.get('.conversation-item').text()).toContain('进程学习')
  })

  it('收起最近对话分组时不再保留一整块空的 flex 占位', async () => {
    const wrapper = mountPage()

    await wrapper.get('.section-toggle').trigger('click')

    expect(wrapper.get('.history-section').classes()).toContain('is-history-collapsed')
    expect(wrapper.get('.primary-nav').exists()).toBe(true)
  })
})

describe('侧边栏会话行内管理', () => {
  /** 打开第一行的 [⋮] 菜单 */
  const openRowMenu = async (wrapper: ReturnType<typeof mountPage>) => {
    await wrapper.get('.conversation-row .row-more').trigger('click')
  }

  it('每行提供 [⋮] 入口，菜单默认收起', async () => {
    getConversationsMock.mockResolvedValue([makeConversation()])

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.get('.conversation-row .row-more').exists()).toBe(true)
    expect(wrapper.find('.row-menu').exists()).toBe(false)
  })

  it('点击 [⋮] 就在该行展开小菜单，提供重命名与删除', async () => {
    getConversationsMock.mockResolvedValue([makeConversation()])

    const wrapper = mountPage()
    await flushPromises()
    await openRowMenu(wrapper)

    const menu = wrapper.get('.row-menu')
    expect(menu.text()).toContain('重命名')
    expect(menu.text()).toContain('删除')
    // 浮层必须留在行内，不能退化成全屏对话框
    expect(wrapper.get('.conversation-row').find('.row-menu').exists()).toBe(true)
  })

  it('选择重命名后在该行内联编辑，回车提交新标题', async () => {
    updateConversationMock.mockResolvedValue(makeConversation({ title: '进程与线程' }))
    getConversationsMock.mockResolvedValue([makeConversation()])

    const wrapper = mountPage()
    await flushPromises()
    await openRowMenu(wrapper)
    await wrapper.get('.row-menu button').trigger('click')

    const input = wrapper.get('.conversation-rename')
    expect((input.element as HTMLInputElement).value).toBe('进程学习')

    await input.setValue('进程与线程')
    await input.trigger('keydown.enter')
    await flushPromises()

    expect(updateConversationMock).toHaveBeenCalledWith(22, { title: '进程与线程' })
    expect(wrapper.get('.conversation-item').text()).toContain('进程与线程')
    expect(wrapper.find('.conversation-rename').exists()).toBe(false)
  })

  it('标题未改变时不发请求，直接退出编辑', async () => {
    getConversationsMock.mockResolvedValue([makeConversation()])

    const wrapper = mountPage()
    await flushPromises()
    await openRowMenu(wrapper)
    await wrapper.get('.row-menu button').trigger('click')
    await wrapper.get('.conversation-rename').trigger('keydown.enter')
    await flushPromises()

    expect(updateConversationMock).not.toHaveBeenCalled()
    expect(wrapper.find('.conversation-rename').exists()).toBe(false)
  })

  it('重命名失败时保留编辑态与草稿，且不重复弹错误提示', async () => {
    updateConversationMock.mockRejectedValue({ message: '更新失败' })
    getConversationsMock.mockResolvedValue([makeConversation()])

    const wrapper = mountPage()
    await flushPromises()
    await openRowMenu(wrapper)
    await wrapper.get('.row-menu button').trigger('click')
    const input = wrapper.get('.conversation-rename')
    await input.setValue('新标题')
    await input.trigger('keydown.enter')
    await flushPromises()

    expect(errorMock).not.toHaveBeenCalled()
    // 仍处于编辑态，且草稿保留，用户可以直接改完重试
    const stillEditing = wrapper.get('.conversation-rename')
    expect((stillEditing.element as HTMLInputElement).value).toBe('新标题')
    expect(wrapper.find('.conversation-item').exists()).toBe(false)
  })

  it('删除必须先确认：点删除只展开行旁确认卡，不立即调用接口', async () => {
    getConversationsMock.mockResolvedValue([makeConversation()])

    const wrapper = mountPage()
    await flushPromises()
    await openRowMenu(wrapper)
    await wrapper.get('.row-menu button.is-danger').trigger('click')

    const confirm = wrapper.get('.row-confirm')
    expect(confirm.text()).toContain('进程学习')
    expect(wrapper.get('.conversation-row').find('.row-confirm').exists()).toBe(true)
    expect(deleteConversationMock).not.toHaveBeenCalled()
  })

  it('确认卡里点取消则关闭且不删除', async () => {
    getConversationsMock.mockResolvedValue([makeConversation()])

    const wrapper = mountPage()
    await flushPromises()
    await openRowMenu(wrapper)
    await wrapper.get('.row-menu button.is-danger').trigger('click')
    await wrapper.get('.confirm-actions button').trigger('click')

    expect(wrapper.find('.row-confirm').exists()).toBe(false)
    expect(deleteConversationMock).not.toHaveBeenCalled()
  })

  it('确认删除后调用接口并从列表移除该行', async () => {
    deleteConversationMock.mockResolvedValue(undefined)
    getConversationsMock.mockResolvedValue([makeConversation()])

    const wrapper = mountPage()
    await flushPromises()
    await openRowMenu(wrapper)
    await wrapper.get('.row-menu button.is-danger').trigger('click')
    await wrapper.get('.confirm-actions button.is-danger').trigger('click')
    await flushPromises()

    expect(deleteConversationMock).toHaveBeenCalledWith(22)
    expect(wrapper.findAll('.conversation-item')).toHaveLength(0)
    expect(successMock).toHaveBeenCalled()
  })

  it('删除的正是当前打开的会话时回到新对话入口', async () => {
    deleteConversationMock.mockResolvedValue(undefined)
    getConversationsMock.mockResolvedValue([makeConversation()])
    routeQuery.conversationId = '22'

    const wrapper = mountPage()
    await flushPromises()
    await openRowMenu(wrapper)
    await wrapper.get('.row-menu button.is-danger').trigger('click')
    await wrapper.get('.confirm-actions button.is-danger').trigger('click')
    await flushPromises()

    expect(pushMock).toHaveBeenCalledWith({ path: '/question-nav-chat' })
  })

  it('删除的不是当前会话时保持不变，不跳转', async () => {
    deleteConversationMock.mockResolvedValue(undefined)
    getConversationsMock.mockResolvedValue([makeConversation()])
    routeQuery.conversationId = '99'

    const wrapper = mountPage()
    await flushPromises()
    await openRowMenu(wrapper)
    await wrapper.get('.row-menu button.is-danger').trigger('click')
    await wrapper.get('.confirm-actions button.is-danger').trigger('click')
    await flushPromises()

    expect(pushMock).not.toHaveBeenCalled()
  })

  it('删除失败时保留该行与确认卡，且不重复弹错误提示', async () => {
    deleteConversationMock.mockRejectedValue({ message: '会话不存在' })
    getConversationsMock.mockResolvedValue([makeConversation()])

    const wrapper = mountPage()
    await flushPromises()
    await openRowMenu(wrapper)
    await wrapper.get('.row-menu button.is-danger').trigger('click')
    await wrapper.get('.confirm-actions button.is-danger').trigger('click')
    await flushPromises()

    // 错误提示由 request.ts 的响应拦截器统一弹出，页面不得再弹一次
    expect(errorMock).not.toHaveBeenCalled()
    expect(wrapper.findAll('.conversation-item')).toHaveLength(1)
    expect(wrapper.find('.row-confirm').exists()).toBe(true)
  })

  it('Esc 关闭展开的行内浮层', async () => {
    getConversationsMock.mockResolvedValue([makeConversation()])

    const wrapper = mountPage()
    await flushPromises()
    await openRowMenu(wrapper)
    expect(wrapper.find('.row-menu').exists()).toBe(true)

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()

    expect(wrapper.find('.row-menu').exists()).toBe(false)
  })
})
