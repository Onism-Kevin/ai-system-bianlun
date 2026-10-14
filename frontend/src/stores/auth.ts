import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getMe, login as loginApi } from '../api/auth'
import type { AuthUser } from '../api/types'

// S2-F1 骨架：Pinia + axios 基础封装。登录态挂 httpOnly Cookie（方案 A），
// 本 store 只持有公开用户信息。S2-F3 增 roles（/auth/me 出参，dashboard
// 双角色徽标与分区消费）。
export const useAuthStore = defineStore('auth', () => {
  const user = ref<AuthUser | null>(null)
  const roles = ref<string[]>([])

  async function fetchMe() {
    const me = await getMe()
    user.value = me.user
    roles.value = me.roles
  }

  async function login(username: string, password: string) {
    await loginApi(username, password)
    await fetchMe()
  }

  function reset() {
    user.value = null
    roles.value = []
  }

  return { user, roles, fetchMe, login, reset }
})
