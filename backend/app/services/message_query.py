"""S2-12：messages 查询共享逻辑（history 详情 + sessions messages 分页）。

抽公共函数避免代码重复——将来加 status 过滤等改动时，两个端点自动同步。
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
) -> list[Message]:
    """按 seq 升序查询会话消息。

    - after_seq 非 None 时过滤 seq > after_seq（分页用）；
    - limit 非 None 时截断（分页用）；
    - 都不传时返回全部消息（history 详情用）。

    调用方：
    - history.py get_history_detail: query_messages(db, session_id)（全量）
    - sessions.py list_messages: query_messages(db, session_id, after_seq=after_seq, limit=limit)
    """
    stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.seq.asc())
    )
    if after_seq is not None:
        stmt = stmt.where(Message.seq > after_seq)
    if limit is not None:
        stmt = stmt.limit(limit)
    return db.scalars(stmt).all()
