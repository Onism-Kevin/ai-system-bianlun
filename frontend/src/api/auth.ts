import client from './client'
import type { LoginResponse, MeResponse, RegisterResponse } from './types'

// 与 backend/app/api/auth.py 三端点一一对应（api.md:25-27）；
// 登录态挂 httpOnly Cookie（方案 A），本层不触碰 token。
export function register(username: string, password: string) {
  return client
    .post<RegisterResponse>('/auth/register', { username, password })
    .then((res) => res.data)
}

export function login(username: string, password: string) {
  return client
    .post<LoginResponse>('/auth/login', { username, password })
    .then((res) => res.data)
}

export function getMe() {
  return client.get<MeResponse>('/auth/me').then((res) => res.data)
}
