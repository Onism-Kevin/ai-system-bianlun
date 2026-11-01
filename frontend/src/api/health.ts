import client from './client'
import type { HealthStatus } from './types'

// GET /api/health — api.md:74：200 {mysql, model_gateway}。
// 降级也 200（状态在 body），匿名可读；前端只读 body 字段，不按状态码猜语义。
// S2-F9 健康徽标/横幅消费。health 是探针，调用方（useHealth）自行兜底，
// 不把探针失败抛给业务层。
export function getHealth() {
  return client.get<HealthStatus>('/health').then((res) => res.data)
}
