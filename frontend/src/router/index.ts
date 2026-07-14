import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'Home',
      component: () => import('../views/Home.vue'),
      children: [
        { path: '', name: 'HomeIndex', redirect: '/question-nav-chat' },
        { path: 'dashboard', name: 'Dashboard', redirect: '/learning-analysis' },
        { path: 'profile-chat', name: 'ProfileChat', redirect: '/learning-analysis' },
        { path: 'resource-center', name: 'ResourceCenter', component: () => import('../views/ResourceCenterPage.vue') },
        { path: 'learning-path', name: 'LearningPath', component: () => import('../views/LearningPlanPage.vue') },
        { path: 'ai-tutor', name: 'AITutor', component: () => import('../views/ModulePreview.vue') },
        { path: 'course-detail', name: 'CourseDetail', component: () => import('../views/ModulePreview.vue') },
        { path: 'exercise', name: 'ExercisePage', component: () => import('../views/ExerciseCenterPage.vue') },
        { path: 'learning-resource-network', name: 'LearningResourceNetwork', component: () => import('../views/KnowledgeGraphPage.vue') },
        { path: 'learning-analysis', name: 'LearningAnalysis', component: () => import('../views/LearningAnalysisPage.vue') },
        { path: 'question-nav-chat', name: 'QuestionNavChat', component: () => import('../views/QuestionNavChat.vue') },
      ],
    },
  ],
})

export default router
