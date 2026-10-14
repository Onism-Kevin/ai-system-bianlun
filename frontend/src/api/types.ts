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
