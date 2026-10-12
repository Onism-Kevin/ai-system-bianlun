"""S1-2 模型测试夹具：固定连 sfb_test（APP_ENV=test），建表→测→拆表。

S1-5 切换（计划书任务备注，用户 2026-10-12 指示）：建表方式从
`Base.metadata.create_all` 改为 **先 DROP ALL TABLES 再 `alembic upgrade head`**
——sfb_test 的表结构现在与生产完全同源（migration 是唯一建表入口），
create_all 与 migration 产物的任何结构差异都不再被"两边都绿"掩盖。

- 模块级：DROP ALL（FK 关闭，清空含 alembic_version 在内的一切遗留表）
  → 进程内 `alembic upgrade head`（env.py 按 APP_ENV=test 连 sfb_test）
  → 交付 module engine；模块结束再次 DROP ALL，sfb_test 保持空库；
- 函数级：每用例前 TRUNCATE 全表（重置 AUTO_INCREMENT，等价于原
  "重建表"的隔离效果，但保持 migration 建出来的表结构不动）；
- APP_ENV 必须在首次 get_settings() 之前写入进程环境。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ["APP_ENV"] = "test"

from alembic import command  # noqa: E402
from alembic.config import Config as AlembicConfig  # noqa: E402
from sqlalchemy import create_engine, inspect  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import reset_factory  # noqa: E402
from app.models import Base  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[2]  # backend/


def _drop_all_tables(eng) -> None:
    """DROP 一切表（含 alembic_version 等非 ORM 表）；关 FK 避免父子依赖拦截。"""
    with eng.begin() as conn:
        conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
        try:
            for t in inspect(eng).get_table_names():
                conn.exec_driver_sql(f"DROP TABLE IF EXISTS `{t}`")
        finally:
            conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")


def _truncate_all_tables(eng) -> None:
    """每用例前清空所有表（TRUNCATE 重置 AUTO_INCREMENT），表结构保持 migration 产物。"""
    with eng.begin() as conn:
        conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
        try:
            for t in inspect(eng).get_table_names():
                conn.exec_driver_sql(f"TRUNCATE TABLE `{t}`")
        finally:
            conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")


def _alembic_upgrade_head() -> None:
    """进程内执行 `alembic upgrade head`（env.py 读 APP_ENV=test → sfb_test）。"""
    cfg = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="module")
def engine():
    """模块级 engine：sfb_test 清空后由 alembic upgrade head 建表（S1-5 migration 接管）。"""
    get_settings.cache_clear()
    reset_factory()
    url = get_settings().sqlalchemy_url()
    assert url.database == "sfb_test", f"测试必须连 sfb_test，实际 {url.database}"
    eng = create_engine(url, pool_pre_ping=True, future=True)

    _drop_all_tables(eng)
    _alembic_upgrade_head()

    # upgrade 成功的基本保证：ORM 全部 12 张表 + alembic 版本表齐备
    insp = inspect(eng)
    db_tables = set(insp.get_table_names())
    missing = set(Base.metadata.tables) - db_tables
    assert not missing, f"alembic upgrade head 后缺表：{sorted(missing)}"
    assert "alembic_version" in db_tables, "alembic upgrade head 后缺 alembic_version 表"

    yield eng
    _drop_all_tables(eng)
    eng.dispose()
    reset_factory()


@pytest.fixture()
def session(engine):
    """函数级 Session：每用例前 TRUNCATE 全表（防上一用例已提交数据残留撞唯一键），
    表结构始终是 migration 产物（不再 create_all 重建）。"""
    from sqlalchemy.orm import sessionmaker

    _truncate_all_tables(engine)
    sess = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield sess
    finally:
        sess.close()
