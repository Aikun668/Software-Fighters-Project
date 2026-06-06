<template>
  <div class="home-container">
    <header class="home-header">
      <div class="header-left">
        <div class="logo-wrapper">
          <div class="logo-icon">
            <el-icon :size="28"><Odometer /></el-icon>
          </div>
          <div class="logo-text">
            <h1 class="logo-title">智学云</h1>
            <span class="logo-subtitle">个性化学习多智能体系统</span>
          </div>
        </div>
      </div>
      <div class="header-right">
        <div class="user-actions">
          <el-button type="primary" size="default" class="login-btn" @click="goToLogin">
            <el-icon><User /></el-icon>
            <span>登录 / 注册</span>
          </el-button>
        </div>
      </div>
    </header>

    <div class="home-content">
      <aside :class="['sidebar', { collapsed: isCollapsed }]">
       
        <el-menu
          :default-active="activeMenu"
          class="sidebar-menu"
          @select="handleMenuSelect"
        >
          <el-menu-item index="dashboard">
            <el-icon><Odometer /></el-icon>
            <span>学习仪表盘</span>
          </el-menu-item>
          <el-menu-item index="profile-chat">
            <el-icon><User /></el-icon>
            <span>学生画像</span>
          </el-menu-item>
          <el-menu-item index="resource-center">
            <el-icon><Files /></el-icon>
            <span>资源中心</span>
          </el-menu-item>
          <el-menu-item index="learning-path">
            <el-icon><Guide /></el-icon>
            <span>学习路径</span>
          </el-menu-item>
          <el-menu-item index="ai-tutor">
            <el-icon><ChatDotRound /></el-icon>
            <span>智能答疑</span>
          </el-menu-item>
          <el-menu-item index="course-detail">
            <el-icon><Document /></el-icon>
            <span>课程文档</span>
          </el-menu-item>
          <el-menu-item index="exercise">
            <el-icon><EditPen /></el-icon>
            <span>在线答题</span>
          </el-menu-item>
        </el-menu>

        <div class="sidebar-footer">


          <button class="collapse-btn" @click="toggleSidebar" :title="isCollapsed ? '展开侧边栏' : '收起侧边栏'">
            <svg v-if="isCollapsed" viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
              <path d="M9.29 6.71a.996.996 0 000 1.41L13.17 12l-3.88 3.88a.996.996 0 101.41 1.41l4.59-4.59a.996.996 0 000-1.41L10.7 6.7c-.38-.38-1.02-.38-1.41.01z"/>
            </svg>
            <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
              <path d="M15.29 17.71a.996.996 0 000-1.41L11.41 12l3.88-3.88a.996.996 0 00-1.41-1.41l-4.59 4.59a.996.996 0 000 1.41l4.59 4.59c.38.38 1.02.38 1.41 0z"/>
            </svg>
          </button>
        </div>
      </aside>

      <main :class="['main-content-wrapper', { 'sidebar-collapsed': isCollapsed }]">
        <div class="main-content">
          <router-view />
        </div>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { Odometer, User, Files, Guide, ChatDotRound, Document, EditPen } from '@element-plus/icons-vue';

const router = useRouter();
const route = useRoute();

const isCollapsed = ref(false);

const activeMenu = computed(() => {
  const path = route.path.split('/').pop() || 'dashboard';
  return path;
});

const handleMenuSelect = (index: string) => {
  router.push(`/${index}`);
};

const goToLogin = () => {
  router.push('/loginRegister');
};

const toggleSidebar = () => {
  isCollapsed.value = !isCollapsed.value;
};
</script>

<style scoped>
.home-container {
  min-height: 100vh;
  background: var(--bg-page);
  display: flex;
  flex-direction: column;
}

.home-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 28px;
  height: var(--header-height);
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border-color);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
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
  gap: 14px;
}

.logo-icon {
  width: 44px;
  height: 44px;
  background: var(--gradient-primary);
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  box-shadow: 0 8px 24px rgba(194, 65, 12, 0.25);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.logo-icon:hover {
  transform: translateY(-2px) scale(1.02);
  box-shadow: 0 12px 32px rgba(194, 65, 12, 0.35);
}

.logo-text {
  display: flex;
  flex-direction: column;
}

.logo-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  background: var(--gradient-primary);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: 1.2;
}

