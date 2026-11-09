import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { AxiosError } from 'axios'
import { useAuthStore } from '../stores/auth'
import { isUnauthorized } from '../api/errors'

// S3-F3：从 CourseTasksView（S3-F2 commit C）抽出的错误处理模式，
// 供 TaskDetailView / CourseTasksView 共用——抽公共函数，不复制粘贴。

export type LoadError = 'unauthorized' | 'forbidden' | 'notFound' | 'network'

export interface LoadErrorLabels {
  forbiddenTitle?: string
  forbiddenDesc?: string
  notFoundTitle?: string
  notFoundDesc?: string
}

export function useLoadError(labels: LoadErrorLabels = {}) {
  const auth = useAuthStore()
  const route = useRoute()
  const router = useRouter()

  const loadError = ref<LoadError | null>(null)

  /** 401 → 清本地登录态 + 跳登录（带 redirect）。 */
  function goLogin() {
    auth.reset()
    router.push({ path: '/login', query: { redirect: route.fullPath } })
  }

  /**
   * 把加载/提交错误映射到 loadError 分支。
   * 401 → goLogin；403 → forbidden；404 → notFound；其余 → network + toast。
   * 返回 true 表示已处理（调用方应 return）。
   */
  function handleLoadError(err: unknown): boolean {
    if (isUnauthorized(err)) {
      goLogin()
      return true
    }
    if (err instanceof AxiosError) {
      const status = err.response?.status
      if (status === 403) {
        loadError.value = 'forbidden'
        return true
      }
      if (status === 404) {
        loadError.value = 'notFound'
        return true
      }
    }
    loadError.value = 'network'
    ElMessage.error('加载失败，请稍后重试')
    return true
  }

  const errorTitle = computed(() => {
    if (loadError.value === 'forbidden') return labels.forbiddenTitle ?? '无权访问'
    if (loadError.value === 'notFound') return labels.notFoundTitle ?? '资源不存在'
    return '加载失败'
  })

  const errorDesc = computed(() => {
    if (loadError.value === 'forbidden') {
      return labels.forbiddenDesc ?? '你没有该资源的权限'
    }
    if (loadError.value === 'notFound') {
      return labels.notFoundDesc ?? '资源不存在或已删除'
    }
    return '请检查网络连接后重试'
  })

  return { loadError, goLogin, handleLoadError, errorTitle, errorDesc }
}
