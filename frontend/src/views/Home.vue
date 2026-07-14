<script setup lang="ts">
import { computed, ref } from 'vue'
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
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  PencilLine,
  Plus,
  Settings2,
  CircleHelp,
  UserRound,
} from '@lucide/vue'

const router = useRouter()
const route = useRoute()
const collapsed = ref(false)
const historyOpen = ref(true)

const conversations = [
  { title: '生成式模型的注意力机制', time: '14:32' },
  { title: '傅里叶变换可视化探索', time: '昨天' },
  { title: '作为计算机专业的学习路径', time: '周二' },
]

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
</script>

<template>
  <div class="app-shell" :class="{ 'is-collapsed': collapsed }">
    <aside class="app-sidebar">
      <div class="brand-row" @click="go('/question-nav-chat')">
        <div class="brand-mark" aria-hidden="true"><BookOpen :size="22" :stroke-width="1.45" /></div>
        <span v-if="!collapsed" class="brand-name">智学tutor</span>
      </div>

      <button class="new-chat" @click="go('/question-nav-chat')">
        <Plus :size="18" :stroke-width="1.6" />
        <span v-if="!collapsed">新建对话</span>
      </button>

      <section v-if="!collapsed" class="history-section">
        <button class="section-toggle" @click="historyOpen = !historyOpen">
          <span>最近对话</span>
          <ChevronDown :size="15" :class="{ rotated: !historyOpen }" />
        </button>
        <div v-if="historyOpen" class="conversation-list">
          <button v-for="item in conversations" :key="item.title" class="conversation-item" @click="go('/question-nav-chat')">
            <span class="status-dot" />
            <span class="conversation-title">{{ item.title }}</span>
            <time>{{ item.time }}</time>
          </button>
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

    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-shell { min-height: 100vh; display: flex; background: var(--page); }
.app-sidebar { position: fixed; inset: 0 auto 0 0; width: var(--sidebar-width); display: flex; flex-direction: column; padding: 27px 18px 18px; background: var(--sidebar); border-right: 1px solid var(--line); transition: width .22s ease; z-index: 2; }
.is-collapsed .app-sidebar { width: var(--sidebar-collapsed-width); padding-inline: 12px; align-items: center; }
.app-main { width: calc(100% - var(--sidebar-width)); min-height: 100vh; margin-left: var(--sidebar-width); transition: width .22s ease, margin-left .22s ease; }
.is-collapsed .app-main { width: calc(100% - var(--sidebar-collapsed-width)); margin-left: var(--sidebar-collapsed-width); }
.brand-row { display: flex; align-items: center; gap: 10px; min-height: 34px; padding: 0 3px; cursor: pointer; }
.brand-mark { display: grid; place-items: center; color: var(--ink); }
.brand-name { font-family: var(--font-display); font-size: 21px; letter-spacing: -.02em; white-space: nowrap; }
.new-chat, .section-toggle, .conversation-item, .nav-item, .bottom-links button, .profile-chip, .collapse-toggle { border: 0; background: transparent; cursor: pointer; }
.new-chat { display: flex; align-items: center; justify-content: center; gap: 9px; width: 100%; min-height: 42px; margin: 35px 0 27px; border: 1px solid #d9d1c3; border-radius: var(--radius-control); background: rgba(255,254,250,.34); font-size: 14px; }
.new-chat:hover, .conversation-item:hover, .bottom-links button:hover, .profile-chip:hover { background: rgba(255,255,255,.5); }
.history-section { padding-bottom: 18px; border-bottom: 1px solid var(--line); }
.section-toggle { display: flex; justify-content: space-between; align-items: center; width: 100%; padding: 0 4px 10px; color: var(--ink); font-size: 13px; }
.section-toggle svg { transition: transform .2s ease; }.section-toggle svg.rotated { transform: rotate(-90deg); }
.conversation-list { display: grid; gap: 2px; }
.conversation-item { display: flex; align-items: center; gap: 9px; width: 100%; min-width: 0; padding: 8px 4px; color: var(--muted); text-align: left; font-size: 12px; }
.status-dot { width: 7px; height: 7px; flex: 0 0 auto; border-radius: 50%; background: #6fbea1; }.conversation-title { overflow: hidden; flex: 1; text-overflow: ellipsis; white-space: nowrap; }.conversation-item time { color: var(--soft-muted); font-size: 11px; }
.primary-nav { display: grid; gap: 4px; padding-top: 20px; }
.nav-item { position: relative; display: flex; align-items: center; gap: 13px; width: 100%; min-height: 43px; padding: 0 12px; border-radius: 9px; color: var(--muted); text-align: left; font-size: 14px; transition: background .16s ease, color .16s ease; }
.is-collapsed .nav-item { justify-content: center; width: 43px; padding: 0; }.nav-item:hover { color: var(--ink); background: rgba(255,255,255,.48); }.nav-item.active { color: var(--ink); background: var(--sage-soft); }.nav-item.active::before { position: absolute; left: -18px; width: 3px; height: 24px; border-radius: 0 3px 3px 0; background: var(--sage); content: ''; }.is-collapsed .nav-item.active::before { left: -12px; }
.sidebar-bottom { display: grid; gap: 12px; margin-top: auto; padding-top: 16px; border-top: 1px solid var(--line); }.bottom-links { display: flex; gap: 7px; }.bottom-links button { display: inline-flex; align-items: center; gap: 6px; padding: 5px 4px; color: var(--muted); font-size: 12px; }.profile-chip { display: flex; align-items: center; gap: 9px; width: 100%; padding: 5px 4px; color: var(--muted); text-align: left; }.avatar { display: grid; place-items: center; width: 31px; height: 31px; border: 1px solid #d5cec2; border-radius: 50%; color: var(--muted); }.profile-chevron { margin-left: auto; }.collapse-toggle { display: flex; justify-content: center; align-items: center; width: 100%; min-height: 31px; color: var(--soft-muted); }.collapse-toggle:hover { color: var(--ink); }
@media (max-width: 900px) { .app-sidebar { width: var(--sidebar-collapsed-width); padding-inline: 12px; align-items: center; }.app-main { width: calc(100% - var(--sidebar-collapsed-width)); margin-left: var(--sidebar-collapsed-width); }.brand-name, .new-chat span, .history-section, .nav-item span, .bottom-links, .profile-chip > span:not(.avatar), .profile-chevron { display: none; }.new-chat { width: 43px; padding: 0; }.nav-item { justify-content: center; width: 43px; padding: 0; }.nav-item.active::before { left: -12px; } }
</style>
