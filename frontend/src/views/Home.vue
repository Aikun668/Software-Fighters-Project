<template>
  <div class="home-container">
    <header class="home-header">
      <div class="header-left">
        <div class="logo-wrapper">
          <div class="logo-icon">
            <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2L2 7l10 5 10-5-10-5z"/>
              <path d="M2 17l10 5 10-5"/>
              <path d="M2 12l10 5 10-5"/>
            </svg>
          </div>
          <div class="logo-text">
            <h1 class="logo-title">智学云</h1>
            <span class="logo-subtitle">DeepTutor 智能学习系统</span>
          </div>
        </div>
      </div>
      <div class="header-right">
        <div class="header-actions">
          <button class="icon-btn" title="通知">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
              <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
            </svg>
          </button>
          <button class="icon-btn" title="设置">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
          </button>
        </div>
        <div class="user-info-wrapper">
          <div class="user-avatar">
            <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
          </div>
          <div class="user-detail">
            <span class="user-name">{{ userStore.userName }}</span>
            <span class="user-status">在线</span>
          </div>
          <button class="logout-btn" @click="handleLogout" title="退出登录">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
          </button>
        </div>
      </div>
    </header>

    <div class="home-content">
      <!-- 左侧导航栏 -->
      <aside :class="['sidebar', { collapsed: isCollapsed }]">
        <!-- 全局动作区 -->
        <div class="nav-section">
          <button class="new-chat-btn" @click="createNewChat">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            <span>新建对话</span>
          </button>
        </div>

        <!-- 核心功能区 -->
        <div class="nav-section">
          <div class="section-title">核心功能</div>
          <el-menu
            :default-active="activeMenu"
            class="sidebar-menu"
            @select="handleMenuSelect"
          >
            <el-menu-item index="question-nav-chat">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
              <span>对话辅导</span>
            </el-menu-item>
          </el-menu>
        </div>

        <!-- 个人学习产出区 -->
        <div class="nav-section">
          <div class="section-title">个人学习</div>
          <el-menu
            :default-active="activeMenu"
            class="sidebar-menu"
            @select="handleMenuSelect"
          >
            <el-menu-item index="learning-plan">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
              </svg>
              <span>我的计划</span>
            </el-menu-item>
            <el-menu-item index="exercise">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
              </svg>
              <span>练习中心</span>
            </el-menu-item>
            <el-menu-item index="resource-center">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
              <span>资源工坊</span>
            </el-menu-item>
            <el-menu-item index="learning-resource-network">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="18" cy="5" r="3"/>
                <circle cx="6" cy="12" r="3"/>
                <circle cx="18" cy="19" r="3"/>
                <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>
                <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
              </svg>
              <span>知识图谱</span>
            </el-menu-item>
          </el-menu>
        </div>

        <!-- 数据&个人区 -->
        <div class="nav-section">
          <div class="section-title">数据&个人</div>
          <el-menu
            :default-active="activeMenu"
            class="sidebar-menu"
            @select="handleMenuSelect"
          >
            <el-menu-item index="dashboard">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="3" width="7" height="7"/>
                <rect x="14" y="3" width="7" height="7"/>
                <rect x="14" y="14" width="7" height="7"/>
                <rect x="3" y="14" width="7" height="7"/>
              </svg>
              <span>数据看板</span>
            </el-menu-item>
            <el-menu-item index="profile-chat">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
              <span>学习画像</span>
            </el-menu-item>
          </el-menu>
        </div>

        <!-- 折叠按钮 -->
        <div class="sidebar-footer">
          <button class="collapse-btn" @click="toggleSidebar" :title="isCollapsed ? '展开侧边栏' : '收起侧边栏'">
            <svg v-if="isCollapsed" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
            <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
          </button>
        </div>
      </aside>

      <!-- 主内容区 -->
      <main :class="['main-content-wrapper', { 'sidebar-collapsed': isCollapsed }]">
        <div class="main-content">
          <router-view />
        </div>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const isCollapsed = ref(false)

const activeMenu = computed(() => {
  const path = route.path.split('/').pop() || 'dashboard'
  return path
})

const handleMenuSelect = (index: string) => {
  router.push(`/${index}`)
}

const goToLogin = () => {
  router.push('/loginRegister')
}

const handleLogout = () => {
  userStore.logout()
  localStorage.removeItem('token')
  router.push('/loginRegister')
}

const createNewChat = () => {
  router.push('/question-nav-chat')
}

const toggleSidebar = () => {
  isCollapsed.value = !isCollapsed.value
}
</script>

<style scoped>
.home-container {
  height: 100vh;
  background: var(--bg-page);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.home-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  height: var(--header-height);
  background: var(--bg-card);
  border-bottom: 1px solid var(--border-color);
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-left {
  flex: 1;
}

.logo-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-icon {
  width: 40px;
  height: 40px;
  background: var(--gradient-primary);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  box-shadow: 0 4px 12px rgba(34, 197, 94, 0.3);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.logo-icon:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(34, 197, 94, 0.4);
}

.logo-text {
  display: flex;
  flex-direction: column;
}

.logo-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
}

