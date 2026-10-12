"""Alembic 环境（同步 SQLAlchemy + pymysql）。

关键接线（S1-5）：
1. URL 直接取 `settings.sqlalchemy_url()` **URL 对象**，不经 alembic.ini 字符串
   往返——避开 SQLAlchemy 2.x make_url 不 percent-decode 密码的 1045 坑
   （见 app/core/config.py sqlalchemy_url() 注释）。
2. target_metadata = Base.metadata（import app.models 注册全部 15 张表）。
3. APP_ENV 决定连哪个 schema（dev→sfb_dev / test→sfb_test / demo→sfb_demo）。
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.engine import create_engine

from alembic import context

# 让 `app` 包可导入（backend/ 在 sys.path）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.models import Base  # noqa: E402  import 即注册全部表

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _make_engine():
    """URL 对象直传 create_engine（不走 config.get_main_option 字符串）。"""
    return create_engine(get_settings().sqlalchemy_url(), poolclass=pool.NullPool)


def run_migrations_offline() -> None:
    """离线模式：只渲染 SQL 不连库。"""
    url = get_settings().sqlalchemy_url().render_as_string()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,  # 类型差异参与比对（S1-5 逐列一致验收依赖）
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连当前 APP_ENV 对应的 schema。"""
    connectable = _make_engine()
    with connectable.connect() as connection:
        do_run_migrations(connection)
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
