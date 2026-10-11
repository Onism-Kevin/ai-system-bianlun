"""思辨工坊 backend 应用入口（S0-2 骨架）。

当前仅提供 /api/health 骨架与应用组装；业务路由随 S2 逐步挂载。
"""
from fastapi import FastAPI

app = FastAPI(title="思辨工坊", version="0.0.1")


@app.get("/api/health")
def health() -> dict:
    """存活探针。S2-13 会扩展为探测模型网关 + MySQL。"""
    return {"status": "ok"}
