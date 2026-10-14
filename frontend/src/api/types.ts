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
