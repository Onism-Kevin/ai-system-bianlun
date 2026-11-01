import { createRouter, createWebHistory } from 'vue-router'

// S2-F1 骨架路由（用户指定五条）；业务逻辑（守卫/参数/嵌套）后续任务补
const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue') },
  { path: '/dashboard', name: 'dashboard', component: () => import('../views/DashboardView.vue') },
  { path: '/training', name: 'training', component: () => import('../views/TrainingView.vue') },
  { path: '/review', name: 'review', component: () => import('../views/ReviewView.vue') },
  { path: '/graph', name: 'graph', component: () => import('../views/GraphView.vue') },
  // S2-F8：训练历史页（GET /api/history + /api/history/{id}，api.md:40-41）
  { path: '/history', name: 'history', component: () => import('../views/HistoryView.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
