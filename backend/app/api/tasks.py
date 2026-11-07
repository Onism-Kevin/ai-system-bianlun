"""S3-3：任务创建 + 加入码 + join API（api.md:60-64，逐字对齐）。

端点（5 个）：
- POST /api/courses/{course_id}/tasks   建任务（课程教师；need_join_code 生成码）
- GET  /api/courses/{course_id}/tasks   列表（教师→本人课程；学生→成员课程）
- GET  /api/tasks/{id}                  详情（join_code 仅课程教师可见）
- PATCH /api/tasks/{id}                 改任务（课程教师；含 deadline/is_archived）
- POST /api/tasks/{id}/join             加入（join_code；错码 403；已过期 410）

403/404 分层（errata E-16）：资源级端点先判可读（不可读 → 404），
再判动作/归属（可读但不符 → 403）。任务写动作的门槛是"课程教师"。

join 语义（§9 Q1 已决 + 计划书 S3-3 备注）：join_code 仅作**入组校验**，
加入的是 `course_members`（course_id 行），任务读取权限 = 课程成员为主路径。
**不建 task_members 表**——教师看"哪些学生已加入未提交"由 S3-4 的
submissions 端点承担，届时若确需持久任务成员记录再提 schema 增量。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import (
    can_read_course,
    can_read_task,
    get_current_user,
    is_course_teacher,
    is_task_teacher,
)
from app.core.codes import CODE_MAX_ATTEMPTS, generate_code, is_duplicate_key
from app.core.database import get_db
from app.models.course import Course, CourseMember
from app.models.task import Task
from app.models.user import User
from app.schemas.task import (
    TaskCreate,
    TaskJoinRequest,
    TaskJoinResponse,
    TaskOut,
    TaskUpdate,
    TaskWithCodeOut,
)

router = APIRouter(prefix="/api", tags=["tasks"])

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在或无权访问"
)
_FORBIDDEN = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail="仅课程教师可操作"
)


# ---- POST /api/courses/{course_id}/tasks ----


@router.post(
    "/courses/{course_id}/tasks",
    status_code=status.HTTP_201_CREATED,
    response_model=TaskWithCodeOut,
)
def create_task(
    course_id: int,
    body: TaskCreate,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
) -> TaskWithCodeOut:
    """建任务：E-16 分层——课程不可读 → 404；可读但非课程教师 → 403。"""
    course = db.get(Course, course_id)
    if course is None or not can_read_course(db, me, course):
        raise _NOT_FOUND
    if not is_course_teacher(db, me, course):
        raise _FORBIDDEN

    # need_join_code 时生成加入码（String(8)，同课程邀请码规则）；
    # 唯一键冲突（UNIQUE join_code）重试，不先查后插。
    for _ in range(CODE_MAX_ATTEMPTS):
        join_code = generate_code() if body.need_join_code else None
        task = Task(
            course_id=course_id,
            title=body.title,
            material=body.material,
            deadline=body.deadline,
            join_code=join_code,
        )
        db.add(task)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            if is_duplicate_key(exc, "join_code"):
                continue
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="任务创建冲突"
            )
        db.refresh(task)
        return TaskWithCodeOut.model_validate(task)
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail="加入码生成冲突，请重试"
    )


# ---- GET /api/courses/{course_id}/tasks ----


@router.get("/courses/{course_id}/tasks", response_model=list[TaskOut])
def list_course_tasks(
    course_id: int,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
) -> list[TaskOut]:
    """任务列表：教师→本人课程任务；学生→成员课程任务（均不含 join_code）。

    列表排除已归档任务（归档=关闭，教师仍可在详情/patch 中操作）。
    """
    course = db.get(Course, course_id)
    if course is None or not can_read_course(db, me, course):
        raise _NOT_FOUND
    tasks = db.scalars(
        select(Task)
        .where(Task.course_id == course_id, Task.is_archived.is_(False))
        .order_by(Task.id)
    ).all()
    return [TaskOut.model_validate(t) for t in tasks]


# ---- POST /api/tasks/{id}/join（先注册，避免与 /{task_id} 混淆）----


@router.post("/tasks/{task_id}/join", response_model=TaskJoinResponse)
def join_task(
    task_id: int,
    body: TaskJoinRequest,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
) -> TaskJoinResponse:
    """加入任务：join_code 校验 → 错码 403（E-12，不暴露存在性）；过期 410。

    顺序：任务存在性（404）→ 加入码匹配（403）→ 过期（410）→ 入组（幂等 200）。
    先比码再查过期，避免向错码请求泄露过期信息。
    """
    task = db.get(Task, task_id)
    if task is None:
        raise _NOT_FOUND
    # 任务无加入码（need_join_code=False）或码不匹配 → 403（同错码语义）
    if task.join_code is None or task.join_code != body.join_code:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="加入码无效")
    if task.deadline is not None and task.deadline < datetime.now():
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="任务已过期")

    # 入组 = 加入 course_members（§9 Q1：任务读取权限 = 课程成员为主路径）
    existing = db.scalar(
        select(CourseMember.id).where(
            CourseMember.course_id == task.course_id, CourseMember.user_id == me.id
        )
    )
    if existing is None:
        db.add(CourseMember(course_id=task.course_id, user_id=me.id))
        try:
            db.commit()
        except IntegrityError:
            # 并发重复加入 → UNIQUE(course_id,user_id) 撞 → 幂等仍 200
            db.rollback()
    return TaskJoinResponse(course_id=task.course_id, task_id=task.id)


# ---- GET /api/tasks/{id}（join_code 可见性按角色区分）----


@router.get("/tasks/{task_id}")
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """任务详情。

    不声明 response_model：课程教师返回 `TaskWithCodeOut`（含 join_code），
    其余返回 `TaskOut`（**无 join_code 字段**，键完全缺席）。
    """
    task = db.get(Task, task_id)
    if task is None or not can_read_task(db, me, task):
        raise _NOT_FOUND
    if is_task_teacher(db, me, task):
        return TaskWithCodeOut.model_validate(task)
    return TaskOut.model_validate(task)


# ---- PATCH /api/tasks/{id} ----


@router.patch("/tasks/{task_id}", response_model=TaskWithCodeOut)
def update_task(
    task_id: int,
    body: TaskUpdate,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
) -> TaskWithCodeOut:
    """改任务（课程教师；含 deadline/is_archived，删除走归档 E-8）。

    E-16 分层：① can_read_task 不过 → 404；② 非课程教师 → 403。
    """
    task = db.get(Task, task_id)
    if task is None or not can_read_task(db, me, task):
        raise _NOT_FOUND
    if not is_task_teacher(db, me, task):
        raise _FORBIDDEN
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    return TaskWithCodeOut.model_validate(task)
