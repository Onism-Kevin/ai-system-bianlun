"""S1-3：sessions 练习会话表（docs/contracts/schema_v2_tasks.md 定稿）。

- visibility 校验在**应用层**（errata E-2）：DB 故意不设 CHECK——
  DB CHECK 报错不友好、加第三态要 ALTER、跨表存在性本就得应用层查。
  `validate_session_visibility()` 是唯一校验入口，API/服务层必须调用。
- task_id 外键 CASCADE：任务删除时其练习会话一并删除（防孤儿行）。
- status 五态与 S2-2 状态机一致；由应用层在状态转移时写入。
- ORM 类名用 TrainingSession 避免与 sqlalchemy.orm.Session 撞名；表名仍是 sessions。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# 复用同一 Enum 实例，保证 ORM 与后续 Alembic 迁移生成同一个 MySQL ENUM 类型
SESSION_VISIBILITY_ENUM = Enum("private", "task", name="session_visibility")
SESSION_STATUS_ENUM = Enum(
    "waiting", "generating", "paused", "finished", "failed", name="session_status"
)


def validate_session_visibility(visibility: str, task_id: int | None) -> None:
    """应用层校验（契约 5.3，errata E-2 取代 DB CHECK）。

    规则：visibility='task' ⇔ task_id 非空。
    违反时抛 ValueError（API 层映射为 4xx，消息可直接给用户看）。
    """
    if visibility == "task" and task_id is None:
        raise ValueError("任务练习会话必须关联任务（task_id 不能为空）")
    if visibility == "private" and task_id is not None:
        raise ValueError("个人练习会话不能关联任务（task_id 必须为空）")


class TrainingSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_sessions_owner_id_users"),
        nullable=False,
    )
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    visibility: Mapped[str] = mapped_column(
        SESSION_VISIBILITY_ENUM, nullable=False, server_default=text("'private'")
    )
    task_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("tasks.id", ondelete="CASCADE", name="fk_sessions_task_id_tasks"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        SESSION_STATUS_ENUM, nullable=False, server_default=text("'waiting'")
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
