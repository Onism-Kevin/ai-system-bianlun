"""S3-5：学生反馈 API（POST/GET /api/tasks/{task_id}/feedback，api.md:68-69）。

端点（2 个）：
- POST /api/tasks/{task_id}/feedback   学生提交反馈（upsert，UNIQUE(task_id,student_id)）
- GET  /api/tasks/{task_id}/feedback   教师读全部学生反馈

403/404 分层（errata E-16）：
- POST（学生动作）：任务不可读 → 404；未提交该任务 → 404（存在性隐藏）。
- GET（教师动作）：任务不可读 → 404；非课程教师 → 403。

前置校验：POST 要求学生**已提交该任务**（api.md:68「404 未提交该任务 /
非课程成员」）——未做过任务的学生不能给体验评分。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import can_read_task, get_current_user, is_task_teacher
from app.core.database import get_db
from app.models.feedback import FeedbackForm
from app.models.task import Task, TaskSubmission
from app.models.user import User
from app.schemas.feedback import (
    FeedbackCreate,
    FeedbackOut,
    FeedbackPostResponse,
)

router = APIRouter(prefix="/api/tasks", tags=["feedback"])

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在或无权访问"
)
_FORBIDDEN = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail="仅课程教师可操作"
)


def _now() -> datetime:
    return datetime.now()


# ---- POST /api/tasks/{task_id}/feedback ----


@router.post("/{task_id}/feedback", response_model=FeedbackPostResponse)
def create_feedback(
    task_id: int,
    body: FeedbackCreate,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
) -> FeedbackPostResponse:
    """学生提交反馈（upsert：一生一任务一份）。

    前置：任务可读（404）且本人已提交该任务（404，存在性隐藏）。
    """
    # ① 任务可读性（E-16 第一层）
    task = db.get(Task, task_id)
    if task is None or not can_read_task(db, me, task):
        raise _NOT_FOUND
    # ② 未提交该任务 → 404（存在性隐藏）
    submitted = db.scalar(
        select(TaskSubmission.id).where(
            TaskSubmission.task_id == task.id,
            TaskSubmission.student_id == me.id,
        )
    )
    if submitted is None:
        raise _NOT_FOUND

    # ③ upsert（UNIQUE(task_id, student_id)）
    existing = db.scalar(
        select(FeedbackForm).where(
            FeedbackForm.task_id == task.id, FeedbackForm.student_id == me.id
        )
    )
    if existing is not None:
        existing.scores = body.scores.model_dump()
        existing.comment = body.comment
        existing.submitted_at = _now()
        db.commit()
        return FeedbackPostResponse(id=existing.id)

    fb = FeedbackForm(
        task_id=task.id,
        student_id=me.id,
        scores=body.scores.model_dump(),
        comment=body.comment,
        submitted_at=_now(),
    )
    db.add(fb)
    try:
        db.commit()
    except IntegrityError:
        # 并发：另一请求刚插入同一 (task_id, student_id)
        db.rollback()
        existing = db.scalar(
            select(FeedbackForm).where(
                FeedbackForm.task_id == task.id, FeedbackForm.student_id == me.id
            )
        )
        if existing is None:
            raise
        existing.scores = body.scores.model_dump()
        existing.comment = body.comment
        existing.submitted_at = _now()
        db.commit()
        return FeedbackPostResponse(id=existing.id)
    return FeedbackPostResponse(id=fb.id)


# ---- GET /api/tasks/{task_id}/feedback（教师）----


@router.get("/{task_id}/feedback", response_model=list[FeedbackOut])
def list_feedback(
    task_id: int,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
) -> list[FeedbackOut]:
    """教师读全部学生反馈（S3-5 汇总对象）。

    E-16 分层：① 任务不可读 → 404；② 非课程教师 → 403。
    """
    task = db.get(Task, task_id)
    if task is None or not can_read_task(db, me, task):
        raise _NOT_FOUND
    if not is_task_teacher(db, me, task):
        raise _FORBIDDEN
    rows = db.scalars(
        select(FeedbackForm)
        .where(FeedbackForm.task_id == task.id)
        .order_by(FeedbackForm.submitted_at)
    ).all()
    return [
        FeedbackOut(
            student_id=r.student_id,
            scores=r.scores,
            comment=r.comment,
            created_at=r.submitted_at,
        )
        for r in rows
    ]
