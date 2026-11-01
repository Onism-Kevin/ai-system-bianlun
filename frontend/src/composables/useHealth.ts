import { computed, onScopeDispose, ref } from 'vue'
import { getHealth } from '../api/health'
import type { HealthStatus } from '../api/types'

// S2-F9：模型网关健康状态（模块级单例）。
// 三个视图共享同一份状态与同一条轮询，避免各视图各拉一次 /api/health。
//
// 契约：GET /api/health 降级也 200（api.md:74），状态在 body；
// 前端不按 HTTP 状态码判断健康，只读 model_gateway 字段。
const HEALTH_POLL_MS = 15000

const status = ref<HealthStatus | null>(null)
const loading = ref(false)
/** 最近一次健康检查是否失败（后端不可达/网络断）——保留上一次 status，不置空。 */
const unreachable = ref(false)

export type GatewayState = 'ok' | 'degraded' | 'down' | 'unknown'

/** 模型网关状态（尚未拉到时 unknown）。 */
export const gatewayState = computed<GatewayState>(() => {
  const g = status.value?.model_gateway
  if (g === 'ok' || g === 'degraded' || g === 'down') return g
  return 'unknown'
})

/** 是否显示"模型服务告警"横幅：down / degraded。 */
export const gatewayAlert = computed(
  () => gatewayState.value === 'down' || gatewayState.value === 'degraded',
)

/** 页脚徽标文案（MySQL + 网关）。 */
export const healthBadge = computed(() => {
  if (unreachable.value && !status.value) {
    return { mysql: '不可达', gateway: '不可达', gatewayState: 'unknown' as GatewayState }
  }
  return {
    mysql: status.value?.mysql ?? '未知',
    gateway: status.value?.model_gateway ?? '未知',
    gatewayState: gatewayState.value,
  }
})

let pollTimer: ReturnType<typeof setInterval> | null = null
let started = false

function onOnline() {
  void reload()
}

async function reload() {
  loading.value = true
  try {
    status.value = await getHealth()
    unreachable.value = false
  } catch {
    // health 匿名可读；失败=后端不可达（或断网）。保留上一次 status，
    // 仅标记 unreachable——让徽标显示"不可达"而非"未知"。
    unreachable.value = true
  } finally {
    loading.value = false
  }
}

function start() {
  if (started) return
  started = true
  void reload()
  pollTimer = setInterval(() => {
    void reload()
  }, HEALTH_POLL_MS)
  window.addEventListener('online', onOnline)
}

function stop() {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  window.removeEventListener('online', onOnline)
  started = false
}

export function useHealth() {
  // 组件作用域卸载时停掉轮询；单例状态保留（下次挂载继续用）。
  onScopeDispose(stop)
  return { status, loading, unreachable, gatewayState, gatewayAlert, healthBadge, reload, start }
}
