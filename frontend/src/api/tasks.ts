import client from './client'
import type {
  TaskCreateBody,
  TaskJoinBody,
  TaskJoinResponse,
  TaskOut,
  TaskUpdateBody,
} from './types'

// S3-F1 commit C：tasks 真实调用层（api.md:60-64）。
// - listCourseTasks：GET /api/courses/:id/tasks（教师/学生视角）
// - createTask：POST /api/courses/:id/tasks（课程教师）
// - getTask / patchTask：GET / PATCH /api/tasks/:id
// - joinTask：POST /api/tasks/:id/join（学生）

export function listCourseTasks(courseId: number): Promise<TaskOut[]> {
  return client.get<TaskOut[]>(`/courses/${courseId}/tasks`).then((res) => res.data)
}

export function getTask(taskId: number): Promise<TaskOut> {
  return client.get<TaskOut>(`/tasks/${taskId}`).then((res) => res.data)
}

export function createTask(courseId: number, body: TaskCreateBody): Promise<TaskOut> {
  return client
    .post<TaskOut>(`/courses/${courseId}/tasks`, body)
    .then((res) => res.data)
}

export function patchTask(taskId: number, body: TaskUpdateBody): Promise<TaskOut> {
  return client.patch<TaskOut>(`/tasks/${taskId}`, body).then((res) => res.data)
}

export function joinTask(taskId: number, joinCode: string): Promise<TaskJoinResponse> {
  return client
    .post<TaskJoinResponse>(`/tasks/${taskId}/join`, { join_code: joinCode } as TaskJoinBody)
    .then((res) => res.data)
}
