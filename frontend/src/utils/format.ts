/**
 * S3-F3：前端公共格式化工具。
 * 从 CourseTasksView 抽出，供 TaskDetailView 等复用（抽公共函数，不复制粘贴）。
 */

/** 截止时间格式化：ISO → "YYYY-MM-DD HH:mm"；空 → "—"。 */
export function formatDeadline(d: string | null): string {
  if (!d) return '—'
  return d.replace('T', ' ').slice(0, 16)
}
