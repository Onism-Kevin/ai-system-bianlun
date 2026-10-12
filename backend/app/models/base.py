"""S1-2：ORM 声明基类。

命名约定统一约束名（Alembic autogenerate 与 MySQL DDL 友好）：
- 唯一约束 uq_<表>_<列>；外键 fk_<表>_<列>_<被引用表>；主键 pk_<表>；索引 ix_<表>_<列>
字段定义的权威来源：docs/contracts/schema_v1.md（已勾选定稿）。
"""
from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# 每张表显式带字符集/排序规则（S1-5 验收项），不依赖 MySQL 库默认；
# 自带 __table_args__ 元组的表需手动把本字典追加到元组末尾。
MYSQL_TABLE_ARGS = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}


class Base(DeclarativeBase):
    """全部 ORM 模型的声明基类（携带统一命名约定的 MetaData）。"""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    __table_args__ = MYSQL_TABLE_ARGS
