"""S1-5 卡2：migration 产物 ↔ ORM 声明一致性比对（三轮加严，sfb_dev）。

比对对象：`sfb_dev`（`alembic upgrade head` 的真实产物）与 `app.models.Base.metadata`。
用 SQLAlchemy `inspect(engine)` 反射 DB 表结构，与 ORM `__table__` 逐项比对，
**差异必须为 0**——这是计划书 S1-5 任务备注（用户 2026-10-12 指示）要求的
"ORM 声明与 migration 产物一致（表结构逐列比对）"的机器验证。

三轮加严（每轮绿了再加下一轮）：
  1. test_round1_table_and_column_names —— 只比表名 + 列名
  2. test_round2_column_type_nullable_default —— 加类型、nullable、默认值
  3. test_round3_constraints —— 加 PK、FK、索引、ENUM 值
  3+ test_round3_table_options —— 表级 charset / collate / engine（Round 3 增补）

与本目录其他模型测试的分工：test_user.py 等跑 sfb_test（S1-5 起由 alembic upgrade
head 建表，测 ORM 行为）；本文件跑 sfb_dev（migration 建表，测 DDL 产物与 ORM 声明
一致），互不干扰。

MySQL 方言反射的 5 个坑与归一化（pitfalls，见任务卡）——归一化公共工具已抽到
本目录 `_type_utils.py`（长期资产，后续加表测试复用）：
  1. VARCHAR(50) 可能反射为泛型 String(50)、TINYINT(1) 可能反射为 TINYINT/BOOLEAN
     → 双方类型统一用 MySQL 方言编译成 DDL 文本，再按 canon_type() 规则折算
     （BOOL/TINYINT/TINYINT(1) → BOOLEAN；剥列级 COLLATE 子句；剥整型显示宽度；
      NUMERIC ≡ DECIMAL 同义折算）；
  2. ENUM 值顺序要和 ORM Enum 一致 → 按元组逐位比对（MySQL DDL 保序，不排序不转集合）；
  3. CURRENT_TIMESTAMP 反射可能带精度括号 → canon_default() 正则剥 `(...)` 并剥引号；
  4. 索引名 op.f() 前缀只是 DDL 渲染包装，反射回来是纯名 → strip_op_f() 剥外壳；
  5. nullable 默认：ORM 未显式声明是 True，MySQL 反射 YES → 双方 bool() 后再比。

维护点（加表 / 新增 migration 后必须同步更新，故意硬编码为绊线）：
  - EXPECTED_REVISION 基线常量；
  - round1 的 `len(db_names) == 12` 基线数字。
"""
from __future__ import annotations

import pytest
from sqlalchemy import Enum, ForeignKeyConstraint, UniqueConstraint, create_engine, inspect, text

from _type_utils import canon_default, canon_type, orm_default, strip_op_f  # noqa: E402
from app.core.config import database_url_for  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.base import MYSQL_TABLE_ARGS  # noqa: E402

# S1-5 卡1 通过时的基线 revision（backend/alembic/versions/5f605c7da13a_initial_12_tables.py）
EXPECTED_REVISION = "5f605c7da13a"
# Alembic 版本表，不参与业务表比对
META_TABLE = "alembic_version"
# 期望表级选项直接取自 ORM 声明源头 MYSQL_TABLE_ARGS（避免两处硬编码漂移）；
# 断言时统一 lower() 比较（防 utf8mb4 vs UTF8MB4、InnoDB vs innodb 大小写误报）。
EXPECTED_CHARSET = MYSQL_TABLE_ARGS["mysql_charset"].lower()
EXPECTED_COLLATE = MYSQL_TABLE_ARGS["mysql_collate"].lower()
# engine：ORM 未声明（MySQL 8 默认 InnoDB），属 S1-5 验收项的单边核验
EXPECTED_ENGINE = "innodb"


# --------------------------------------------------------------------------
# 夹具：sfb_dev engine + 反射结果（前置校验：迁移已升级到期望 revision）
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def dev_engine():
    """sfb_dev 的只读比对 engine（不建表、不改数据，测完即关）。"""
    url = database_url_for("dev")
    assert url.database == "sfb_dev", f"一致性测试必须连 sfb_dev，实际 {url.database}"
    eng = create_engine(url, pool_pre_ping=True, future=True)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # MySQL 不可达时跳过并打印原因（计划书 S1-12 约定）
        eng.dispose()
        pytest.skip(f"MySQL 不可达，跳过迁移一致性比对：{exc}")
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def inspector(dev_engine):
    """反射 sfb_dev；前置校验 alembic_version 存在且等于期望 revision。"""
    insp = inspect(dev_engine)
    if META_TABLE not in insp.get_table_names():
        pytest.fail(f"sfb_dev 没有 {META_TABLE} 表：先执行 alembic upgrade head 再跑本测试")
    with dev_engine.connect() as conn:
        rev = conn.execute(text(f"SELECT version_num FROM {META_TABLE}")).scalar_one()
    if rev != EXPECTED_REVISION:
        pytest.fail(
            f"alembic_version={rev}，期望 {EXPECTED_REVISION}：先执行 alembic upgrade head 再跑本测试"
        )
    return insp


