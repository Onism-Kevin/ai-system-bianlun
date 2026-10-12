"""S1-1：SQLAlchemy engine / session 工厂。

- engine 与 sessionmaker 进程内懒加载单例（首次使用时按 Settings 创建）；
- pool_pre_ping=True：拿连接前先探活，避免 MySQL wait_timeout 断连导致的
  "server has gone away"；
- get_db() 是 FastAPI 依赖：请求结束自动 close，异常时 rollback。
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker | None = None


def get_engine() -> Engine:
    """懒加载单例 engine（连接串按当前 APP_ENV 选 schema）。"""
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_settings().sqlalchemy_url(),
            pool_pre_ping=True,
            future=True,
        )
    return _engine


def get_session_factory() -> sessionmaker:
    """懒加载单例 sessionmaker。"""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), autoflush=False, expire_on_commit=False
        )
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每请求一个 Session，结束即关，异常回滚。"""
    session = get_session_factory()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping(session: Session) -> str:
    """连通性探针：SELECT 1，返回服务端版本串。"""
    return session.execute(text("SELECT VERSION()")).scalar_one()


def reset_factory() -> None:
    """测试专用：清空单例，让下一次调用重建 engine/sessionmaker。"""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
