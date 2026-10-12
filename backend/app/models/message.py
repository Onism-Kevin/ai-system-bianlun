"""S1-4：messages 消息流表（docs/contracts/schema_v3_messages.md 表 1 定稿）。

- 方案 A（errata E-1）：`seq` 即主键、无独立 id 列；对 API 对外 message id = seq。
- seq 全局自增、各会话交错分配（A 得 1,3,5；B 得 2,4）；会话内单调由
  "全局单调序列的子序列仍单调"保证；回放 `WHERE session_id=? AND seq>? ORDER BY seq`。
- status 三值枚举（errata E-3）：streaming / complete / paused_truncated。
- agent_role（errata E-5 补充 1）：assistant 细分 'pro'/'con'/'judge'/'coach'；
  user/system 消息为 NULL。值域校验属应用层（DB 不加 CHECK，同 E-2 哲学）。
- 暂停续写：同一行重写 content（契约 5.2），updated_at 由 onupdate 刷新。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import MYSQL_TABLE_ARGS, Base

# 复用同一 Enum 实例，保证 ORM 与后续 Alembic 迁移生成同一个 MySQL ENUM 类型
MESSAGE_ROLE_ENUM = Enum("user", "assistant", "system", name="message_role")
MESSAGE_STATUS_ENUM = Enum(
    "streaming", "complete", "paused_truncated", name="message_status"
)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        # 方案 A 下唯一性已蕴含（seq 全局唯一），保留作回放查询覆盖索引（契约 5.1）
        UniqueConstraint("session_id", "seq", name="uq_messages_session_id_seq"),
        MYSQL_TABLE_ARGS,
    )

    # 方案 A：seq 即主键（errata E-1），对 API 即 message id
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "sessions.id", ondelete="CASCADE", name="fk_messages_session_id_sessions"
        ),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(MESSAGE_ROLE_ENUM, nullable=False)
    # assistant 细分角色；user/system 消息为 NULL。高频查询字段，不进 detail JSON
    agent_role: Mapped[str | None] = mapped_column(String(16), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        MESSAGE_STATUS_ENUM, nullable=False, server_default=text("'streaming'")
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
