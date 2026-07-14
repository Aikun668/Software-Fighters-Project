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
          redirect: '/question-nav-chat'
        },
        {
          path: 'dashboard',
          name: 'Dashboard',
          redirect: '/learning-analysis'
        },
        {
          path: 'profile-chat',
          name: 'ProfileChat',
          redirect: '/learning-analysis'
        },
        {
          path: 'resource-center',
          name: 'ResourceCenter',
          component: () => import('../views/ModulePreview.vue'),
          meta: { title: '资源工坊', eyebrow: '把知识整理成适合你的材料', icon: 'resource' }
        },
        {
          path: 'learning-path',
          name: 'LearningPath',
          component: () => import('../views/ModulePreview.vue'),
          meta: { title: '学习计划', eyebrow: '把目标变成今天可以完成的任务', icon: 'plan' }
        },
        {
          path: 'ai-tutor',
          name: 'AITutor',
          component: () => import('../views/ModulePreview.vue'),
          meta: { title: '对话辅导', eyebrow: '从一个问题开始你的学习', icon: 'chat' }
        },
        {
          path: 'course-detail',
          name: 'CourseDetail',
          component: () => import('../views/ModulePreview.vue'),
          meta: { title: '课程内容', eyebrow: '把知识拆成可以理解的章节', icon: 'course' }
        },
        {
          path: 'exercise',
          name: 'ExercisePage',
          component: () => import('../views/ModulePreview.vue'),
          meta: { title: '练习中心', eyebrow: '用练习确认真正掌握的知识', icon: 'exercise' }
        },
        {
          path: 'learning-resource-network',
          name: 'LearningResourceNetwork',
          component: () => import('../views/ModulePreview.vue'),
          meta: { title: '知识图谱', eyebrow: '探索你的知识结构', icon: 'network' }
        },
        {
          path: 'learning-analysis',
          name: 'LearningAnalysis',
          component: () => import('../views/ModulePreview.vue'),
          meta: { title: '学情分析', eyebrow: '了解你的学习状态与下一步', icon: 'analysis' }
        },
        {
          path: 'question-nav-chat',
          name: 'QuestionNavChat',
          component: () => import('../views/QuestionNavChat.vue')
        }
      ]
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
