import axios from 'axios'

// 鉴权方案 A（Cookie）：REST/SSE 同一凭据（permissions §6.3、sse_events §9）。
// withCredentials=true：同源部署（vite proxy / nginx 反代）下零配置即可
// 携带 httpOnly Cookie；跨源联调时同样必须开启，并依赖后端 CORS
// allow_credentials=True（S2-1 已在 main.py 精确列举 allow_origins）。
const client = axios.create({
  baseURL: '/api',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

export default client
