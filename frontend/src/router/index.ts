import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'Home',
      component: () => import('../views/Home.vue'),
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          redirect: '/dashboard'
        },
        {
          path: 'dashboard',
          name: 'Dashboard',
          component: () => import('../views/Dashboard.vue')
        },
        {
          path: 'profile-chat',
          name: 'ProfileChat',
          component: () => import('../views/ProfileChat.vue')
        },
        {
          path: 'resource-center',
          name: 'ResourceCenter',
          component: () => import('../views/ResourceCenter.vue')
        },
        {
          path: 'learning-path',
          name: 'LearningPath',
          component: () => import('../views/LearningPath.vue')
        },
        {
          path: 'ai-tutor',
          name: 'AITutor',
          component: () => import('../views/AITutor.vue')
        },
        {
          path: 'course-detail',
          name: 'CourseDetail',
          component: () => import('../views/CourseDetail.vue')
        },
        {
          path: 'exercise',
          name: 'ExercisePage',
          component: () => import('../views/ExercisePage.vue')
        },
        {
          path: 'learning-resource-network',
          name: 'LearningResourceNetwork',
          component: () => import('../views/LearningResourceNetwork.vue')
        },
        {
          path: 'question-nav-chat',
          name: 'QuestionNavChat',
          component: () => import('../views/QuestionNavChat.vue')
        }
      ]
    },
    {
      path: '/loginRegister',
      name: 'LoginRegister',
      component: () => import('../views/LoginRegister.vue'),
      meta: { requiresGuest: true }
    }
  ]
})

// 全局路由守卫
router.beforeEach((to, from, next) => {
  const userStore = useUserStore()
  const isLoggedIn = userStore.isLoggedIn || localStorage.getItem('token')
  
  // 需要登录的页面
  if (to.meta.requiresAuth && !isLoggedIn) {
    next('/loginRegister')
    return
  }
  
  // 已登录用户访问登录页面，重定向到首页
  if (to.meta.requiresGuest && isLoggedIn) {
    next('/dashboard')
    return
  }
  
  next()
})

export default router
