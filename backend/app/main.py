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
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, IntegrityError

from app.api import (
    analyze,
    auth,
    coach_turn,
    courses,
    events,
    explore,
    feedback,
    health,
    history,
    reports,
    revisions,
    sessions,
    submissions,
    tasks,
    teacher,
    user_roles,
)
from app.services.error_map import classify_db_error

app = FastAPI(title="思辨工坊", version="0.0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # dev：Vite 源；禁 *（§6.3）
    allow_credentials=True,  # Cookie 凭据必需（§6.3）
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(user_roles.router)
app.include_router(courses.router)
app.include_router(teacher.router)
app.include_router(tasks.router)
app.include_router(submissions.router)
app.include_router(feedback.router)
app.include_router(sessions.router)
app.include_router(events.router)
app.include_router(explore.router)
app.include_router(analyze.router)
app.include_router(coach_turn.router)
app.include_router(reports.router)
app.include_router(revisions.router)
app.include_router(history.router)
app.include_router(health.router)


# ---- 数据库异常全局处理（errata E-6）----
# DataError(1265) → 422；IntegrityError(1062) → 409；IntegrityError(1451/1452) → 409


@app.exception_handler(DataError)
async def data_error_handler(request, exc):
    status_code, detail = classify_db_error(exc)
    return JSONResponse(status_code=status_code, content={"detail": detail})


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request, exc):
    status_code, detail = classify_db_error(exc)
    return JSONResponse(status_code=status_code, content={"detail": detail})
