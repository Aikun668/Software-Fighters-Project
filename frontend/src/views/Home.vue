<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, provide, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  BarChart3,
  BookOpen,
  CalendarCheck2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  FolderOpen,
  MessageSquare,
  MoreHorizontal,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  PencilLine,
  Plus,
  Settings2,
  Trash2,
  CircleHelp,
  UserRound,
} from '@lucide/vue'
import { ElMessage } from 'element-plus'
import { deleteConversation, getConversations, updateConversation } from '@/api/conversations'
import type { Conversation } from '@/api/types'

const router = useRouter()
const route = useRoute()
const collapsed = ref(false)
const historyOpen = ref(true)

/** 侧栏宽度可拖拽调整，默认 260px，两个极限防止拖得过窄/过宽 */
const SIDEBAR_MIN_WIDTH = 220
const SIDEBAR_MAX_WIDTH = 360
const sidebarWidth = ref(260)
const resizing = ref(false)

const stopResize = () => {
  resizing.value = false
  window.removeEventListener('mousemove', onResizeMove)
  window.removeEventListener('mouseup', stopResize)
}
const onResizeMove = (event: MouseEvent) => {
  sidebarWidth.value = Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, event.clientX))
}
const startResize = () => {
  resizing.value = true
  window.addEventListener('mousemove', onResizeMove)
  window.addEventListener('mouseup', stopResize)
}
const conversations = ref<Conversation[]>([])
const listLoading = ref(false)

/**
 * 行内管理的互斥状态。
 *
 * 管理动作全部贴着被操作的那一行展开（`[⋮]` 小菜单、行旁删除确认、行内重命名），
 * 不使用全屏对话框：侧栏本身只有 220–360px 宽，全屏弹窗会打断浏览上下文。
 * 同一时刻只允许一行展开浮层，避免多个浮层叠加。
 */
const menuOpenId = ref<number | null>(null)
const renamingId = ref<number | null>(null)
const renameDraft = ref('')
/** v-for 内的模板引用会收集成数组，这里用函数引用固定到当前唯一的重命名输入框 */
const renameInput = ref<HTMLInputElement | null>(null)
const setRenameInput = (el: unknown) => {
  renameInput.value = (el as HTMLInputElement | null) ?? null
}
/** 待确认删除的会话；非空时在该行旁显示小确认浮层 */
const deleteTarget = ref<Conversation | null>(null)
/** 正在提交的会话 id，用于禁用重复提交 */
const busyId = ref<number | null>(null)

const navItems = [
  { label: '对话辅导', path: '/question-nav-chat', icon: MessageSquare },
  { label: '知识图谱', path: '/learning-resource-network', icon: Network },
  { label: '学习计划', path: '/learning-path', icon: CalendarCheck2 },
  { label: '资源工坊', path: '/resource-center', icon: FolderOpen },
  { label: '练习中心', path: '/exercise', icon: PencilLine },
  { label: '学情分析', path: '/learning-analysis', icon: BarChart3 },
]

const activePath = computed(() => route.path)
const go = (path: string) => router.push(path)
const formatConversationTime = (value: string) => value.replace('T', ' ').slice(0, 16)

const loadConversations = async () => {
  listLoading.value = true
  try {
    conversations.value = await getConversations()
  } catch (error) {
    console.error('加载会话列表失败', error)
  } finally {
    listLoading.value = false
  }
}

const openConversation = (id: number) => {
  // 打开另一条会话时收起当前展开的浮层，避免菜单停在一个已经离开的行上
  closeRowOverlays()
  void router.push({ path: '/question-nav-chat', query: { conversationId: String(id) } })
}

const closeRowOverlays = () => {
  menuOpenId.value = null
  deleteTarget.value = null
}

const toggleMenu = (id: number) => {
  // 打开菜单时收起其他行的浮层；再点同一行则关闭
  if (menuOpenId.value === id) {
    closeRowOverlays()
    return
  }
  cancelRename()
  menuOpenId.value = id
  deleteTarget.value = null
}

/** 标题在列表里最多显示一行，统一按显示文本回退，避免把 '未命名对话' 存成真标题 */
const displayTitleOf = (conversation: Conversation) => conversation.title || '未命名对话'

/** 进入行内重命名：草稿用已保存标题，无标题时留空 */
const startRename = (conversation: Conversation) => {
  menuOpenId.value = null
  deleteTarget.value = null
  renamingId.value = conversation.id
  renameDraft.value = conversation.title ?? ''
  void nextTick(() => {
    renameInput.value?.focus()
    renameInput.value?.select()
  })
}

