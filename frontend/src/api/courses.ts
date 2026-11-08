import client from './client'
import type {
  CourseCreateBody,
  CourseJoinBody,
  CourseJoinResponse,
  CourseOut,
} from './types'

// S3-F1：courses 真实调用层（api.md:54-59）。
// 只接 F1 需要的四个：listCourses / getCourse / createCourse / joinCourse。
// listCourseTasks / patchCourse / getCourseMembers 后续任务按需补。

export function listCourses(): Promise<CourseOut[]> {
  return client.get<CourseOut[]>('/courses').then((res) => res.data)
}

export function getCourse(courseId: number): Promise<CourseOut> {
  return client.get<CourseOut>(`/courses/${courseId}`).then((res) => res.data)
}

export function createCourse(body: CourseCreateBody): Promise<CourseOut> {
  return client.post<CourseOut>('/courses', body).then((res) => res.data)
}

export function joinCourse(inviteCode: string): Promise<CourseJoinResponse> {
  return client
    .post<CourseJoinResponse>('/courses/join', { invite_code: inviteCode } as CourseJoinBody)
    .then((res) => res.data)
}
