"""S1-3：tasks / task_submissions 两张表（docs/contracts/schema_v2_tasks.md 定稿）。

- courses 外键 RESTRICT：不允许删带任务的课程（MVP 无删课 API，防误删数据）。
- task_submissions 双唯一键：UNIQUE(task_id, session_id)（契约 5.3）+
  UNIQUE(task_id, student_id)（用户拍板，errata E-5）——一个学生对一个任务仅一份提交。
  连带语义：学生换会话重做任务会被 DB 拒绝 → S3-4 提交 API 必须 upsert
  （INSERT ... ON DUPLICATE KEY UPDATE，见计划书 S3-4 备注）。
- student_id / session_id 外键 CASCADE：删账号、删任务、删会话时清理提交记录。
- join_code NULL 允许（不需要加入码的任务）；MySQL UNIQUE 允许多个 NULL。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import MYSQL_TABLE_ARGS, Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("courses.id", ondelete="RESTRICT", name="fk_tasks_course_id_courses"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    material: Mapped[str | None] = mapped_column(Text, nullable=True)
    join_code: Mapped[str | None] = mapped_column(String(8), nullable=True, unique=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0")
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


class TaskSubmission(Base):
    __tablename__ = "task_submissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_task_submissions_student_id_users"),
        nullable=False,
    )
    task_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tasks.id", ondelete="CASCADE", name="fk_task_submissions_task_id_tasks"),
        nullable=False,
    )
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("sessions.id", ondelete="CASCADE", name="fk_task_submissions_session_id_sessions"),
        nullable=False,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        UniqueConstraint("task_id", "session_id", name="uq_task_submissions_task_id_session_id"),
        UniqueConstraint("task_id", "student_id", name="uq_task_submissions_task_id_student_id"),
        MYSQL_TABLE_ARGS,
    )