const cancelRename = () => {
  renamingId.value = null
  renameDraft.value = ''
}

/**
 * 提交重命名。
 *
 * 标题未变化时不发请求，直接退出编辑态；空标题不作为合法输入，
 * 也直接退出，避免把会话改成没有标题的「未命名对话」。
 */
const commitRename = async (conversation: Conversation) => {
  if (renamingId.value !== conversation.id || busyId.value !== null) return
  const next = renameDraft.value.trim()
  if (!next || next === (conversation.title ?? '')) {
    cancelRename()
    return
  }

  busyId.value = conversation.id
  try {
    const updated = await updateConversation(conversation.id, { title: next })
    // 后端回包是权威值；缺失时用本地草稿兜底，保证列表立刻反映新标题
    conversation.title = updated?.title ?? next
    cancelRename()
    ElMessage.success('已重命名')
  } catch (error) {
    // 失败提示由 request.ts 的响应拦截器统一弹出，这里再弹一次会变成双 toast。
    // 保留编辑态与草稿，用户可以直接改完重试。
    console.error('重命名会话失败', error)
  } finally {
    busyId.value = null
  }
}

/** 删除入口：只切到"待确认"，不直接删；确认浮层贴着该行展开 */
const askDelete = (conversation: Conversation) => {
  cancelRename()
  menuOpenId.value = null
  deleteTarget.value = conversation
}

/**
 * 确认删除。
 *
 * 后端会连同该会话的消息一起删除。删除成功后从本地列表移除，
 * 若删的正是当前打开的会话，则清掉 query 里的 conversationId 回到新对话页，
 * 否则会停留在一个已经不存在、每次刷新都报 404 的会话上。
 */
const confirmDelete = async () => {
  const target = deleteTarget.value
  if (!target || busyId.value !== null) return

  busyId.value = target.id
  try {
    await deleteConversation(target.id)
    conversations.value = conversations.value.filter((item) => item.id !== target.id)
    deleteTarget.value = null
    ElMessage.success('已删除对话')

    const currentId = Number(route.query.conversationId)
    if (Number.isInteger(currentId) && currentId === target.id) {
      void router.push({ path: '/question-nav-chat' })
    }
  } catch (error) {
    // 同 commitRename：错误 toast 由响应拦截器负责，这里保留确认卡供用户重试
    console.error('删除会话失败', error)
  } finally {
    busyId.value = null
  }
}

/** 点击空白处 / Esc 关闭行内浮层 */
const handleDocumentPointerDown = (event: MouseEvent) => {
  const el = event.target as HTMLElement | null
  if (el?.closest('.conversation-row')) return
  closeRowOverlays()
}
const handleKeydown = (event: KeyboardEvent) => {
  if (event.key !== 'Escape') return
  if (renamingId.value !== null) {
    cancelRename()
    return
  }
  closeRowOverlays()
}