def _orm_tables() -> dict:
    """ORM 侧：Base.metadata.tables（import app.models 已注册全部 12 张表）。"""
    return Base.metadata.tables


def _db_table_names(insp) -> set[str]:
    """DB 侧：业务表名（剔除 alembic 版本表）。"""
    return {t for t in insp.get_table_names() if t != META_TABLE}


# --------------------------------------------------------------------------
# 第一轮：只比表名 + 列名
# --------------------------------------------------------------------------
def test_round1_table_and_column_names(inspector):
    """Round 1：12 张业务表一一对应，且每张表列名集合一致（差异 = 0）。"""
    orm_names = set(_orm_tables())
    db_names = _db_table_names(inspector)

    missing_in_db = sorted(orm_names - db_names)
    extra_in_db = sorted(db_names - orm_names)
    assert not missing_in_db and not extra_in_db, (
        f"表名不一致：migration 缺 {missing_in_db}，migration 多 {extra_in_db}"
    )
    assert len(db_names) == 12, f"业务表应为 12 张（S1-5 基线；15 张含 S4 图谱三表），实际 {len(db_names)}"

    for name in sorted(orm_names):
        orm_cols = [c.name for c in _orm_tables()[name].columns]
        db_cols = [c["name"] for c in inspector.get_columns(name)]
        assert orm_cols == db_cols, (
            f"表 {name} 列不一致：\n  ORM  = {orm_cols}\n  DB   = {db_cols}"
        )


# --------------------------------------------------------------------------
# 第二轮：加类型、nullable、默认值
# --------------------------------------------------------------------------
def test_round2_column_type_nullable_default(inspector):
    """Round 2：每列的规范类型、nullable、DEFAULT 三项差异 = 0（归一化后）。"""
    for name in sorted(_orm_tables()):
        orm_cols = {c.name: c for c in _orm_tables()[name].columns}
        db_cols = {c["name"]: c for c in inspector.get_columns(name)}

        for col_name, orm_col in orm_cols.items():
            ref = db_cols[col_name]
            # 坑 1：类型归一化后比（TINYINT(1)/BOOL/BOOLEAN → BOOLEAN；剥 COLLATE；NUMERIC≡DECIMAL）
            assert canon_type(orm_col.type) == canon_type(ref["type"]), (
                f"{name}.{col_name} 类型不一致：ORM={canon_type(orm_col.type)} "
                f"DB={canon_type(ref['type'])}（原值 ORM={orm_col.type!r} DB={ref['type']!r}）"
            )
            # 坑 5：nullable 双方 bool() 后再比
            assert bool(orm_col.nullable) == bool(ref["nullable"]), (
                f"{name}.{col_name} nullable 不一致：ORM={orm_col.nullable} DB={ref['nullable']}"
            )
            # 坑 3：CURRENT_TIMESTAMP 剥精度括号 + 默认值引号归一化后比
            orm_def = orm_default(orm_col)
            db_def = canon_default(ref["default"])
            assert orm_def == db_def, (
                f"{name}.{col_name} DEFAULT 不一致：ORM={orm_def!r} DB={db_def!r}"
                f"（原值 ORM={orm_col.server_default!r} DB={ref['default']!r}）"
            )


