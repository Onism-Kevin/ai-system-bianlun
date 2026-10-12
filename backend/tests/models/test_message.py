"""S1-4 验收：messages 建表 + 方案A seq 语义 + 回放查询（sfb_test）。

errata E-1：seq 即主键、全局自增交错；会话内单调=子序列单调。
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError

from app.models import Message, TrainingSession, User


def _mk_student(session) -> User:
    u = User(username="stu1", password_hash="y" * 60)
    session.add(u)
    session.commit()
    return u


def _mk_session(session, owner_id: int, topic: str = "辩题") -> TrainingSession:
    s = TrainingSession(owner_id=owner_id, topic=topic)
    session.add(s)
    session.commit()
    return s


def _mk_msg(session, sid: int, role="assistant", agent_role="pro", content="内容"):
    m = Message(
        session_id=sid,
        role=role,
        agent_role=agent_role,
        content=content,
    )
    session.add(m)
    session.commit()
    return m


def test_seq_autoincrement_and_defaults(session):
    stu = _mk_student(session)
    s = _mk_session(session, stu.id)
    m = _mk_msg(session, s.id)
    assert m.seq is not None
    assert m.status == "streaming"  # server_default（契约 5.2 默认流式）
    assert m.agent_role == "pro"
    assert m.created_at is not None and m.updated_at is not None


def test_agent_role_null_for_user_and_system_messages(session):
    stu = _mk_student(session)
    s = _mk_session(session, stu.id)
    mu = _mk_msg(session, s.id, role="user", agent_role=None, content="学生输入")
    assert mu.agent_role is None
    # system 消息同样 NULL
    ms = _mk_msg(session, s.id, role="system", agent_role=None, content="阶段指令")
    assert ms.agent_role is None


def test_role_enum_rejects_invalid(session):
    stu = _mk_student(session)
    s = _mk_session(session, stu.id)
    m = Message(session_id=s.id, role="coach", agent_role="coach", content="x")
    session.add(m)
    # MySQL ENUM 违规 = 1265 Data truncated → DataError（不是 IntegrityError）
    with pytest.raises(DataError):
        session.commit()
    session.rollback()


def test_status_enum_rejects_invalid(session):
    stu = _mk_student(session)
    s = _mk_session(session, stu.id)
    m = _mk_msg(session, s.id)
    m.status = "generating"  # E-3 勘误后的非法值
    with pytest.raises(DataError):
        session.flush()  # UPDATE 落库即被 ENUM 拒
    session.rollback()


def test_unique_session_seq(session):
    stu = _mk_student(session)
    s = _mk_session(session, stu.id)
    m = _mk_msg(session, s.id)
    dup = Message(
        session_id=s.id, seq=m.seq, role="assistant", agent_role="con", content="撞"
    )
    session.add(dup)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_seq_interleaves_and_replay_is_monotonic_per_session(session):
    """方案 A 核心行为：两会话交错分配全局 seq，回放按 seq 升序各自单调。"""
    stu = _mk_student(session)
    sa = _mk_session(session, stu.id, topic="会话A")
    sb = _mk_session(session, stu.id, topic="会话B")
    seqs_a = []
    seqs_b = []
    for i in range(3):
        seqs_a.append(_mk_msg(session, sa.id, content=f"A{i}").seq)
        seqs_b.append(_mk_msg(session, sb.id, content=f"B{i}").seq)

    # 会话内严格递增
    assert seqs_a == sorted(seqs_a) and len(set(seqs_a)) == 3
    assert seqs_b == sorted(seqs_b) and len(set(seqs_b)) == 3
    # 全局唯一（并集恰好 6 个不同值）
    assert len(set(seqs_a) | set(seqs_b)) == 6

    # 回放（契约 5.1）：WHERE session_id=? AND seq>? ORDER BY seq
    last = seqs_a[0]
    rows = session.execute(
        text(
            "SELECT seq FROM messages WHERE session_id=:sid AND seq > :last ORDER BY seq"
        ),
        {"sid": sa.id, "last": last},
    ).scalars().all()
    assert list(rows) == seqs_a[1:]


def test_status_can_complete_and_updated_at_moves(session):
    stu = _mk_student(session)
    s = _mk_session(session, stu.id)
    m = _mk_msg(session, s.id, content="流式中")
    before = m.updated_at
    session.query(Message).filter_by(seq=m.seq).update(
        {"status": "complete", "content": "流式完"}, synchronize_session=False
    )
    session.commit()
    session.expire_all()  # expire_on_commit=False：bulk update 绕过 ORM，身份映射对象已陈旧
    row = session.query(Message).filter_by(seq=m.seq).first()
    assert row.status == "complete"
    assert row.content == "流式完"
    assert row.updated_at >= before  # 暂停续写依赖 onupdate


def test_cascade_on_session_delete(session):
    stu = _mk_student(session)
    s = _mk_session(session, stu.id)
    m1 = _mk_msg(session, s.id)
    m2 = _mk_msg(session, s.id, role="user", agent_role=None)
    sids = [m1.seq, m2.seq]

    session.delete(s)
    session.commit()
    for seq in sids:
        assert session.query(Message).filter_by(seq=seq).first() is None
