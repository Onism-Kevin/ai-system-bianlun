"""S1-4：audit_events 审计留痕表（docs/contracts/schema_v3_messages.md 表 5 定稿）。

- actor_id ON DELETE SET NULL：删账号后留痕保留（断链人、保事件）；NULL=系统动作。
- ip VARCHAR(45)（errata E-5）：IPv6 上限 45 位；登录留痕常用。
- detail JSON：变更前后值/上下文。**密码/密钥永不入此列——实现层约束**
  （S3-6"不记录敏感数据"；DB 无法强制，写日志的代码负责）。
- teacher 角色的审计细则（哪些动作必留痕）→ S3-1 实现时定，表结构已支持。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # NULL=系统动作；删账号后事件保留（SET NULL 断链人、保事件）
    actor_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id", ondelete="SET NULL", name="fk_audit_events_actor_id_users"
        ),
        nullable=True,
    )
    # 如 user.login / user.deactivate / role.grant / task.create / submission.view
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        index=True,  # (created_at) 索引供按时间审计查询
    )
