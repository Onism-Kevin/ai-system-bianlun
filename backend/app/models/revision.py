"""S1-4：revisions 观点修改稿表（docs/contracts/schema_v3_messages.md 表 2 定稿）。

- 初稿与每版修改稿各一行（S2-11"草稿保存"+"修改稿"）；version 从 1 递增，
  `UNIQUE(session_id, version)`。
- status draft/final（errata E-5）：S4"复用学生提交的原观点作对比"要知道哪版是定稿。
- student_id 冗余于 session.owner_id：越权检查免 join（同 schema_v2 焦点三哲学）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

REVISION_STATUS_ENUM = Enum("draft", "final", name="revision_status")


class Revision(Base):
    __tablename__ = "revisions"
    __table_args__ = (
        UniqueConstraint("session_id", "version", name="uq_revisions_session_id_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "sessions.id", ondelete="CASCADE", name="fk_revisions_session_id_sessions"
        ),
        nullable=False,
    )
    student_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id", ondelete="CASCADE", name="fk_revisions_student_id_users"
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        REVISION_STATUS_ENUM, nullable=False, server_default=text("'draft'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
