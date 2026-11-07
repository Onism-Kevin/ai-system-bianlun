"""S3-5：班级汇总统计 API（GET /api/courses/{course_id}/summary，api.md:70）。

端点（1 个，纯教师动作）：
- GET /api/courses/{course_id}/summary?task_id?
  → 200 {submitted_count, total_students, top_pending_verification:[]}

- `submitted_count`：给定 task_id 时 = 该任务提交数；未给时 = 课程全部任务提交数
- `total_students`：课程成员数（course_members 行数，UNIQUE 保证 = 学生数）
- `top_pending_verification`：MVP 返回 `[]`（errata E-29：reports 表无结构化
  "待核实项"字段，summary_text 是 markdown 拼接无法可靠提取；S5 需要时
  S2-10 报告生成时提取存入 reports 新列）

403/404 分层（errata E-16）：课程不可读 → 404；非课程教师 → 403。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import can_read_course, get_current_user, is_course_teacher
from app.core.database import get_db
from app.models.course import Course, CourseMember
from app.models.task import Task, TaskSubmission
from app.models.user import User
from app.schemas.feedback import CourseSummaryOut

router = APIRouter(prefix="/api/courses", tags=["teacher"])

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在或无权访问"
)
_FORBIDDEN = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail="仅课程教师可操作"
)


@router.get("/{course_id}/summary", response_model=CourseSummaryOut)
def course_summary(
    course_id: int,
    task_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
) -> CourseSummaryOut:
    """班级汇总统计（教师）。

    E-16 分层：① 课程不可读 → 404；② 非课程教师 → 403。
    """
    course = db.get(Course, course_id)
    if course is None or not can_read_course(db, me, course):
        raise _NOT_FOUND
    if not is_course_teacher(db, me, course):
        raise _FORBIDDEN

    # total_students：course_members 行数（UNIQUE(course_id,user_id) → = 学生数）
    total_students = db.scalar(
        select(func.count()).select_from(CourseMember).where(
            CourseMember.course_id == course.id
        )
    ) or 0

    # submitted_count：指定 task_id 时只算该任务；否则算课程全部任务
    if task_id is not None:
        # 任务须属于本课程（防止跨课程统计）
        task_ok = db.scalar(
            select(Task.id).where(Task.id == task_id, Task.course_id == course.id)
        )
        submitted_count = (
            db.scalar(
                select(func.count())
                .select_from(TaskSubmission)
                .where(TaskSubmission.task_id == task_id)
            )
            if task_ok is not None
            else 0
        ) or 0
    else:
        submitted_count = (
            db.scalar(
                select(func.count())
                .select_from(TaskSubmission)
                .join(Task, Task.id == TaskSubmission.task_id)
                .where(Task.course_id == course.id)
            )
        ) or 0

    return CourseSummaryOut(
        submitted_count=submitted_count,
        total_students=total_students,
        top_pending_verification=[],  # E-29：MVP 空数组
    )