.logo-subtitle {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.icon-btn {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.icon-btn:hover {
  background: var(--primary-bg);
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.user-info-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 12px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  transition: all 0.2s ease;
}

.user-info-wrapper:hover {
  border-color: var(--primary-color);
  box-shadow: 0 2px 8px rgba(34, 197, 94, 0.15);
}

.user-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--gradient-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  flex-shrink: 0;
}

.user-detail {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.user-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.user-status {
  font-size: 12px;
  color: var(--primary-color);
}

.logout-btn {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.logout-btn:hover {
  background: var(--danger-bg);
  border-color: var(--danger-color);
  color: var(--danger-color);
}

.home-content {
  display: flex;
  flex: 1;
  position: relative;
  overflow: hidden;
}

.sidebar {
  width: var(--sidebar-width);
  background: var(--bg-card);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  position: fixed;
  left: 0;
  top: var(--header-height);
  bottom: 0;
  z-index: 50;
  transition: width 0.3s ease;
  overflow-y: auto;
  overflow-x: hidden;
}

.sidebar.collapsed {
  width: var(--sidebar-collapsed-width);
}

/* 导航区块 */
.nav-section {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-color);
}

.nav-section:last-of-type {
  border-bottom: none;
}

/* 新建对话按钮 */
.new-chat-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 16px;
  background: var(--gradient-primary);
  color: #ffffff;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 4px 12px rgba(34, 197, 94, 0.25);
}

.new-chat-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(34, 197, 94, 0.35);
}

.new-chat-btn svg {
  flex-shrink: 0;
}

/* 区块标题 */
.section-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-placeholder);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 8px 8px 4px 8px;
  margin-bottom: 4px;
}

/* 菜单样式 */
.sidebar-menu {
  border: none;
  background: transparent;
}

.sidebar-menu :deep(.el-menu-item) {
  margin: 2px 0;
  border-radius: 8px;
  height: 40px;
  line-height: 40px;
  font-weight: 500;
  color: var(--text-secondary);
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  padding: 0 12px !important;
}

.sidebar-menu :deep(.el-menu-item) svg {
  margin-right: 10px;
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.sidebar-menu :deep(.el-menu-item):hover {
  background: var(--primary-bg);
  color: var(--primary-color);
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  background: var(--gradient-primary);
  color: #ffffff;
  box-shadow: 0 4px 12px rgba(34, 197, 94, 0.25);
}

/* 折叠状态 */
.sidebar.collapsed .section-title,
.sidebar.collapsed .new-chat-btn span,
.sidebar.collapsed .sidebar-menu :deep(.el-menu-item) span {
  display: none;
}

.sidebar.collapsed .new-chat-btn {
  justify-content: center;
  padding: 10px;
}

.sidebar.collapsed .sidebar-menu :deep(.el-menu-item) {
  padding: 0 !important;
  justify-content: center;
}

.sidebar.collapsed .sidebar-menu :deep(.el-menu-item) svg {
  margin-right: 0;
}

/* 底部折叠按钮 */
.sidebar-footer {
  margin-top: auto;
  padding: 12px;
  border-top: 1px solid var(--border-color);
  background: linear-gradient(180deg, transparent 0%, rgba(34, 197, 94, 0.05) 100%);
}

.collapse-btn {
  width: 100%;
  height: 36px;
  border-radius: 8px;
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.collapse-btn:hover {
  background: var(--primary-bg);
  border-color: var(--primary-color);
  color: var(--primary-color);
}

/* 主内容区 */
.main-content-wrapper {
  flex: 1;
  margin-left: var(--sidebar-width);
  height: 100%;
  overflow-y: auto;
  transition: margin-left 0.3s ease;
}

.main-content-wrapper.sidebar-collapsed {
  margin-left: var(--sidebar-collapsed-width);
}

.main-content {
  /* padding: 24px; */
  min-height: 100%;
  box-sizing: border-box;
}

/* 响应式 */
@media (max-width: 768px) {
  .sidebar {
    width: var(--sidebar-collapsed-width);
  }

  .sidebar .section-title,
  .sidebar .new-chat-btn span,
  .sidebar-menu :deep(.el-menu-item) span {
    display: none;
  }

  .sidebar .new-chat-btn {
    justify-content: center;
    padding: 10px;
  }

  .sidebar-menu :deep(.el-menu-item) {
    padding: 0 !important;
    justify-content: center;
  }

  .sidebar-menu :deep(.el-menu-item) svg {
    margin-right: 0;
  }

  .sidebar-footer {
    display: none;
  }

  .logo-subtitle {
    display: none;
  }

  .main-content-wrapper {
    margin-left: var(--sidebar-collapsed-width);
  }
}
</style>
