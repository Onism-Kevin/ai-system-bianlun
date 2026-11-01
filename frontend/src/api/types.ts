// 与 backend/app/schemas/auth.py 逐字对应（S2-1 出参形状，api.md:25-27）
export interface AuthUser {
  id: number
  username: string
  display_name: string | null
}

export interface RegisterResponse {
  id: number
  username: string
  roles: string[]
}

export interface LoginResponse {
  user: AuthUser
}

export interface MeResponse {
  user: AuthUser
  roles: string[]
}

// 与 backend/app/schemas/session.py 对应（S2-3，api.md:28）
export interface SessionCreated {
  id: number
  status: string
}

export interface SessionCreateBody {
  topic: string
  visibility?: 'private' | 'task'
  task_id?: number | null
}

// 与 backend/app/schemas/session.py SessionOut 对应（S2-3，api.md:29/30 出参）
export interface SessionOut {
  id: number
  topic: string
  visibility: string
  task_id: number | null
  status: string
  created_at: string
  updated_at: string
}

// 与 backend/app/schemas/session.py SessionStatusOut 对应（S2-6 控制端点，api.md:31-34）。
// 统一 {id, status}：pause/resume 返回 {id, status}（id 冗余但无害），
// restart/quick 返回 {id, status}。status ∈ waiting/generating/paused/finished/failed。
export interface SessionStatusOut {
  id: number
  status: string
}

// 与 backend/app/schemas/message.py 对应（S2-4 落库，api.md:35/38）
export interface MessageCreated {
  seq: number
  created_at: string
}

export interface MessageOut {
  seq: number
  role: 'user' | 'assistant' | 'system'
  agent_role: 'pro' | 'con' | 'judge' | 'coach' | null
  content: string
  status: 'streaming' | 'complete' | 'paused_truncated'
  created_at: string
}

export interface MessageListOut {
  messages: MessageOut[]
  next_seq: number
}

// 与 backend/app/schemas/history.py HistoryItem 对应（S2-12，api.md:40）。
// 列表是 owner 视角 5 字段（无 visibility/task_id）；后端按 updated_at DESC 排序。
export interface HistoryItem {
  id: number
  topic: string
  status: string
  created_at: string
  updated_at: string
}

// 与 backend/app/schemas/history.py HistoryDetailOut 对应（S2-12，api.md:41）。
// session = SessionOut（平铺七字段）；messages = list[MessageOut]（按 seq 升序，
// 含 streaming 在途消息——历史详情是完整重建，不过滤）。
export interface HistoryDetailOut {
  session: SessionOut
  messages: MessageOut[]
}

// 与 docs/contracts/sse_events.md §4 事件总表逐字对应（S2-F5 useSSE 消费）。
// 注意：只有 speech_* 帧服务端写 id: 行（=seq），EventSource 原生把 id 透传到
// event.lastEventId；帧内 seq 字段冗余但前端按帧内 seq upsert（§7.4 幂等）。
export interface SseSpeechStartFrame {
  seq: number
  agent_role: 'pro' | 'con' | 'judge' | 'coach'
}

export interface SseSpeechDeltaFrame {
  seq: number
  delta: string
}

export interface SseSpeechEndFrame {
  seq: number
  status: 'complete' | 'paused_truncated'
}

export interface SseSpeechSnapshotFrame {
  seq: number
  agent_role: 'pro' | 'con' | 'judge' | 'coach'
  content: string
  status: 'streaming' | 'complete' | 'paused_truncated'
}

export interface SseErrorFrame {
  code: 'model_connection' | 'model_timeout' | 'model_server' | 'structured_validation' | 'internal' | string
  message: string
  retryable: boolean
  fatal: boolean
}

export interface SseDoneFrame {
  reason: 'finished' | 'failed' | string
}

// 与 backend/app/api/health.py 对应（S2-13，api.md:74）。
// 降级也 200（状态在 body），匿名可读；前端只读 body 字段，不按状态码猜语义。
// S2-F9 徽标/横幅消费。
export interface HealthStatus {
  mysql: 'ok' | 'down'
  model_gateway: 'ok' | 'degraded' | 'down'
}

