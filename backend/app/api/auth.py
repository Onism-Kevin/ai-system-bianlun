"""S2-1：auth 三端点（register / login / me）。

逐字对齐 docs/contracts/api.md v1.2：
- POST /api/auth/register  入参 {username, password} → 201 {id, username, roles[]}
                            409 用户名重名；422 入参校验
- POST /api/auth/login     入参 {username, password} → 200 {user} + Set-Cookie
                            （httpOnly + SameSite=Lax + path=/ + max_age=jwt 有效期，
                            详见 permissions.md §6.3；secure=False 仅 dev）
                            401 凭据错误（用户名不存在/密码错/账号停用，统一不外泄区别）
- GET  /api/auth/me        仅 Cookie → 200 {user, roles[]}；401 未登录/登录态无效

密码不记日志、不回显、不进 commit；所有错误体统一 {"detail": "..."}（api.md §3）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, list_user_roles
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User, UserRole
from app.schemas.auth import (
    AuthUser,
    LoginRequest,
    LoginResponse,
    MeResponse,
    RegisterRequest,
    RegisterResponse,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Cookie 名（permissions §6.3）：REST 与 SSE（S2-4 起）同一凭据
COOKIE_NAME = "access_token"


def _to_auth_user(user: User) -> AuthUser:
    """公开用户信息（不含 password_hash）。"""
    return AuthUser(id=user.id, username=user.username, display_name=user.display_name)


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=RegisterResponse,
)
def register(
    body: RegisterRequest,
    db: Session = Depends(get_db),
) -> RegisterResponse:
    """注册：建 users 行 + 默认授予 student 角色（permissions §2）。

    409 重名先查一遍（语义清晰），并发撞 UNIQUE(username) 再兜底一次。
    """
    existing = db.scalar(select(User.id).where(User.username == body.username))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="用户名已被占用"
        )
    user = User(username=body.username, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()  # 先拿 user.id，再插角色行
    db.add(UserRole(user_id=user.id, role="student"))
    try:
        db.commit()
    except IntegrityError:
        # 并发重名（UNIQUE(username)）或角色行撞唯一键：回滚后按 409 处理
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="用户名已被占用"
        )
    return RegisterResponse(id=user.id, username=user.username, roles=["student"])


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    """登录：验凭据 → 签发 JWT → 写 httpOnly Cookie（SameSite=Lax，dev 不 secure）。"""
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="账号已停用"
        )

    token = create_access_token(user.id)
    settings = get_settings()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,  # 仅 dev；HTTPS 部署改 True（permissions §6.3）
        path="/",
        max_age=settings.jwt_expire_days * 24 * 60 * 60,
    )
    return LoginResponse(user=_to_auth_user(user))


@router.get("/me", response_model=MeResponse)
def me(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MeResponse:
    """当前登录态：返回用户信息与角色列表（凭据 = Cookie）。"""
    return MeResponse(user=_to_auth_user(user), roles=list_user_roles(db, user.id))
