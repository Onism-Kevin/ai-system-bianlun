"""S2-13：健康探针（api.md:74）。

GET /api/health → 200 {mysql:"ok"|"down", model_gateway:"ok"|"degraded"|"down"}
降级也 200（状态在 body），匿名可读，前端徽标 S2-F9。

探测逻辑：
- MySQL：SELECT 1 → ok/down
- 模型网关：GET {base}/models + Bearer → ok（200）/degraded（>3s 超时）/down（连接拒绝/非200）
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter
from sqlalchemy import text

router = APIRouter(prefix="/api", tags=["health"])


def _probe_mysql() -> str:
    """探测 MySQL：SELECT 1 → ok/down。"""
    try:
        from app.core.database import get_engine

        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "down"


def _probe_gateway() -> str:
    """探测模型网关：GET {base}/models → ok/degraded/down。

    状态判定：
    - 200 → ok
    - >3s 超时 → degraded
    - 连接拒绝/非200 → down
    - 401（key 无效）也归为 down——MVP 不区分"网关不可达"和
      "key 配置错误"，S5 若需要可加"config_error"状态。
    """
    try:
        from app.core.config import get_settings

        settings = get_settings()
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(
                f"{settings.model_base_url}/models",
                headers={
                    "Authorization": f"Bearer {settings.model_api_key.get_secret_value()}"
                },
            )
            return "ok" if resp.status_code == 200 else "down"
    except httpx.ConnectError:
        return "down"
    except httpx.ReadTimeout:
        return "degraded"
    except httpx.HTTPError:
        return "down"


@router.get("/health")
def health() -> dict:
    """健康探针：探测 MySQL + 模型网关（api.md:74）。

    降级也 200，状态在 body；匿名可读。
    """
    return {"mysql": _probe_mysql(), "model_gateway": _probe_gateway()}