// ---- S2-F7：revisions（S2-11，api.md:50-53）+ reflection（G2，api.md:36-37）+ reports（S2-10）----

export type RevisionStatus = 'draft' | 'final'

// 与 backend/app/schemas/revision.py RevisionOut 对应（api.md:50/53）。
export interface RevisionOut {
  id: number
  version: number
  status: RevisionStatus | string
  content: string
  created_at: string
}

// POST /api/revisions 出参（api.md:50）：{id, version, status, diff:null}。
// diff 在新版本总是 null（无上一版可 diff）。
export interface RevisionPostResponse {
  id: number
  version: number
  status: RevisionStatus | string
  diff: string | null
}

// GET /api/revisions 列表项（api.md:52）：含 diff_vs_prev（版本间 diff，首版 null）。
export interface RevisionListItem extends RevisionOut {
  diff_vs_prev: string | null
}

// PATCH /api/revisions/{id} 与 GET /api/revisions/{id} 出参（api.md:51/53）。
// E-25：PATCH 的 diff_vs_prev 是"同 revision 修改前 vs 修改后"；
// GET 的 diff_vs_prev 是"上一版 version vs 当前版"。
export interface RevisionDetailOut {
  revision: RevisionOut
  diff_vs_prev: string | null
}

export interface RevisionCreateBody {
  session_id: number
  content: string
  status?: RevisionStatus
}

export interface RevisionUpdateBody {
  content?: string
  status?: RevisionStatus
}

// 与 backend/app/schemas/session.py ReflectionOut/ReflectionSavedOut 对应
// （G2 裁定，api.md:36-37）。
export interface ReflectionOut {
  content: string | null
  updated_at: string
}

export interface ReflectionSavedOut {
  updated_at: string
}

// ---- reports（S2-10，api.md:47-49 + errata E-24/E-27）----

// 与 backend/app/schemas/stage_outputs.py ReportSection 对应（POST 专属，E-27）。
export interface ReportSection {
  heading: string
  body: string
  dimension_id: string
}

// 与 ReviewReport 对应（POST /api/sessions/{id}/reports 返回，api.md:47）。
// E-24：scores 是英文 id 键的四维度分数；score 是端点计算的加权总分。
export interface ReviewReport {
  summary: string
  strengths: string[]
  weaknesses: string[]
  sections: ReportSection[]
  scores: Record<string, number>
  score: number
}

// 与 reports 表出参对应（GET /api/sessions/{id}/reports 与 GET /api/reports/{id}，
// api.md:48/49 + errata E-27：**不返回 sections[]**，只有拼接后的 summary_text）。
export interface StoredReport {
  id: number
  session_id: number
  rubric_version: string
  scores: Record<string, number>
  overall_score: number
  summary_text: string
  created_at: string
}

/**
 * 归一化报告对象（S2-F7 双渲染路径的统一入口）。
 *
 * ⚠️ summary 与 summary_text **不是同一个东西**，勿混用：
 * - summary：POST /api/sessions/{id}/reports 返回（api.md:47）——模型生成的
 *   总结，一两句话（ReviewReport.summary）。
 * - summary_text：GET /api/sessions/{id}/reports / GET /api/reports/{id} 返回
 *   （api.md:48/49 + errata E-27）——sections + strengths + weaknesses 的拼接
 *   全文（markdown）。
 * 渲染时：有 sections 走结构化渲染；只有 summary_text 走 markdown 渲染。
 */
export interface NormalizedReport {
  rubric_version: string
  scores: Record<string, number>
  overall_score: number
  /** POST 返回：模型生成的总结（一两句话） */
  summary?: string
  /** GET 返回：sections + strengths + weaknesses 的拼接全文（markdown） */
  summary_text?: string
  sections?: ReportSection[]
  strengths?: string[]
  weaknesses?: string[]
  created_at: string
}

// 与 backend/app/schemas/task.py 提交出参对应（api.md:65，S3-4 未实现）。
export interface SubmissionResponse {
  id: number
  session_id: number
  submitted_at: string
  replaced: boolean
}
