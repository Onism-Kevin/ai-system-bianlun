"""S1-2：courses / course_members 两张表（docs/contracts/schema_v1.md §3 §4 定稿）。

- courses：教师建课（S3-2）；invite_code 为课程级加入码（生成规则属 S3-3
  实现约束：6~8 位 A-Z0-9 剔除 I/O/0/1）；term 为学期标签（NULL 预留）。
- teacher_id 外键用 ON DELETE RESTRICT：防止删教师账号产生孤儿课；
  正确流程是先归档/转移课程再删账号。
- 建课时"teacher_id 对应用户必须有 teacher 角色"由应用层校验（S3-2 落地），
  DB 层不做跨表 CHECK。
- course_members：学生加入课程的成员表；教师身份一律查 courses.teacher_id，
  成员表只有学生行。UNIQUE(course_id, user_id) 防重复加入。
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


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    teacher_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_courses_teacher_id_users"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    invite_code: Mapped[str] = mapped_column(String(8), nullable=False, unique=True)
    term: Mapped[str | None] = mapped_column(String(20), nullable=True)
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


class CourseMember(Base):
    __tablename__ = "course_members"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("courses.id", ondelete="CASCADE", name="fk_course_members_course_id_courses"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_course_members_user_id_users"),
        nullable=False,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        UniqueConstraint("course_id", "user_id", name="uq_course_members_course_id_user_id"),
        MYSQL_TABLE_ARGS,
    )
