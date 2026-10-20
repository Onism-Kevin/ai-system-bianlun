import client from './client'
import type {
  MessageCreated,
  MessageListOut,
  SessionCreateBody,
  SessionCreated,
  SessionOut,
} from './types'

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

// 与 backend/app/api/sessions.py POST /{id}/messages 对应（S2-4，api.md:35：
// 201 {seq, created_at}）。同步落库 role=user → 异步触发 waiting→generating
// → SSE 推送下一轮 AI 生成。用户消息由前端本地渲染，不走 SSE 回显（sse §4 补注）。
export function submitMessage(sessionId: number, content: string) {
  return client
    .post<MessageCreated>(`/sessions/${sessionId}/messages`, { content })
    .then((res) => res.data)
}

// 与 backend/app/api/sessions.py GET /{id}/messages 对应（S2-4，api.md:38：
// 200 {messages, next_seq}）。S2-F5 进页面先拉历史记 maxSeq 再 SSE 建流
// （sse §7.2 消缝），limit 默认 200 与后端 sessions.py:557 默认值一致。
export function listMessages(sessionId: number, afterSeq = 0, limit = 200) {
  return client
    .get<MessageListOut>(`/sessions/${sessionId}/messages`, {
      params: { after_seq: afterSeq, limit },
    })
    .then((res) => res.data)
}