provide('refreshConversations', loadConversations)
onMounted(() => {
  void loadConversations()
  document.addEventListener('pointerdown', handleDocumentPointerDown)
  document.addEventListener('keydown', handleKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
  document.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('mousemove', onResizeMove)
  window.removeEventListener('mouseup', stopResize)
})
</script>

<template>
  <div
    class="app-shell"
    :class="{ 'is-collapsed': collapsed, 'is-resizing': resizing }"
    :style="{ '--sidebar-width': `${sidebarWidth}px` }"
  >
    <aside class="app-sidebar">
      <div class="brand-row" @click="go('/question-nav-chat')">
        <div class="brand-mark" aria-hidden="true"><BookOpen :size="22" :stroke-width="1.45" /></div>
        <span v-if="!collapsed" class="brand-name">智学tutor</span>
      </div>

      <button class="new-chat" @click="go('/question-nav-chat')">
        <Plus :size="18" :stroke-width="1.6" />
        <span v-if="!collapsed">新建对话</span>
      </button>

      <div class="sidebar-main">
        <section class="history-section" :class="{ 'is-history-collapsed': !historyOpen }" :aria-hidden="collapsed">
          <button class="section-toggle" :aria-expanded="historyOpen" @click="historyOpen = !historyOpen">
            <span>最近对话</span>
            <ChevronDown :size="15" :class="{ rotated: !historyOpen }" />
          </button>
          <div v-if="historyOpen" class="conversation-list">
            <span v-if="listLoading" class="conversation-state">正在加载…</span>
            <span v-else-if="!conversations.length" class="conversation-state">还没有历史对话</span>
            <template v-else>
              <div
                v-for="conversation in conversations"
                :key="conversation.id"
                class="conversation-row"
                :class="{ 'is-menu-open': menuOpenId === conversation.id, 'is-confirming': deleteTarget?.id === conversation.id }"
              >
                <div class="conversation-line">
                  <template v-if="renamingId === conversation.id">
                    <span class="status-dot" />
                    <input
                      :ref="setRenameInput"
                      v-model="renameDraft"
                      class="conversation-rename"
                      type="text"
                      maxlength="60"
                      aria-label="重命名对话"
                      :disabled="busyId === conversation.id"
                      @click.stop
                      @keydown.enter.prevent="commitRename(conversation)"
                      @keydown.esc.prevent="cancelRename()"
                      @blur="commitRename(conversation)"
                    />
                  </template>
                  <template v-else>
                    <button class="conversation-item" :title="displayTitleOf(conversation)" @click="openConversation(conversation.id)">
                      <span class="status-dot" />
                      <span class="conversation-title">{{ displayTitleOf(conversation) }}</span>
                      <time>{{ formatConversationTime(conversation.updatedAt || conversation.createdAt) }}</time>
                    </button>
                    <button
                      class="row-more"
                      type="button"
                      :aria-label="`管理对话：${displayTitleOf(conversation)}`"
                      :aria-expanded="menuOpenId === conversation.id"
                      title="更多操作"
                      @click.stop="toggleMenu(conversation.id)"
                    >
                      <MoreHorizontal :size="15" :stroke-width="1.6" />
                    </button>
                  </template>
                </div>

                <div v-if="menuOpenId === conversation.id" class="row-menu" role="menu" @click.stop>
                  <button type="button" role="menuitem" @click="startRename(conversation)">
                    <PencilLine :size="14" :stroke-width="1.5" />重命名
                  </button>
                  <button type="button" role="menuitem" class="is-danger" @click="askDelete(conversation)">
                    <Trash2 :size="14" :stroke-width="1.5" />删除
                  </button>
                </div>

                <div v-if="deleteTarget?.id === conversation.id" class="row-confirm" role="dialog" aria-label="确认删除对话" @click.stop>
                  <p>删除「{{ displayTitleOf(conversation) }}」？</p>
                  <span class="confirm-sub">对话与消息将一并删除，不可撤销。</span>
                  <div class="confirm-actions">
                    <button type="button" :disabled="busyId === conversation.id" @click="deleteTarget = null">取消</button>
                    <button type="button" class="is-danger" :disabled="busyId === conversation.id" @click="confirmDelete">
                      {{ busyId === conversation.id ? '删除中…' : '删除' }}
                    </button>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </section>

        <nav class="primary-nav" aria-label="主要功能">
          <button
            v-for="item in navItems"
            :key="item.path"
            class="nav-item"
            :class="{ active: activePath === item.path }"
            :title="collapsed ? item.label : undefined"
            @click="go(item.path)"
          >
            <component :is="item.icon" :size="20" :stroke-width="1.45" />
            <span v-if="!collapsed">{{ item.label }}</span>
          </button>
        </nav>
      </div>

      <div class="sidebar-bottom">
        <div v-if="!collapsed" class="bottom-links">
          <button><Settings2 :size="17" :stroke-width="1.5" />设置</button>
          <button><CircleHelp :size="17" :stroke-width="1.5" />帮助</button>
        </div>
        <button class="profile-chip" title="学习者">
          <span class="avatar"><UserRound :size="17" :stroke-width="1.5" /></span>
          <span v-if="!collapsed">学习者</span>
          <ChevronDown v-if="!collapsed" :size="14" class="profile-chevron" />
        </button>
        <button class="collapse-toggle" @click="collapsed = !collapsed" :title="collapsed ? '展开侧边栏' : '收起侧边栏'">
          <PanelLeftOpen v-if="collapsed" :size="17" :stroke-width="1.5" />
          <PanelLeftClose v-else :size="17" :stroke-width="1.5" />
        </button>
      </div>
    </aside>

    <div
      class="sidebar-resizer"
      aria-hidden="true"
      title="拖拽调整侧边栏宽度"
      @mousedown.prevent="startResize"
    />

    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-shell { height: 100vh; display: flex; overflow: hidden; background: var(--page); }
.app-shell.is-resizing { cursor: col-resize; user-select: none; }
.app-sidebar { flex: 0 0 auto; width: var(--sidebar-width); min-height: 0; display: flex; flex-direction: column; padding: 27px 18px 18px; background: var(--sidebar); border-right: 1px solid var(--line); transition: width .22s ease; }
.is-resizing .app-sidebar { transition: none; }
.is-collapsed .app-sidebar { width: var(--sidebar-collapsed-width); padding-inline: 12px; align-items: center; }
.sidebar-resizer { flex: 0 0 6px; cursor: col-resize; background: transparent; }
.sidebar-resizer:hover, .is-resizing .sidebar-resizer { background: var(--line); }
.is-collapsed .sidebar-resizer { display: none; }
.app-main { flex: 1; min-width: 0; min-height: 0; overflow-y: auto; background: var(--page); }
.brand-row { display: flex; align-items: center; gap: 10px; min-height: 34px; padding: 0 3px; cursor: pointer; }
.brand-mark { display: grid; place-items: center; color: var(--ink); }
.brand-name { font-family: var(--font-display); font-size: 21px; letter-spacing: -.02em; white-space: nowrap; }
.new-chat, .section-toggle, .conversation-item, .nav-item, .bottom-links button, .profile-chip, .collapse-toggle { border: 0; background: transparent; cursor: pointer; }
.new-chat { display: flex; align-items: center; justify-content: center; gap: 9px; width: 100%; min-height: 42px; margin: 35px 0 27px; border: 1px solid #d9d1c3; border-radius: var(--radius-control); background: rgba(255,254,250,.34); font-size: 14px; }
.new-chat:hover, .conversation-item:hover, .bottom-links button:hover, .profile-chip:hover { background: rgba(255,255,255,.5); }
.sidebar-main { display: flex; flex: 1; min-height: 0; flex-direction: column; width: 100%; }
.history-section { display: flex; flex: 1 1 auto; min-height: 0; flex-direction: column; padding-bottom: 18px; border-bottom: 1px solid var(--line); overflow: hidden; transition: opacity .16s ease, flex-basis .22s ease; }
.is-collapsed .history-section { flex: 0 0 0; padding: 0; border-bottom: 0; opacity: 0; pointer-events: none; visibility: hidden; }
.history-section.is-history-collapsed { flex: 0 0 auto; padding-bottom: 0; border-bottom: 0; }
.section-toggle { display: flex; justify-content: space-between; align-items: center; width: 100%; padding: 0 4px 10px; color: var(--ink); font-size: 13px; }
.section-toggle svg { transition: transform .2s ease; }.section-toggle svg.rotated { transform: rotate(-90deg); }
.conversation-list { display: grid; flex: 1; min-height: 0; align-content: start; gap: 2px; overflow-y: auto; overscroll-behavior: contain; scrollbar-width: thin; scrollbar-color: #cfc7ba transparent; }
/* minmax(0,1fr) 而非默认 auto：标题是 nowrap，默认列宽按 max-content 计算会把整列撑出侧栏 */
.conversation-list { grid-template-columns: minmax(0, 1fr); }
.conversation-state { padding: 8px 4px; color: var(--soft-muted); font-size: 12px; }
/* 一行 = 会话按钮 + hover 才出现的 [⋮]；浮层在同一 .conversation-row 内向下展开，
   因此不会被 .conversation-list 的 overflow 裁掉，也无需全屏对话框。 */
.conversation-row { display: grid; gap: 2px; min-width: 0; }
.conversation-line { display: flex; align-items: center; gap: 2px; min-width: 0; border-radius: 8px; }
.conversation-line:hover { background: rgba(255,255,255,.5); }
.conversation-item { display: flex; align-items: center; gap: 9px; flex: 1; min-width: 0; padding: 8px 4px; color: var(--muted); text-align: left; font-size: 12px; border: 0; background: transparent; cursor: pointer; border-radius: 8px; }
.row-more { display: grid; place-items: center; flex: 0 0 auto; width: 26px; height: 26px; margin-right: 2px; border: 0; border-radius: 7px; background: transparent; color: var(--soft-muted); cursor: pointer; opacity: 0; transition: opacity .14s ease, background .14s ease, color .14s ease; }
/* 悬停或已展开时才显示按钮：静止列表保持干净，也避免误触 */
.conversation-line:hover .row-more, .row-more:focus-visible, .conversation-row.is-menu-open .row-more, .conversation-row.is-confirming .row-more { opacity: 1; }
.row-more:hover, .row-more:focus-visible { background: rgba(255,255,255,.9); color: var(--ink); }
.status-dot { width: 7px; height: 7px; flex: 0 0 auto; border-radius: 50%; background: #6fbea1; }.conversation-title { overflow: hidden; flex: 1; text-overflow: ellipsis; white-space: nowrap; }.conversation-item time { color: var(--soft-muted); font-size: 11px; }
/* 行内重命名：替换整行内容，避免与列表布局打架 */
.conversation-rename { flex: 1; min-width: 0; margin: 6px 4px; padding: 3px 7px; border: 1px solid var(--sage); border-radius: 7px; background: var(--surface); color: var(--ink); font-size: 12px; outline: none; }
/* 行内小浮层：紧贴现所在行向下展开，宽高由内容决定，不做全屏遮罩 */
.row-menu, .row-confirm { min-width: 0; margin: 0 4px 4px 24px; padding: 5px; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); box-shadow: 0 6px 18px rgba(36,35,31,.09); }
.row-menu { display: grid; gap: 1px; }
.row-menu button { display: flex; align-items: center; gap: 8px; width: 100%; padding: 6px 8px; border: 0; border-radius: 7px; background: transparent; color: var(--muted); text-align: left; font-size: 12px; cursor: pointer; }
.row-menu button:hover { background: var(--surface-muted); color: var(--ink); }
.row-menu button.is-danger:hover { background: var(--clay-soft); color: #a4553c; }
.row-confirm { display: grid; gap: 4px; padding: 9px 10px; }
.row-confirm p { margin: 0; overflow: hidden; color: var(--ink); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.confirm-sub { color: var(--soft-muted); font-size: 11px; line-height: 1.4; }
.confirm-actions { display: flex; justify-content: flex-end; gap: 6px; margin-top: 3px; }
.confirm-actions button { padding: 4px 10px; border: 1px solid var(--line); border-radius: 7px; background: transparent; color: var(--muted); font-size: 12px; cursor: pointer; }
.confirm-actions button:hover:not(:disabled) { background: var(--surface-muted); color: var(--ink); }
.confirm-actions button.is-danger { border-color: var(--clay); background: var(--clay); color: #fff; }
.confirm-actions button.is-danger:hover:not(:disabled) { background: #b87d66; }
.confirm-actions button:disabled { opacity: .6; cursor: default; }
.primary-nav { display: grid; flex: 0 0 auto; gap: 4px; padding-top: 16px; }
.nav-item { position: relative; display: flex; align-items: center; gap: 13px; width: 100%; min-height: 43px; padding: 0 12px; border-radius: 9px; color: var(--muted); text-align: left; font-size: 14px; transition: background .16s ease, color .16s ease; }
.is-collapsed .nav-item { justify-content: center; width: 43px; padding: 0; }.nav-item:hover { color: var(--ink); background: rgba(255,255,255,.48); }.nav-item.active { color: var(--ink); background: var(--sage-soft); }.nav-item.active::before { position: absolute; left: -18px; width: 3px; height: 24px; border-radius: 0 3px 3px 0; background: var(--sage); content: ''; }.is-collapsed .nav-item.active::before { left: -12px; }
.sidebar-bottom { display: grid; gap: 12px; margin-top: auto; padding-top: 16px; border-top: 1px solid var(--line); }.bottom-links { display: flex; gap: 7px; }.bottom-links button { display: inline-flex; align-items: center; gap: 6px; padding: 5px 4px; color: var(--muted); font-size: 12px; }.profile-chip { display: flex; align-items: center; gap: 9px; width: 100%; padding: 5px 4px; color: var(--muted); text-align: left; }.avatar { display: grid; place-items: center; width: 31px; height: 31px; border: 1px solid #d5cec2; border-radius: 50%; color: var(--muted); }.profile-chevron { margin-left: auto; }.collapse-toggle { display: flex; justify-content: center; align-items: center; width: 100%; min-height: 31px; color: var(--soft-muted); }.collapse-toggle:hover { color: var(--ink); }
@media (max-width: 900px) { .app-sidebar { width: var(--sidebar-collapsed-width); padding-inline: 12px; align-items: center; }.sidebar-resizer { display: none; }.brand-name, .new-chat span, .history-section, .nav-item span, .bottom-links, .profile-chip > span:not(.avatar), .profile-chevron { display: none; }.new-chat { width: 43px; padding: 0; }.nav-item { justify-content: center; width: 43px; padding: 0; }.nav-item.active::before { left: -12px; } }
</style>
