import { AxiosError, type AxiosResponse } from 'axios'

// S2-F3 dashboard 数据层。
// - fetchStudentCourses / joinCourse：S3-2 已交付，接真实调用（api/courses.ts）；
// - fetchTeacherCourses：教师课程改由 TeacherDashboardView 接真实数据，移除；
// - joinTask：S3-3 已交付，但 api/tasks.ts 属 commit C，本文件暂保留假数据；
// - demoError403/410：S2-F3 教学演示，保留（用户 2026-11-08 确认不动）；
// - history 走 api/history.ts（S2-12 真实）。
//
// 错误演示的关键设计：模拟错误构造**真 AxiosError**（带 status + response.data.detail），
// 与真实后端错误走同一条 describeApiError 消费路径——错误码演示不是"另一套分支"。

const DELAY_MS = 300

import { joinCourse as joinCourseApi, listCourses } from './courses'
import type { CourseOut } from './types'

export type CourseItem = CourseOut

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function fakeError(status: number, detail: string): AxiosError {
  const response = { status, data: { detail } } as AxiosResponse
  return new AxiosError('模拟错误', AxiosError.ERR_BAD_REQUEST, undefined, undefined, response)
}

// ---------- 我的课程（学生视角：GET /api/courses 真实调用）----------

export function fetchStudentCourses(): Promise<CourseItem[]> {
  return listCourses()
}

// ---------- 加入课程（POST /api/courses/join 真实调用）----------

export function joinCourse(inviteCode: string): Promise<{ course_id: number }> {
  return joinCourseApi(inviteCode)
}

// ---------- 加入任务（POST /api/tasks/{id}/join 的假数据）----------
// api/tasks.ts 属 commit C；本函数保留假数据直至该 commit。

const VALID_TASK_CODE = 'XK7M2QP'

export function joinTask(
  joinCode: string,
  expired: boolean,
): Promise<{ course_id: number; task_id: number }> {
  return delay(DELAY_MS).then(() => {
    if (expired) {
      throw fakeError(410, '任务已过截止时间')
    }
    if (joinCode.trim() !== VALID_TASK_CODE) {
      throw fakeError(403, '加入码无效')
    }
    return { course_id: 101, task_id: 201 }
  })
}

// ---------- 错误码演示：经同一条 describeApiError 路径 ----------

export function demoError403(): Promise<never> {
  return delay(DELAY_MS).then(() => {
    throw fakeError(403, '加入码无效')
  })
}

export function demoError410(): Promise<never> {
  return delay(DELAY_MS).then(() => {
    throw fakeError(410, '任务已过截止时间')
  })
}
