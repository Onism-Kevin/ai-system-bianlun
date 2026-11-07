"""S3-4：task_submissions 端点出入参（api.md:65-67，逐字对齐）。

- POST 出参：200 `{id, session_id, submitted_at, replaced:boolean}`（E-5 upsert）
- GET 列表出参：200 `[{student_id, session_id, submitted_at}]`（教师，仅已提交行）
- GET /me 出参：200 `{submission}`；未提交 → 404（不暴露存在性）
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SubmissionOut(BaseModel):
    """单条提交完整出参（GET /submissions/me）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    task_id: int
    session_id: int
    submitted_at: datetime


class SubmissionListItem(BaseModel):
    """教师列表项（GET /submissions）：{student_id, session_id, submitted_at}。"""

    student_id: int
    session_id: int
    submitted_at: datetime


class SubmissionCreate(BaseModel):
    """POST /submissions 入参：{session_id}。"""

    session_id: int


class SubmissionPostResponse(BaseModel):
    """POST /submissions 出参：{id, session_id, submitted_at, replaced}。"""

    id: int
    session_id: int
    submitted_at: datetime
    replaced: bool
