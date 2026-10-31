"""S2-11：观点 revisions CRUD（api.md:50-53）。

POST /api/revisions — 创建观点版本（version 自增，status 可选）
PATCH /api/revisions/{id} — 更新内容/状态（final 降级其他 final）
GET  /api/revisions?session_id= — 列表（含 diff_vs_prev，空列表 200）
GET  /api/revisions/{id} — 单条（含 diff_vs_prev）

diff 计算方式 B：GET 时用 difflib.unified_diff 实时计算，不存 DB。
version 自增：SELECT MAX(version) + INSERT 同事务，捕获 IntegrityError(1062) → 409。
status 规则：同一 session 最多一个 final；PATCH 设 final 时自动降级其他 final；
允许 final → draft（撤销定稿）。
"""
from __future__ import annotations

import difflib
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import can_read_session, get_current_user
from app.core.database import get_db
from app.models.revision import Revision
from app.models.session import TrainingSession
from app.models.user import User
from app.schemas.revision import (
    RevisionCreate,
    RevisionDetailOut,
    RevisionListItem,
    RevisionOut,
    RevisionPostResponse,
    RevisionUpdate,
)

router = APIRouter(prefix="/api", tags=["revisions"])

logger = logging.getLogger(__name__)

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="资源不存在或无权访问",
)
_FORBIDDEN = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="仅会话所有者可操作",
)
_UNPROCESSABLE = status.HTTP_422_UNPROCESSABLE_CONTENT
_CONFLICT = status.HTTP_409_CONFLICT


# ---- helpers ----


def _to_out(rev: Revision) -> RevisionOut:
    """ORM → RevisionOut（created_at ISO 字符串）。"""
    return RevisionOut(
        id=rev.id,
        version=rev.version,
        status=rev.status,
        content=rev.content,
        created_at=rev.created_at.isoformat() if rev.created_at else "",
    )


def _get_prev_content(db: Session, session_id: int, curr_version: int) -> str | None:
    """取上一版 content（version < curr_version，不假设连续）。"""
    return db.scalar(
        select(Revision.content)
        .where(
            Revision.session_id == session_id,
            Revision.version < curr_version,
        )
        .order_by(Revision.version.desc())
        .limit(1)
    )


def _compute_diff(prev_content: str | None, curr_content: str) -> str | None:
    """unified diff（首版返回 None）。"""
    if prev_content is None:
        return None
    prev_lines = prev_content.splitlines(keepends=True)
    curr_lines = curr_content.splitlines(keepends=True)
    return "".join(difflib.unified_diff(prev_lines, curr_lines))


def _demote_other_finals(db: Session, session_id: int, keep_id: int) -> None:
    """同一 session 最多一个 final：降级除 keep_id 外的其他 final。"""
    db.execute(
        update(Revision)
        .where(
            Revision.session_id == session_id,
            Revision.id != keep_id,
            Revision.status == "final",
        )
        .values(status="draft")
    )


# ---- POST /api/revisions ----


@router.post("/revisions", status_code=status.HTTP_201_CREATED)
def create_revision(
    body: RevisionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RevisionPostResponse:
    """创建观点版本（api.md:50）。

    流程：get_current_user → can_read_session（404）→ owner 校验（403）
    → version 自增 → INSERT → 捕获 IntegrityError(1062) → 409。
    """
    session = db.get(TrainingSession, body.session_id)
    if session is None or not can_read_session(db, user, session):
        raise _NOT_FOUND
    if session.owner_id != user.id:
        raise _FORBIDDEN

    # version 自增：SELECT MAX(version) + INSERT 同事务
    max_version = db.scalar(
        select(func.max(Revision.version)).where(Revision.session_id == body.session_id)
    )
    new_version = (max_version or 0) + 1

    revision = Revision(
        session_id=body.session_id,
        student_id=user.id,
        content=body.content,
        version=new_version,
        status=body.status,
    )
    db.add(revision)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=_CONFLICT,
            detail="版本冲突，请重试",
        ) from exc
    db.refresh(revision)

    # 设 final 时降级其他 final
    if body.status == "final":
        _demote_other_finals(db, body.session_id, revision.id)
        db.commit()

    return RevisionPostResponse(
        id=revision.id,
        version=revision.version,
        status=revision.status,
        diff=None,
    )


# ---- PATCH /api/revisions/{id} ----


@router.patch("/revisions/{revision_id}")
def update_revision(
    revision_id: int,
    body: RevisionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RevisionDetailOut:
    """更新观点版本（api.md:51）。

    流程：get_current_user → 查 revision + 会话 → can_read_session（404）
    → owner 校验（403）→ 更新 content/status → 设 final 降级其他 final
    → commit → 计算 diff_vs_prev → 返回。
    """
    revision = db.get(Revision, revision_id)
    if revision is None:
        raise _NOT_FOUND

    session = db.get(TrainingSession, revision.session_id)
    if session is None or not can_read_session(db, user, session):
        raise _NOT_FOUND
    if session.owner_id != user.id:
        raise _FORBIDDEN

    prev_content = revision.content

    if "content" in body.model_fields_set and body.content is not None:
        revision.content = body.content

    new_status = body.status if "status" in body.model_fields_set else revision.status
    if new_status == "final":
        # 降级同 session 其他 final（最多一个 final）
        _demote_other_finals(db, revision.session_id, revision.id)
    revision.status = new_status

    db.commit()
    db.refresh(revision)

    # 计算 diff_vs_prev：PATCH 对比"更新前同一 revision 的 content"
    # （prev_content）与"更新后的 content"——显示本次 PATCH 改了什么。
    # 与 GET 不同：GET 对比"上一版 version 的 content"与"当前 version 的
    # content"（跨版本 diff）；PATCH 对比"同 revision 旧内容"与"新内容"。
    diff = _compute_diff(prev_content, revision.content)

    return RevisionDetailOut(
        revision=_to_out(revision),
        diff_vs_prev=diff,
    )


# ---- GET /api/revisions?session_id= ----


@router.get("/revisions")
def list_revisions(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RevisionListItem]:
    """列表（api.md:52）。空列表返回 200 + []（不 404）。"""
    session = db.get(TrainingSession, session_id)
    if session is None or not can_read_session(db, user, session):
        raise _NOT_FOUND

    rows = db.scalars(
        select(Revision)
        .where(Revision.session_id == session_id)
        .order_by(Revision.version.asc())
    ).all()

    items: list[RevisionListItem] = []
    for rev in rows:
        prev = _get_prev_content(db, session_id, rev.version)
        diff = _compute_diff(prev, rev.content)
        out = _to_out(rev)
        items.append(RevisionListItem(
            id=out.id, version=out.version, status=out.status,
            content=out.content, created_at=out.created_at,
            diff_vs_prev=diff,
        ))
    return items


# ---- GET /api/revisions/{id} ----


@router.get("/revisions/{revision_id}")
def get_revision(
    revision_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RevisionDetailOut:
    """单条（api.md:53）。"""
    revision = db.get(Revision, revision_id)
    if revision is None:
        raise _NOT_FOUND

    session = db.get(TrainingSession, revision.session_id)
    if session is None or not can_read_session(db, user, session):
        raise _NOT_FOUND

    prev = _get_prev_content(db, revision.session_id, revision.version)
    diff = _compute_diff(prev, revision.content)

    return RevisionDetailOut(
        revision=_to_out(revision),
        diff_vs_prev=diff,
    )
