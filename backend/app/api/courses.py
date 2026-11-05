"""S3-2：课程创建 + 成员 API（api.md:54-59，逐字对齐）。

端点（6 个）：
- POST /api/courses          建课（仅 teacher）→ 201 {id, name, invite_code, …}
- GET  /api/courses          列表（teacher→本人教的；student→已加入的）
- GET  /api/courses/{id}     详情（invite_code 仅课程教师可见）
- PATCH /api/courses/{id}    改课（课程教师；归档替代删除）
- GET  /api/courses/{id}/members  成员列表（仅学生行）
- POST /api/courses/join     加入（invite_code；错码 403，幂等）

403/404 分层（errata E-16，2026-11-05 补登）：
资源级写动作先判**可读性**（不可读 → 404 存在性隐藏），再判**动作/归属**
（可读但不符 → 403）。例外：全局角色门槛（POST 建课的 teacher）直接 403。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, list_user_roles, require_role
from app.core.codes import CODE_MAX_ATTEMPTS, generate_code, is_duplicate_key
from app.core.database import get_db
from app.models.course import Course, CourseMember
from app.models.user import User
from app.schemas.course import (
    CourseCreate,
    CourseJoinRequest,
    CourseJoinResponse,
    CourseMemberOut,
    CourseOut,
    CourseUpdate,
    CourseWithCodeOut,
)

router = APIRouter(prefix="/api/courses", tags=["courses"])

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在或无权访问"
)
_FORBIDDEN = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail="仅课程教师可操作"
)


# ---- 资源级判定 helper（E-16 分层的第一层）----


def _has_teacher_role(db: Session, user: User) -> bool:
    """全局 teacher 角色（permissions §4 courses 行的 role 列）。"""
    return "teacher" in set(list_user_roles(db, user.id))


def _is_course_owner(course: Course, user: User) -> bool:
    """courses.teacher_id = 本人（E-15 同款 owner 优先级：不要求角色行）。"""
    return course.teacher_id == user.id


def _can_read_course(db: Session, user: User, course: Course) -> bool:
    """课程可读性：本人是教师（teacher_id）或本人在 course_members 中。

    未列出的 角色×资源×动作 组合一律 404（permissions §4 兜底），
    故非教师且非成员 → False → 404。
    """
    if _is_course_owner(course, user):
        return True
    return (
        db.scalar(
            select(CourseMember.id).where(
                CourseMember.course_id == course.id,
                CourseMember.user_id == user.id,
            )
        )
        is not None
    )


def _is_course_teacher(db: Session, user: User, course: Course) -> bool:
    """课程教师（写动作门槛）：teacher_id = 本人 **且** 具 teacher 角色。"""
    return _is_course_owner(course, user) and _has_teacher_role(db, user)


# ---- POST /api/courses ----


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CourseWithCodeOut,
)
def create_course(
    body: CourseCreate,
    db: Session = Depends(get_db),
    me: User = Depends(require_role("teacher")),
) -> CourseWithCodeOut:
    """建课：teacher 角色门槛（403 非 teacher）→ 生成 invite_code → 201。"""
    for _ in range(CODE_MAX_ATTEMPTS):
        course = Course(
            teacher_id=me.id,
            name=body.name,
            description=body.description,
            term=body.term,
            invite_code=generate_code(),
        )
        db.add(course)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            # 只重试 invite_code 唯一键冲突；其他约束（如 FK）不应静默吞掉
            if is_duplicate_key(exc, "invite_code"):
                continue
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="课程创建冲突"
            )
        db.refresh(course)
        return CourseWithCodeOut.model_validate(course)
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail="加入码生成冲突，请重试"
    )


# ---- GET /api/courses（双视角）----


@router.get("", response_model=list[CourseOut])
def list_courses(
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
) -> list[CourseOut]:
    """课程列表：teacher→本人教的；student→已加入的（union，去重）。

    列表一律不含 invite_code（加入码由单课详情端点提供）。
    """
    result: list[Course] = []
    seen: set[int] = set()
    if _has_teacher_role(db, me):
        for c in db.scalars(
            select(Course).where(Course.teacher_id == me.id).order_by(Course.id)
        ).all():
            result.append(c)
            seen.add(c.id)
    # 学生视角：course_members 含本人的课程（members 表只有学生行，故无重叠）
    for c in db.scalars(
        select(Course)
        .join(CourseMember, CourseMember.course_id == Course.id)
        .where(CourseMember.user_id == me.id)
        .order_by(Course.id)
    ).all():
        if c.id not in seen:
            result.append(c)
            seen.add(c.id)
    return [CourseOut.model_validate(c) for c in result]


# ---- POST /api/courses/join（先注册，避免与 /{course_id} 混淆）----


@router.post("/join", response_model=CourseJoinResponse)
def join_course(
    body: CourseJoinRequest,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
) -> CourseJoinResponse:
    """加入课程：invite_code 校验；错码 403（E-12，不暴露存在性）；幂等。"""
    course = db.scalar(select(Course).where(Course.invite_code == body.invite_code))
    if course is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="加入码无效")

    existing = db.scalar(
        select(CourseMember.id).where(
            CourseMember.course_id == course.id, CourseMember.user_id == me.id
        )
    )
    if existing is None:
        db.add(CourseMember(course_id=course.id, user_id=me.id))
        try:
            db.commit()
        except IntegrityError:
            # 并发重复加入 → UNIQUE(course_id,user_id) 撞 → 幂等仍 200
            db.rollback()
    return CourseJoinResponse(course_id=course.id)


# ---- GET /api/courses/{id}（invite_code 可见性按角色区分）----


@router.get("/{course_id}")
def get_course(
    course_id: int,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """课程详情。

    不声明 response_model：课程教师返回 `CourseWithCodeOut`（含 invite_code），
    其余返回 `CourseOut`（**无 invite_code 字段**，键完全缺席）——
    FastAPI 对无 response_model 的返回值直接 jsonable_encoder，不补字段。
    """
    course = db.get(Course, course_id)
    if course is None or not _can_read_course(db, me, course):
        raise _NOT_FOUND
    if _is_course_owner(course, me):
        return CourseWithCodeOut.model_validate(course)
    return CourseOut.model_validate(course)


# ---- PATCH /api/courses/{id} ----


@router.patch("/{course_id}", response_model=CourseWithCodeOut)
def update_course(
    course_id: int,
    body: CourseUpdate,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
) -> CourseWithCodeOut:
    """改课（课程教师；含归档 is_archived，MVP 无删除端点）。

    E-16 分层：① `_can_read_course` 不过 → 404；② 非课程教师 → 403。
    """
    course = db.get(Course, course_id)
    if course is None or not _can_read_course(db, me, course):
        raise _NOT_FOUND
    if not _is_course_teacher(db, me, course):
        raise _FORBIDDEN
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(course, field, value)
    db.commit()
    db.refresh(course)
    return CourseWithCodeOut.model_validate(course)


# ---- GET /api/courses/{id}/members ----


@router.get("/{course_id}/members", response_model=list[CourseMemberOut])
def list_course_members(
    course_id: int,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
) -> list[CourseMemberOut]:
    """成员列表（仅学生行；course_members 无教师行，schema_v1 §4.2）。

    E-16 分层：① 可读性不过 → 404；② 非课程教师 → 403。
    """
    course = db.get(Course, course_id)
    if course is None or not _can_read_course(db, me, course):
        raise _NOT_FOUND
    if not _is_course_teacher(db, me, course):
        raise _FORBIDDEN
    rows = db.execute(
        select(CourseMember.user_id, User.username, CourseMember.joined_at)
        .join(User, User.id == CourseMember.user_id)
        .where(CourseMember.course_id == course.id)
        .order_by(CourseMember.joined_at)
    ).all()
    return [
        CourseMemberOut(user_id=r[0], username=r[1], joined_at=r[2]) for r in rows
    ]
