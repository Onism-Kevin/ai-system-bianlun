import client from './client'
import type { SessionCreateBody, SessionCreated, SessionOut } from './types'

// 与 backend/app/api/sessions.py POST 对应（S2-3，api.md:28：201 {id, status}）。
// 创建后跳训练页（S2-F4 起由 TrainingView 消费 id）；登录态走 Cookie 自动携带。
export function createSession(body: SessionCreateBody) {
  return client.post<SessionCreated>('/sessions', body).then((res) => res.data)
}

// 与 backend/app/api/sessions.py GET 对应（S2-3，api.md:29：200 平铺七字段）。
// 训练页进入时拉取会话信息；404=不存在或无权访问（存在性隐藏）。
export function getSession(id: number) {
  return client.get<SessionOut>(`/sessions/${id}`).then((res) => res.data)
}
