"""S2-1：FastAPI 鉴权依赖（permissions.md §8 授权链第一、三层）。

get_current_user：从 Cookie「access_token」取 JWT → 验签 → 查用户；
token 缺失/无效/过期/用户不存在/已停用 → 401（存在性不泄露，统一
「登录态无效或已过期」）。SSE 端点（S2-4 起）同样经本依赖——
REST/SSE 同一凭据（Cookie，方案 A）。

can_read_session（§8 第三层，S2-2 落地）：会话读权限的资源级判定函数
（E-2 风格），失败由调用方映射 404（存在性隐藏）。require_role（第二层）
按 §8 蓝图留给 S3 教师端。
"""
from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import InvalidToken, decode_access_token
from app.models.course import Course
from app.models.session import TrainingSession
from app.models.task import Task
from app.models.user import User, UserRole

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="登录态无效或已过期",
)


def get_current_user(
    db: Session = Depends(get_db),
    token: str | None = Cookie(default=None, alias="access_token"),
) -> User:
    """解析 Cookie 中的 JWT 并返回当前用户；任何凭据问题抛 401。"""
    if not token:
        raise _UNAUTHORIZED
    try:
        user_id = decode_access_token(token)
    except InvalidToken:
        raise _UNAUTHORIZED
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _UNAUTHORIZED
    return user


def list_user_roles(db: Session, user_id: int) -> list[str]:
    """用户角色列表（user_roles 多角色，UNIQUE(user_id,role) 防重复授予）。

    无角色行的账号按 student 对待（permissions.md §2）；注册即授予
    student（S2-1 落地），此处为兜底。
    """
    rows = db.scalars(select(UserRole.role).where(UserRole.user_id == user_id)).all()
    return sorted(rows) if rows else ["student"]


def can_read_session(db: Session, user: User, session: TrainingSession) -> bool:
    """会话读权限（permissions §5 的 API 面，consistency_check #8 的校验路径）。

    判定优先级（errata E-15 / permissions §5.6：owner_id=本人时无论角色
    可见——教师个人训练页=教师 owner 私有会话；非 owner 才应用角色规则。
    纯澄清，不改既有语义。依据 consistency_check_2026-10-13.md:66 +
    permissions:63/64）：

    ① owner_id == user.id → True（任何角色，含 teacher/admin 的个人训练）；
    ② 非 owner 且 visibility='task'：角色含 teacher/admin 且任务所属课程的
       teacher_id == user.id → True（permissions §5.2 教师可见集合）；
    ③ 其余一律 False（private 对非 owner → 存在性隐藏 404）。

    admin 为契约预留枚举（permissions §2：首版不实现管理员功能），按与
    teacher 同一公式参与判定（用户 2026-10 裁定口径），实际因无课程归属
    自然为 False。
    """
    if session.owner_id == user.id:
        return True
    if session.visibility == "task":
        roles = set(list_user_roles(db, user.id))
        if not roles & {"teacher", "admin"}:
            return False
        if session.task_id is None:
            return False
        task = db.get(Task, session.task_id)
        if task is None:
            return False
        course = db.get(Course, task.course_id)
        if course is None:
            return False
        return course.teacher_id == user.id
    return False
