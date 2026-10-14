import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getMe, login as loginApi } from '../api/auth'
import type { AuthUser } from '../api/types'

// S2-F1 骨架：Pinia + axios 基础封装。登录态挂 httpOnly Cookie（方案 A），
// 本 store 只持有公开用户信息；路由守卫/登出等业务逻辑后续任务补。
export const useAuthStore = defineStore('auth', () => {
  const user = ref<AuthUser | null>(null)

  async function fetchMe() {
    user.value = (await getMe()).user
  }

  async function login(username: string, password: string) {
    await loginApi(username, password)
    await fetchMe()
  }

  function reset() {
    user.value = null
  }

  return { user, fetchMe, login, reset }
})
