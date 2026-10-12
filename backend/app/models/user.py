"""S1-2：users / user_roles 两张表（docs/contracts/schema_v1.md §1 §2 定稿）。

- users：账号与凭证；username 唯一，bcrypt 哈希存 password_hash；
  is_active=0 即停用（登录层拒绝，不在 DB 层拦截）。
- user_roles：多角色设计（同一账号可同时是 student/teacher/admin），
  UNIQUE(user_id, role) 防重复授予；'admin' 为契约 5.3 预留枚举值，
  首版不实现管理员功能。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# 复用同一 Enum 实例，保证 ORM 与后续 Alembic 迁移生成同一个 MySQL ENUM 类型
# 'admin' 为契约 5.3 预留值：纯占位，首版不实现任何管理员功能（无 API、无界面）
USER_ROLE_ENUM = Enum("student", "teacher", "admin", name="user_role")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )


class UserRole(Base):
    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_user_roles_user_id_users"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(USER_ROLE_ENUM, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        # 防同一角色重复授予；多角色本身不受限（方案第 8 节第 1 条）
        UniqueConstraint("user_id", "role", name="uq_user_roles_user_id_role"),
    )
