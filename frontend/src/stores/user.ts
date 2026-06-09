import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { UserProfile } from '@/types'

/**
 * 用户状态管理Store
 * 负责管理学生画像和登录状态
 * 
 * @description
 * 核心功能：
 * - 存储用户基本信息（姓名、专业、年级等）
 * - 管理登录状态
 * - 提供计算属性获取用户名
 * - 支持用户画像的设置和清除
 */
export const useUserStore = defineStore('user', () => {
  // 状态定义
  const profile = ref<UserProfile | null>(null)  // 用户详细信息
  const isLoggedIn = ref(false)                  // 登录状态

  // 计算属性：获取用户名，默认显示"用户"
  const userName = computed(() => profile.value?.name || '用户')

  /**
   * 设置用户画像
   * @param user - 用户信息对象
   */
  function setProfile(user: UserProfile) {
    profile.value = user
    isLoggedIn.value = true
  }

  /**
   * 退出登录
   * 清空用户信息和登录状态
   */
  function logout() {
    profile.value = null
    isLoggedIn.value = false
  }

  return {
    profile,
    isLoggedIn,
    userName,
    setProfile,
    logout
  }
}, {
  persist: {
    key: 'user-store',
    storage: localStorage,
    // @ts-ignore
    paths: ['profile', 'isLoggedIn']
  }
})