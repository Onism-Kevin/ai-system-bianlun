"""S3-4：提交 API（session→submission 快照）（api.md:65-67，逐字对齐）。

端点（3 个）：
- POST /api/tasks/{task_id}/submissions     提交（upsert，E-5）
- GET  /api/tasks/{task_id}/submissions     教师列表（仅已提交行）
- GET  /api/tasks/{task_id}/submissions/me  本人提交（未提交 → 404）

upsert 语义（errata E-5 补充 2）：`task_submissions` 有 UNIQUE(task_id, student_id)，
学生换会话重做任务 → 更新旧行（session_id + submitted_at），`replaced=true`；
旧会话 visibility 处置：推荐改 private（计划书 S3-4 备注补）——否则旧会话仍是
visibility='task' 但不再被 task_submissions 引用，教师端"按提交看会话"会漏、
"按任务看会话"会多。

403/404 分层（errata E-16）：教师列表先判可读（404），再判课程教师（403）。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import can_read_task, get_current_user, is_task_teacher
from app.core.database import get_db
from app.models.session import TrainingSession
from app.models.task import Task, TaskSubmission
from app.models.user import User
from app.schemas.submission import (
    SubmissionCreate,
    SubmissionListItem,
    SubmissionOut,
    SubmissionPostResponse,
)

router = APIRouter(prefix="/api/tasks", tags=["submissions"])

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在或无权访问"
)
_FORBIDDEN = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail="仅课程教师可操作"
)


def _now() -> datetime:
    """提交时间（本地 naive，与 DB DATETIME 一致）。"""
    return datetime.now()


# ---- POST /api/tasks/{task_id}/submissions ----


@router.post(
    "/{task_id}/submissions",
    response_model=SubmissionPostResponse,
)
def create_submission(
    task_id: int,
    body: SubmissionCreate,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
) -> SubmissionPostResponse:
    """提交会话快照到任务（upsert）。

    E-16 分层：任务不可读 → 404；会话不存在/非 owner/非本任务 → 404
    （存在性隐藏，不暴露）。
    """
    # ① 任务可读性（E-16 第一层）
    task = db.get(Task, task_id)
    if task is None or not can_read_task(db, me, task):
        raise _NOT_FOUND
    # ② 会话归属（owner 校验；session 必须属于本任务）
    session = db.get(TrainingSession, body.session_id)
    if (
        session is None
        or session.owner_id != me.id
        or session.task_id != task.id
    ):
        raise _NOT_FOUND

    # ③ upsert（E-5：UNIQUE(task_id, student_id)）
    existing = db.scalar(
        select(TaskSubmission).where(
            TaskSubmission.task_id == task.id,
            TaskSubmission.student_id == me.id,
        )
    )
    submitted_at = _now()

    if existing is not None:
        # 换会话重做：旧会话 visibility 处置（推荐改 private）
        if existing.session_id != session.id:
            old_session = db.get(TrainingSession, existing.session_id)
            if old_session is not None and old_session.visibility == "task":
                old_session.visibility = "private"
        existing.session_id = session.id
        existing.submitted_at = submitted_at
        replaced = True
        db.commit()
    else:
        sub = TaskSubmission(
            student_id=me.id,
            task_id=task.id,
            session_id=session.id,
            submitted_at=submitted_at,
        )
        db.add(sub)
        try:
            db.commit()
        except IntegrityError:
            # 并发：另一请求刚插入同一 (task_id, student_id) → 回滚后按 upsert 重试
            db.rollback()
            existing = db.scalar(
                select(TaskSubmission).where(
                    TaskSubmission.task_id == task.id,
                    TaskSubmission.student_id == me.id,
                )
            )
            if existing is None:
                raise
            existing.session_id = session.id
            existing.submitted_at = submitted_at
            db.commit()
            replaced = True
        else:
            existing = sub
            replaced = False

    db.refresh(existing)  # 取服务端 submitted_at
    return SubmissionPostResponse(
        id=existing.id,
        session_id=session.id,
        submitted_at=existing.submitted_at,
        replaced=replaced,
    )


# ---- GET /api/tasks/{task_id}/submissions（教师列表）----


@router.get("/{task_id}/submissions", response_model=list[SubmissionListItem])
def list_submissions(
    task_id: int,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
) -> list[SubmissionListItem]:
    """教师列表：仅已提交行（未提交无行）。

    E-16 分层：① 任务不可读 → 404；② 非课程教师 → 403。
    """
    task = db.get(Task, task_id)
    if task is None or not can_read_task(db, me, task):
        raise _NOT_FOUND
    if not is_task_teacher(db, me, task):
        raise _FORBIDDEN
    rows = db.scalars(
        select(TaskSubmission)
        .where(TaskSubmission.task_id == task.id)
        .order_by(TaskSubmission.submitted_at)
    ).all()
    return [
        SubmissionListItem(
            student_id=r.student_id, session_id=r.session_id, submitted_at=r.submitted_at
        )
        for r in rows
    ]


# ---- GET /api/tasks/{task_id}/submissions/me ----


@router.get("/{task_id}/submissions/me")
def get_my_submission(
    task_id: int,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
) -> SubmissionOut:
    """本人提交记录；未提交 → 404（不暴露存在性）。"""
    task = db.get(Task, task_id)
    if task is None or not can_read_task(db, me, task):
        raise _NOT_FOUND
    sub = db.scalar(
        select(TaskSubmission).where(
            TaskSubmission.task_id == task.id,
            TaskSubmission.student_id == me.id,
        )
    )
    if sub is None:
        raise _NOT_FOUND
    return SubmissionOut.model_validate(sub)