# --------------------------------------------------------------------------
# 第三轮：加 PK（含 AUTO_INCREMENT）、FK、索引、ENUM 值
# --------------------------------------------------------------------------
def test_round3_constraints(inspector):
    """Round 3：主键/外键/索引/ENUM 值四项差异 = 0。

    - PK 含 AUTO_INCREMENT 核验：errata E-1 方案 A 的落地证据
      （messages.seq 即主键且自增；其余表 id 自增主键）；
    - FK 含 ON DELETE 规则（CASCADE/RESTRICT/SET NULL 是契约删除语义）；
    - 索引比对时剔除 MySQL 为 FK **自动**创建的同名索引（那是 InnoDB 实现细节，
      ORM 侧没有对应声明；判定依据 = 索引名等于某条 FK 约束名）；
    - ENUM 值按元组逐位比对（坑 2：顺序敏感）。ENUM 类型名（user_role 等）
      MySQL 不存储，不比。
    """
    for name in sorted(_orm_tables()):
        table = _orm_tables()[name]
        db_cols = {c["name"]: c for c in inspector.get_columns(name)}

        # ---- PK：列 + AUTO_INCREMENT ----
        ref_pk = inspector.get_pk_constraint(name)
        orm_pk_cols = [c.name for c in table.primary_key]
        assert list(ref_pk["constrained_columns"]) == orm_pk_cols, (
            f"{name} 主键列不一致：ORM={orm_pk_cols} DB={ref_pk['constrained_columns']}"
        )
        for pk_col in table.primary_key:
            ref_auto = db_cols[pk_col.name].get("autoincrement")
            assert ref_auto is True, (
                f"{name}.{pk_col.name} 必须是 AUTO_INCREMENT 主键"
                f"（E-1 方案 A / 全局约定 id BIGINT PK AUTO_INCREMENT），DB 反射 autoincrement={ref_auto!r}"
            )

        # ---- FK：名称 + 列 + 被引用表列 + ON DELETE ----
        orm_fks = []
        for cons in table.constraints:
            if isinstance(cons, ForeignKeyConstraint):
                cols = tuple(e.parent.name for e in cons.elements)
                ref_table = cons.elements[0].target_fullname.split(".")[0]
                ref_cols = tuple(e.target_fullname.split(".")[1] for e in cons.elements)
                ondelete = (cons.ondelete or "NO ACTION").upper()
                orm_fks.append((strip_op_f(cons.name), cols, ref_table, ref_cols, ondelete))
        db_fks = []
        for fk in inspector.get_foreign_keys(name):
            ondelete = (fk.get("options", {}).get("ondelete") or "NO ACTION").upper()
            db_fks.append(
                (
                    fk["name"],
                    tuple(fk["constrained_columns"]),
                    fk["referred_table"],
                    tuple(fk["referred_columns"]),
                    ondelete,
                )
            )
        assert sorted(orm_fks) == sorted(db_fks), (
            f"{name} 外键不一致：\n  ORM = {sorted(orm_fks)}\n  DB  = {sorted(db_fks)}"
        )

        # ---- 索引/唯一键（剔除 FK 自动同名索引，坑 4：剥 op.f() 前缀）----
        fk_names = {fk[0] for fk in db_fks}
        db_idx = {}
        for ix in inspector.get_indexes(name):
            ix_name = strip_op_f(ix["name"])
            if ix_name in fk_names:
                continue  # InnoDB 为外键自动创建的索引，非 ORM 显式声明
            db_idx[ix_name] = (tuple(ix["column_names"]), bool(ix["unique"]))
        orm_idx = {}
        for ix in table.indexes:
            orm_idx[strip_op_f(ix.name)] = (
                tuple(c.name for c in ix.columns),
                bool(ix.unique),
            )
        for cons in table.constraints:
            if isinstance(cons, UniqueConstraint):
                orm_idx[strip_op_f(cons.name)] = (
                    tuple(c.name for c in cons.columns),
                    True,
                )
        assert orm_idx == db_idx, (
            f"{name} 索引不一致：\n  ORM = {orm_idx}\n  DB  = {db_idx}"
        )

        # ---- ENUM 值（坑 2：按序逐位比对）----
        for col in table.columns:
            if isinstance(col.type, Enum):
                orm_values = tuple(col.type.enums)
                ref_values = tuple(getattr(db_cols[col.name]["type"], "enums", ()))
                assert orm_values == ref_values, (
                    f"{name}.{col.name} ENUM 值不一致：\n  ORM = {orm_values}\n  DB  = {ref_values}"
                )


# --------------------------------------------------------------------------
# 第三轮增补：表级 charset / collate / engine
# --------------------------------------------------------------------------
def test_round3_table_options(inspector):
    """Round 3 增补：表级 charset / collate / engine 差异 = 0。

    防的是隐蔽漂移：S2/S3/S4 加表若忘带 MYSQL_TABLE_ARGS，autogenerate 的
    migration 就缺显式 charset，部署到新库会用 MySQL 默认（可能非 utf8mb4），
    列级比对不会报错、上线后才炸——表级选项必须进机器验证。

    防误报：反射值统一 lower() 后比（utf8mb4 vs UTF8MB4、InnoDB vs innodb）。
    SQLAlchemy MySQL 方言把表默认字符集反射在 `mysql_default charset` 键
    （**带空格**，与表选项参数名 mysql_charset 不同），两个键都认，取到谁比谁。
    """
    for name in sorted(_orm_tables()):
        opts = inspector.get_table_options(name)
        db_charset = str(opts.get("mysql_default charset") or opts.get("mysql_charset") or "").lower()
        db_collate = str(opts.get("mysql_collate") or "").lower()
        db_engine = str(opts.get("mysql_engine") or "").lower()
        assert db_charset == EXPECTED_CHARSET, (
            f"{name} 表级 charset 不一致：DB={db_charset!r} 期望={EXPECTED_CHARSET!r}（opts={opts}）"
        )
        assert db_collate == EXPECTED_COLLATE, (
            f"{name} 表级 collate 不一致：DB={db_collate!r} 期望={EXPECTED_COLLATE!r}（opts={opts}）"
        )
        assert db_engine == EXPECTED_ENGINE, (
            f"{name} 表级 engine 不一致：DB={db_engine!r} 期望={EXPECTED_ENGINE!r}（opts={opts}）"
        )
