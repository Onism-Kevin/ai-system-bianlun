<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import HealthBadge from './HealthBadge.vue'

// S3-F1 commit A：全局顶部导航栏（裁定 5：全局导航纳入 S3-F1）。
//
// 链接显示矩阵（用户 2026-11-08 确认）：
//   工作台  —— 始终显示，按角色分流（教师 → /teacher，学生 → /dashboard）
//   训练/历史/复盘 —— 只对学生显示（教师的"训练"是 S3-6 drill，S3-F4 才加入口）
//   教师端  —— 只对教师显示
//
// 说明：教师专属用户的"工作台"与"教师端"都指向 /teacher（用户矩阵的字面要求）；
// 双角色用户的"工作台"按 teacher 优先 → /teacher，教师端同指。
const auth = useAuthStore()
const route = useRoute()

const isStudent = computed(() => auth.roles.includes('student'))
const isTeacher = computed(() => auth.roles.includes('teacher'))

// 工作台按角色分流：教师 → /teacher，否则 → /dashboard
const homePath = computed(() => (isTeacher.value ? '/teacher' : '/dashboard'))

interface NavItem {
  path: string
  label: string
}

const navItems = computed<NavItem[]>(() => {
  const items: NavItem[] = [{ path: homePath.value, label: '工作台' }]
  if (isStudent.value) {
    items.push({ path: '/training', label: '训练' })
    items.push({ path: '/history', label: '历史' })
    items.push({ path: '/review', label: '复盘' })
  }
  if (isTeacher.value) {
    items.push({ path: '/teacher', label: '教师端' })
  }
  return items
})

function isActive(path: string): boolean {
  if (path === '/teacher') return route.path.startsWith('/teacher')
  return route.path === path
}

const displayName = computed(
  () => auth.user?.display_name || auth.user?.username || '',
)
const roleLabel = computed(() => {
  const roles = auth.roles
  if (roles.includes('teacher') && roles.includes('student')) return '师生'
  if (roles.includes('teacher')) return '教师'
  return '学生'
})
</script>

<template>
  <header class="app-header">
    <div class="header-inner">
      <div class="brand">
        <span class="brand-name">思辨工坊</span>
      </div>

      <nav class="nav">
        <router-link
          v-for="item in navItems"
          :key="item.path + item.label"
          :to="item.path"
          class="nav-link"
          :class="{ active: isActive(item.path) }"
        >
          {{ item.label }}
        </router-link>
      </nav>

      <div class="header-right">
        <span v-if="auth.user" class="user-info">
          <el-tag size="small" :type="roleLabel === '教师' ? 'warning' : 'primary'" effect="plain">
            {{ roleLabel }}
          </el-tag>
          <span class="user-name">{{ displayName }}</span>
        </span>
        <HealthBadge />
      </div>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.header-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 16px;
  height: 56px;
  display: flex;
  align-items: center;
  gap: 24px;
}
.brand-name {
  font-size: 17px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}
.nav {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1;
  flex-wrap: wrap;
}
.nav-link {
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 14px;
  color: var(--el-text-color-regular);
  text-decoration: none;
}
.nav-link:hover {
  background: var(--el-fill-color-light);
  color: var(--el-color-primary);
}
.nav-link.active {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 600;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.user-name {
  color: var(--el-text-color-regular);
}
</style>
