import client from './client'
import type { HistoryDetailOut, HistoryItem } from './types'

// ---- S2-F8 训练历史页（S2-12 历史端点，api.md:40-41）----

// GET /api/history — api.md:40：200 [{id, topic, status, created_at, updated_at}]。
// owner 视角列表，后端按 updated_at DESC 排序；登录态走 Cookie 自动携带（方案 A）。
export function listHistory() {
  return client.get<HistoryItem[]>('/history').then((res) => res.data)
}

// GET /api/history/{session_id} — api.md:41：200 {session, messages:[按 seq 升序]}。
// 详情完整重建消息流（含 streaming 在途消息，非"回放终态"）；404=不存在或
// private 越权（存在性隐藏）。
export function getHistoryDetail(sessionId: number) {
  return client
    .get<HistoryDetailOut>(`/history/${sessionId}`)
    .then((res) => res.data)
}
