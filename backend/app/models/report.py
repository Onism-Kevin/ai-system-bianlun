"""S1-4：reports 复盘报告表（docs/contracts/schema_v3_messages.md 表 3 定稿）。

- 无 UNIQUE(session_id)（errata E-5 用户拍板）：允许重跑复盘生成新报告行，
  created_at 最新者为当前版；S3-5 取"每会话最新一份"。
- scores JSON 免锁死维度增删；overall_score 冗余列免每次 JSON 计算（S3-5 按分统计）。
- rubric_version = 量表快照标识（S1-9 rubric.json 版本），量表改版后旧报告仍可解释。
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "sessions.id", ondelete="CASCADE", name="fk_reports_session_id_sessions"
        ),
        nullable=False,
    )
    rubric_version: Mapped[str] = mapped_column(String(20), nullable=False)
    scores: Mapped[dict] = mapped_column(JSON, nullable=False)
    overall_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
