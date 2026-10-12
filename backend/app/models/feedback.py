"""S1-4：feedback_forms 学生反馈表（docs/contracts/schema_v3_messages.md 表 4 定稿）。

- 整表为行业惯例起草（方案/任务卡只有表名）；反馈分项评分用 JSON 免锁死维度。
- `UNIQUE(task_id, student_id)`：一生一任务一份反馈。
- 若对反馈内容有具体设计（如问卷题目固定），S3 实现前提出（契约草案已注明）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import MYSQL_TABLE_ARGS, Base


class FeedbackForm(Base):
    __tablename__ = "feedback_forms"
    __table_args__ = (
        UniqueConstraint(
            "task_id", "student_id", name="uq_feedback_forms_task_id_student_id"
        ),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "tasks.id", ondelete="CASCADE", name="fk_feedback_forms_task_id_tasks"
        ),
        nullable=False,
    )
    student_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id", ondelete="CASCADE", name="fk_feedback_forms_student_id_users"
        ),
        nullable=False,
    )
    scores: Mapped[dict] = mapped_column(JSON, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
