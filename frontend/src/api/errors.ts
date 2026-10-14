import { AxiosError } from 'axios'

// api.md §3 错误分类 → 面向用户的中文提示（S2-F2 登录页消费；S2-F3 dashboard 扩展 403/410）。
// - 401 凭据错 → 「用户名或密码错误」（登录失败不区分用户不存在/密码错，
//   不泄露账号是否存在）；
// - 403 两类（§3:90）：已知资源+归属不符（如教师改学生会话）、加入码错误
//   （E-12 对称化，detail 只说"加入码无效"）→ 优先透传后端 detail（本就是用户
//   文案），无 detail 时兜底「没有权限执行此操作」；
// - 410 任务已过 deadline（api.md:64，S3-3 验收）；
// - 409 用户名重名（register，api.md:25）→ 「用户名已被占用」；
// - 422 校验失败（api.md:91：pydantic + E-2 应用层校验）→ 逐字段明细
//   （FastAPI detail 数组：loc 末位=字段名，msg=原因）；
// - 5xx/网络异常兜底文案。
export function describeApiError(err: unknown): string {
  if (!(err instanceof AxiosError)) {
    return '网络异常，请检查连接后重试'
  }
  const status = err.response?.status
  const data: unknown = err.response?.data
  if (status === 401) return '用户名或密码错误'
  if (status === 403) return describe403(data)
  if (status === 410) return '任务已过截止时间，无法加入'
  if (status === 404) return describe404(data)
  if (status === 409) return '用户名已被占用'
  if (status === 422) return describeValidation(data)
  if (status !== undefined && status >= 500) return '服务器繁忙，请稍后再试'
  return '网络异常，请检查连接后重试'
}

function describe403(data: unknown): string {
  const detail = (data as { detail?: unknown } | undefined)?.detail
  if (typeof detail === 'string' && detail) return detail
  return '没有权限执行此操作'
}

function describe404(data: unknown): string {
  const detail = (data as { detail?: unknown } | undefined)?.detail
  if (typeof detail === 'string' && detail) return detail
  return '资源不存在或无权访问'
}

/** 401 判定：登录态失效，视图层据此跳 /login（不展示文案）。 */
export function isUnauthorized(err: unknown): boolean {
  return err instanceof AxiosError && err.response?.status === 401
}

function describeValidation(data: unknown): string {
  const detail = (data as { detail?: unknown } | undefined)?.detail
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        const record = item as { loc?: unknown[]; msg?: unknown }
        const field = Array.isArray(record.loc)
          ? String(record.loc[record.loc.length - 1])
          : undefined
        const msg = typeof record.msg === 'string' ? record.msg : undefined
        if (field && msg && field !== 'body') return `${field}: ${msg}`
        return msg ?? undefined
      })
      .filter((part): part is string => Boolean(part))
    if (parts.length > 0) return `输入有误：${parts.join('；')}`
  }
  if (typeof detail === 'string') return detail
  return '输入内容校验失败，请检查后重试'
}
