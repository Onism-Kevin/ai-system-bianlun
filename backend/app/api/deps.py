"""S2-1：FastAPI 鉴权依赖（permissions.md §8 授权链第一层）。

get_current_user：从 Cookie「access_token」取 JWT → 验签 → 查用户；
token 缺失/无效/过期/用户不存在/已停用 → 401（存在性不泄露，统一
「登录态无效或已过期」）。SSE 端点（S2-4 起）同样经本依赖——
REST/SSE 同一凭据（Cookie，方案 A）。

permissions §8 的 require_role 与资源级判定函数按蓝图后续任务补齐
（S3 教师端启用），本文件只交付 S2-1 需要的第一层。
"""
from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import InvalidToken, decode_access_token
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
