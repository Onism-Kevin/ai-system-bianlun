import client from './client'
import type {
  NormalizedReport,
  ReflectionOut,
  ReflectionSavedOut,
  RevisionCreateBody,
  RevisionDetailOut,
  RevisionListItem,
  RevisionPostResponse,
  RevisionUpdateBody,
  ReviewReport,
  StoredReport,
  SubmissionResponse,
} from './types'

// ---- S2-F7 复盘页数据层（revisions S2-11 / reflection G2 / reports S2-10 / submissions S3-4）----
// 契约出处：api.md:36-37（reflection）、50-53（revisions）、47-49（reports）、65（submissions）。

// ---- revisions（S2-11，api.md:50-53）----

// GET /api/revisions?session_id= — 版本列表（含 diff_vs_prev，空列表 200 不 404）。
export function listRevisions(sessionId: number) {
  return client
    .get<RevisionListItem[]>('/revisions', { params: { session_id: sessionId } })
    .then((res) => res.data)
}

// POST /api/revisions — 新建观点版本（api.md:50：201 {id, version, status, diff:null}）。
// 初稿 version 自增（后端 SELECT MAX+INSERT）；status 默认 draft。
export function createRevision(body: RevisionCreateBody) {
  return client
    .post<RevisionPostResponse>('/revisions', body)
    .then((res) => res.data)
}

// PATCH /api/revisions/{id} — 更新内容/状态（api.md:51）。
// E-25：返回 diff_vs_prev 是"同 revision 修改前 vs 修改后"。
export function updateRevision(id: number, body: RevisionUpdateBody) {
  return client
    .patch<RevisionDetailOut>(`/revisions/${id}`, body)
    .then((res) => res.data)
}

// GET /api/revisions/{id} — 单条（api.md:53）。
// E-25：返回 diff_vs_prev 是"上一版 version vs 当前版"。
export function getRevision(id: number) {
  return client
    .get<RevisionDetailOut>(`/revisions/${id}`)
    .then((res) => res.data)
}

// ---- reflection（G2 裁定，api.md:36-37）----

// GET /api/sessions/{id}/reflection — 读取反思（api.md:37）。
// 未填写时 content=null（**不 404**，空反思非越权）。
export function getReflection(sessionId: number) {
  return client
    .get<ReflectionOut>(`/sessions/${sessionId}/reflection`)
    .then((res) => res.data)
}

// POST /api/sessions/{id}/reflection — 保存/更新反思（api.md:36：200 {updated_at}）。
// 单会话单文本，UPDATE 同一列（upsert 覆盖）。
export function saveReflection(sessionId: number, content: string) {
  return client
    .post<ReflectionSavedOut>(`/sessions/${sessionId}/reflection`, { content })
    .then((res) => res.data)
}

// ---- reports（S2-10，api.md:47-49 + errata E-24/E-27）----

// POST /api/sessions/{id}/reports — 生成报告（api.md:47）。
// ⚠️ 同步阻塞（中位 30.8s，errata E-28：无 report_progress/ready SSE），
// 调用方需自行展示骨架屏。返回 ReviewReport（E-24 修订版）。
export function createReport(sessionId: number) {
  return client
    .post<ReviewReport>(`/sessions/${sessionId}/reports`)
    .then((res) => res.data)
}

// GET /api/sessions/{id}/reports — 最新一份（api.md:48；无报告 404）。
// E-27：返回 StoredReport（无 sections[]，只有 summary_text）。
export function getLatestReport(sessionId: number) {
  return client
    .get<StoredReport>(`/sessions/${sessionId}/reports`)
    .then((res) => res.data)
}

// GET /api/reports/{id} — 按 id 返回（api.md:49；E-27 同上，无 sections[]）。
export function getReportById(reportId: number) {
  return client
    .get<StoredReport>(`/reports/${reportId}`)
    .then((res) => res.data)
}

/**
 * POST 返回的 ReviewReport → NormalizedReport（结构化路径，用 sections[]）。
 * 与 GET 的 summary_text 路径（markdown 渲染）是 S2-F7 的双渲染分支（设计 §8.3）。
 */
export function normalizePostReport(
  rr: ReviewReport,
): NormalizedReport {
  return {
    rubric_version: 'v1.0',
    scores: rr.scores,
    overall_score: rr.score,
    summary: rr.summary,
    sections: rr.sections,
    strengths: rr.strengths,
    weaknesses: rr.weaknesses,
    created_at: new Date().toISOString(),
  }
}

/** GET 返回的 StoredReport → NormalizedReport（markdown 路径，用 summary_text）。 */
export function normalizeStoredReport(row: StoredReport): NormalizedReport {
  return {
    rubric_version: row.rubric_version,
    scores: row.scores,
    overall_score: row.overall_score,
    summary_text: row.summary_text,
    created_at: row.created_at,
  }
}

// ---- submissions（S3-4 未实现，前端仅占位）----

// POST /api/tasks/{task_id}/submissions — 提交给课程任务（api.md:65）。
// ⚠️ 后端未实现（S3-4 任务）。前端 S2-F7 按钮禁用 + 提示"待 S3-4"，不调用。
export function submitToTask(taskId: number, sessionId: number) {
  return client
    .post<SubmissionResponse>(`/tasks/${taskId}/submissions`, { session_id: sessionId })
    .then((res) => res.data)
}