.logo-subtitle {
  font-size: 12px;
  color: var(--text-placeholder);
  margin-top: 2px;
}

.header-right {
  display: flex;
  align-items: center;
}

.login-btn {
  background: var(--gradient-primary);
  border: none;
  color: #ffffff;
  font-weight: 600;
  padding: 10px 24px;
  border-radius: 12px;
  box-shadow: 0 4px 14px rgba(194, 65, 12, 0.2);
  transition: all 0.2s ease;
}

.login-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(194, 65, 12, 0.3);
}

.home-content {
  display: flex;
  min-height: calc(100vh - var(--header-height));
  position: relative;
}

.sidebar {
  width: var(--sidebar-width);
  background: #ffffff;
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  position: fixed;
  left: 0;
  top: var(--header-height);
  bottom: 0;
  overflow-y: auto;
  z-index: 50;
  transition: width 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

.sidebar.collapsed {
  width: var(--sidebar-collapsed-width);
}

.sidebar-header {
  padding: 16px 12px;
  border-bottom: 1px solid var(--border-color);
}

.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 8px;
}

.logo-mini {
  width: 32px;
  height: 32px;
  background: var(--gradient-primary);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
}

.logo-text {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.sidebar-menu {
  border: none;
  padding: 12px 8px;
}

.sidebar-menu .el-menu-item {
  margin: 4px 8px;
  border-radius: 10px;
  height: 48px;
  line-height: 48px;
  font-weight: 500;
  color: var(--text-secondary);
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
}

.sidebar-menu .el-menu-item:hover {
  background: var(--primary-bg);
  color: var(--primary-color);
}

.sidebar-menu .el-menu-item.is-active {
  background: var(--gradient-primary);
  color: #ffffff;
  box-shadow: 0 4px 14px rgba(194, 65, 12, 0.25);
}

.sidebar-menu .el-menu-item.is-active .el-icon {
  color: #ffffff;
}

.sidebar-menu .el-menu-item .el-icon {
  font-size: 18px;
  margin-right: 10px;
  color: var(--text-secondary);
  transition: color 0.2s ease;
}

.sidebar-footer {
  padding: 16px 20px;
  border-top: 1px solid var(--border-color);
  background: linear-gradient(180deg, transparent 0%, rgba(239, 246, 255, 0.5) 100%);
  margin-top: auto;
}

.quick-stats {
  display: flex;
  align-items: center;
  justify-content: space-around;
  padding: 14px;
  background: var(--bg-page);
  border-radius: 14px;
  border: 1px solid var(--border-color);
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  background: var(--gradient-primary);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.stat-label {
  font-size: 12px;
  color: var(--text-placeholder);
}

.stat-divider {
  width: 1px;
  height: 36px;
  background: var(--border-color);
}

.collapse-btn {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--primary-color) 0%, var(--primary-light) 100%);
  color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  margin: 0 auto;
  margin-top: 16px;
  margin-bottom: 16px;
  transition: all 0.2s ease;
  border: none;
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
  position: relative;
  z-index: 10;
}

.collapse-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(79, 70, 229, 0.4);
}

.collapse-btn:active {
  transform: translateY(0);
  box-shadow: 0 2px 8px rgba(79, 70, 229, 0.3);
}

.sidebar.collapsed .sidebar-menu .el-menu-item {
  padding: 0;
  justify-content: center;
  margin: 4px 6px;
}

.sidebar.collapsed .sidebar-menu .el-menu-item span {
  display: none;
}

.sidebar.collapsed .sidebar-menu .el-menu-item .el-icon {
  margin-right: 0;
  margin-left: 0;
  font-size: 20px;
}

.main-content-wrapper {
  flex: 1;
  margin-left: var(--sidebar-width);
  min-height: calc(100vh - var(--header-height));
  transition: margin-left 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

.main-content-wrapper.sidebar-collapsed {
  margin-left: var(--sidebar-collapsed-width);
}

.main-content {
  padding: 28px;
  min-height: 100%;
  height: calc(100vh - var(--header-height));
  overflow-y: auto;
  background: var(--bg-page);
}

@media (max-width: 768px) {
  .sidebar {
    width: var(--sidebar-collapsed-width);
  }

  .sidebar-menu .el-menu-item span {
    display: none;
  }

  .sidebar-menu .el-menu-item .el-icon {
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

  .main-content {
    padding: 16px;
  }
}
</style>
