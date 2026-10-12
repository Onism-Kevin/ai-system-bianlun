"""S1-2 模型测试夹具：固定连 sfb_test（APP_ENV=test），建表→测→拆表。

- 每个测试模块开始前 drop_all+create_all，结束后 drop_all，
  sfb_test 保持空库状态交给 S1-5（Alembic）接管；
- APP_ENV 必须在首次 get_settings() 之前写入进程环境。
"""
from __future__ import annotations

import os

import pytest

os.environ["APP_ENV"] = "test"

from sqlalchemy import create_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import reset_factory  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture(scope="module")
def engine():
    """模块级 engine：直接指向 sfb_test（绕过单例，隔离于应用运行时）。"""
    get_settings.cache_clear()
    reset_factory()
    url = get_settings().sqlalchemy_url()
    assert url.database == "sfb_test", f"测试必须连 sfb_test，实际 {url.database}"
    eng = create_engine(url, pool_pre_ping=True, future=True)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()
    reset_factory()


@pytest.fixture()
def session(engine):
    """函数级 Session：每用例前重建四表（防上一用例已提交数据残留撞唯一键），
    结束后 drop_all，库保持空库交给 S1-5。"""
    from sqlalchemy.orm import sessionmaker

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    sess = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield sess
    finally:
        sess.close()
