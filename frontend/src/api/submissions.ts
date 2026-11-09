import client from './client'
import type { CourseSummaryOut, SubmissionListItem, SubmissionOut } from './types'

// S3-F3：submissions / summary 真实调用层（api.md:66-70）。
// 后端已交付（S3-4 submissions、S3-5 summary），本层纯前端封装。

/** 教师列表：GET /api/tasks/:id/submissions → [{student_id, session_id, submitted_at}] */
export function listSubmissions(taskId: number): Promise<SubmissionListItem[]> {
  return client
    .get<SubmissionListItem[]>(`/tasks/${taskId}/submissions`)
    .then((res) => res.data)
}

/** 本人提交：GET /api/tasks/:id/submissions/me → {submission}；未提交 → 404 */
export function getMySubmission(taskId: number): Promise<SubmissionOut> {
  return client
    .get<SubmissionOut>(`/tasks/${taskId}/submissions/me`)
    .then((res) => res.data)
}

/** 课程汇总：GET /api/courses/:id/summary → {submitted_count, total_students, top_pending_verification} */
export function getCourseSummary(courseId: number): Promise<CourseSummaryOut> {
  return client
    .get<CourseSummaryOut>(`/courses/${courseId}/summary`)
    .then((res) => res.data)
}
