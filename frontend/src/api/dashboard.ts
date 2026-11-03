import { AxiosError, type AxiosResponse } from 'axios'

// S2-F3 dashboard 假数据层：courses / join 的端点属 S3-2 / S3-3，
// 本任务用假数据把 UI 走通（端点到位后替换为真调用即可，函数签名不变）。
// history 已接真实 GET /api/history（S2-12 已交付，#7 T-6 修复），见 api/history.ts。
//
// 错误演示的关键设计：模拟错误构造**真 AxiosError**（带 status + response.data.detail），
// 与真实后端错误走同一条 describeApiError 消费路径——错误码演示不是"另一套分支"。

const DELAY_MS = 300

export interface CourseItem {
  id: number
  name: string
  term: string | null
  invite_code?: string
}

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function fakeError(status: number, detail: string): AxiosError {
  const response = { status, data: { detail } } as AxiosResponse
  return new AxiosError('模拟错误', AxiosError.ERR_BAD_REQUEST, undefined, undefined, response)
}

// ---------- 我的课程（S3-2 GET /api/courses 的假数据） ----------

const FAKE_STUDENT_COURSES: CourseItem[] = [
  { id: 101, name: '2026 秋·论证与探究', term: '2026-秋' },
]

const FAKE_TEACHER_COURSES: CourseItem[] = [
  { id: 101, name: '2026 秋·论证与探究', term: '2026-秋', invite_code: 'DEMO01' },
]

export function fetchStudentCourses(): Promise<CourseItem[]> {
  return delay(DELAY_MS).then(() => FAKE_STUDENT_COURSES)
}

export function fetchTeacherCourses(): Promise<CourseItem[]> {
  return delay(DELAY_MS).then(() => FAKE_TEACHER_COURSES)
}

// ---------- 加入课程（S3-2 POST /api/courses/join 的假数据） ----------

const VALID_COURSE_CODE = 'DEMO01'

export function joinCourse(inviteCode: string): Promise<{ course_id: number }> {
  return delay(DELAY_MS).then(() => {
    if (inviteCode.trim() !== VALID_COURSE_CODE) {
      throw fakeError(403, '加入码无效')
    }
    return { course_id: 101 }
  })
}

// ---------- 加入任务（S3-3 POST /api/tasks/{id}/join 的假数据） ----------

const VALID_TASK_CODE = 'XK7M2QP'

export function joinTask(joinCode: string, expired: boolean): Promise<{ course_id: number; task_id: number }> {
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
