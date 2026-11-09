import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

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
  // S3-F1：教师端路由（裁定 5 纳入全局导航；并列路由，App.vue 提供布局）
  { path: '/teacher', name: 'teacher-dashboard', component: () => import('../views/teacher/TeacherDashboardView.vue') },
  { path: '/teacher/courses/:id', name: 'teacher-course', component: () => import('../views/teacher/CourseTasksView.vue') },
  // S3-F3：提交查看页（GET /api/tasks/:id/submissions）
  { path: '/teacher/courses/:id/tasks/:tid', name: 'teacher-task', component: () => import('../views/teacher/TaskDetailView.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// S3-F3：/teacher/* 是教师路由——学生/未登录不进（用户 2026-11-09 确认要拦截）。
// 未登录 → 跳 /login 带 redirect；已登录但无 teacher 角色 → 回学生工作台。
router.beforeEach(async (to) => {
  if (!to.path.startsWith('/teacher')) return true
  const auth = useAuthStore()
  if (!auth.user) {
    try {
      await auth.fetchMe()
    } catch {
      return { path: '/login', query: { redirect: to.fullPath } }
    }
  }
  if (!auth.roles.includes('teacher')) {
    return { path: '/dashboard' }
  }
  return true
})

export default router
