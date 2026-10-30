"""思辨工坊 backend 应用入口（S0-2 骨架；S2-1 挂载 auth 路由）。

- 业务路由随 S2 逐步挂载（S2-1：/api/auth/register|login|me；
  S2-3：/api/sessions 创建/详情/修改，状态转移端点 S2-6 补齐；
  S2-4：/api/sessions/{id}/messages + /events SSE）；
- CORS 允许 Vite dev 源 http://localhost:5173 且带凭据——Cookie 鉴权的
  前提（permissions.md §6.3：allow_origins 禁 *，必须 allow_credentials=True；
  CSRF 由 SameSite=Lax + 写操作 Content-Type: application/json 缓解）。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analyze, auth, coach_turn, events, explore, reports, sessions

app = FastAPI(title="思辨工坊", version="0.0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # dev：Vite 源；禁 *（§6.3）
    allow_credentials=True,  # Cookie 凭据必需（§6.3）
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(events.router)
app.include_router(explore.router)
app.include_router(analyze.router)
app.include_router(coach_turn.router)
app.include_router(reports.router)


@app.get("/api/health")
def health() -> dict:
    """存活探针。S2-13 会扩展为探测模型网关 + MySQL。"""
    return {"status": "ok"}
