"""S2-1 API 测试夹具：复用 models 测试的 sfb_test + alembic 建表底座。

- engine / session fixture 从 tests.models.conftest 导入复用（S1-5 起
  migration 是唯一建表入口，避免两处维护同一套建表/清库逻辑）；
- 追加 client fixture：TestClient + get_db 依赖覆盖为测试 session；
  同一 TestClient 实例跨请求共享 cookie jar（E-10 三连验收的载体：
  登录响应 Set-Cookie 自动带回 me 请求）。
"""
from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"  # 必须在导入 app 包之前写入

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import get_db  # noqa: E402
from app.main import app  # noqa: E402

# 复用 models 测试底座 fixture（sfb_test + alembic upgrade head + 每用例 TRUNCATE）
from tests.models.conftest import engine, session  # noqa: E402,F401


@pytest.fixture()
def client(session):
    """TestClient：get_db 覆盖为测试 session；跨请求共享 cookie（三连验收）。"""

    def _override_get_db():
        yield session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
