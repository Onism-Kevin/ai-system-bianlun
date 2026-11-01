"""S2-12：messages 查询共享逻辑（history 详情 + sessions messages 分页 + coach_turn 过滤）。

抽公共函数避免代码重复——三个端点的消息查询都走这里，将来加过滤条件时自动同步。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.message import Message


def query_messages(
    db: Session,
    session_id: int,
    *,
    after_seq: int | None = None,
    limit: int | None = None,
    role: str | None = None,
    exclude_streaming: bool = False,
) -> list[Message]:
    """按 seq 升序查询消息。

    - after_seq 非 None 时过滤 seq > after_seq（分页用）；
    - limit 非 None 时截断（分页用）；
    - role 非 None 时过滤 role（coach 用：'user'/'assistant'）；
    - exclude_streaming=True 时过滤 status != 'streaming'（coach 用）；
    - 都不传时返回全部消息（history 详情用）。

    调用方：
    - history.py get_history_detail: query_messages(db, session_id)（全量）
    - sessions.py list_messages: query_messages(db, session_id, after_seq=after_seq, limit=limit)
    - coach_turn.py coach_turn_session: query_messages(db, session_id, role="user",
      exclude_streaming=True)（全量过滤，Python 侧截取最近 N）
    """
    stmt = (
        select(Message)
        .where(Message.session_id == session_id)
    )
    if after_seq is not None:
        stmt = stmt.where(Message.seq > after_seq)
    if role is not None:
        stmt = stmt.where(Message.role == role)
    if exclude_streaming:
        stmt = stmt.where(Message.status != "streaming")
    stmt = stmt.order_by(Message.seq.asc())
    if limit is not None:
        stmt = stmt.limit(limit)
    return db.scalars(stmt).all()
