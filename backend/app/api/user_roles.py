"""S3-1：角色授予 API（POST /api/user_roles）。

逐字对齐 docs/contracts/api.md v1.2 :28（用户 2026-11-03 裁定 1，漏收补登，非取代）：
- 入参 {user_id, role}，role ∈ {teacher, admin}
  （student 是注册默认角色，不需要 admin 授予）
- 201 {user_id, role, granted_at}
- 401 未登录；403 非 admin；404 user 不存在；
  409 已有该角色（UNIQUE(user_id, role)，E-5 同款）；422 role 非法

权限依据 permissions §4：admin | user_roles | grant（仅 admin 可授予
teacher/admin；teacher/student 只读本人角色行，见 §4 :49-50）。

并发安全（用户 S3-1 验收要点 3）：不"先查后插"，直接 INSERT，
靠 IntegrityError(1062) 捕获重复授予 → 409。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.models.audit import AuditEvent
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/user_roles", tags=["user_roles"])

logger = logging.getLogger(__name__)


class RoleGrantRequest(BaseModel):
    """入参：{user_id, role}。role 只接受 teacher/admin（api.md:28）。

    student 不在枚举内——注册即自动授予，无需 admin 介入（permissions §2）。
    Pydantic Literal 校验失败 → 422。
    """

    user_id: int = Field(gt=0)
    role: Literal["teacher", "admin"]


class RoleGrantResponse(BaseModel):
    """出参：201 {user_id, role, granted_at}（granted_at = user_roles.created_at）。"""

    user_id: int
    role: str
    granted_at: datetime


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=RoleGrantResponse,
)
def grant_role(
    body: RoleGrantRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role("admin")),
) -> RoleGrantResponse:
    """授予 teacher/admin 角色（仅 admin；UNIQUE(user_id, role) 防重复授予）。

    actor 未使用：保留形参显式表达"本端点需 admin 门槛"（permissions §8 第二层）。
    """
    # 404：目标用户不存在（存在性隐藏只针对越权，这里目标明确，直接 404）
    target = db.get(User, body.user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    row = UserRole(user_id=body.user_id, role=body.role)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # UNIQUE(user_id, role) 冲突（1062）→ 409；不先查后插，保证并发安全
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="该用户已拥有此角色"
        )
    db.refresh(row)  # 取服务端生成的 created_at
    # S3-6：audit 旁路记录（role.grant）。detail 记"谁给谁授予了什么角色"——
    # 审计的核心信息。audit 失败**不影响授予**（用户 2026-11-07 拍板）。
    try:
        db.add(
            AuditEvent(
                actor_id=actor.id,
                action="role.grant",
                target_type="user",
                target_id=body.user_id,
                detail={"role": body.role, "target_user_id": body.user_id},
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("audit 写入失败，不影响角色授予", exc_info=True)
    return RoleGrantResponse(
        user_id=body.user_id, role=body.role, granted_at=row.created_at
    )
