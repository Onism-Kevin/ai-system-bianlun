"""S2-12：训练历史列表 + 详情回放 API（api.md:40-41）。

GET /api/history — owner 视角会话列表（按 updated_at DESC 排序）
GET /api/history/{session_id} — 会话详情 + 完整消息流（按 seq 升序）

与 GET /api/sessions/{id}/messages 的差异：
- messages 端点：分页 API（after_seq + limit），返回 {messages, next_seq}，
  供训练页实时拉消息
- history 详情：完整重建视图（无分页），返回 {session, messages}，
  供历史页查看完整消息流

共享查询逻辑：都是 SELECT FROM messages WHERE session_id=? ORDER BY seq ASC。
差异在响应格式（分页 vs 全量）和包装（含 session vs 不含）。

streaming 消息：history 详情包含全部消息（含 streaming）。api.md:41 写
"详情完整重建消息流"——不是"回放终态"。前端 S2-F8 按 status 字段渲染。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import can_read_session, get_current_user
from app.core.database import get_db
from app.models.message import Message
from app.models.session import TrainingSession
from app.models.user import User
from app.schemas.history import HistoryDetailOut, HistoryItem
from app.schemas.message import MessageOut
from app.schemas.session import SessionOut

router = APIRouter(prefix="/api", tags=["history"])

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="资源不存在或无权访问",
)


@router.get("/history")
def list_history(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[HistoryItem]:
    """训练历史列表（api.md:40）。

    owner 视角：只返回 owner_id = user.id 的会话。每个会话自动可见。
    排序：updated_at DESC（最近更新的排前面）。
    """
    sessions = db.scalars(
        select(TrainingSession)
        .where(TrainingSession.owner_id == user.id)
        .order_by(TrainingSession.updated_at.desc())
    ).all()

    return [
        HistoryItem(
            id=s.id,
            topic=s.topic,
            status=s.status,
            created_at=s.created_at.isoformat() if s.created_at else "",
            updated_at=s.updated_at.isoformat() if s.updated_at else "",
        )
        for s in sessions
    ]


@router.get("/history/{session_id}")
def get_history_detail(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HistoryDetailOut:
    """训练历史详情（api.md:41）。

    返回 {session, messages:[按 seq 升序]}。包含全部消息（含 streaming）。
    权限：can_read_session（owner 或 teacher-visible task 会话）。
    """
    session = db.get(TrainingSession, session_id)
    if session is None or not can_read_session(db, user, session):
        raise _NOT_FOUND

    # 完整重建消息流：全部消息按 seq 升序
    messages = db.scalars(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.seq.asc())
    ).all()

    return HistoryDetailOut(
        session=SessionOut.model_validate(session).model_dump(),
        messages=[
            MessageOut.model_validate(m).model_dump()
            for m in messages
        ],
    )
