"""S1-4 验收：revisions 观点修改稿表（sfb_test）。"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Revision, TrainingSession, User


def _mk_session_with_student(session):
    u = User(username="stu1", password_hash="y" * 60)
    session.add(u)
    session.commit()
    s = TrainingSession(owner_id=u.id, topic="辩题")
    session.add(s)
    session.commit()
    return s, u


def _mk_rev(session, sid: int, uid: int, version: int, content="观点", status=None):
    kw = {}
    if status:
        kw["status"] = status
    r = Revision(session_id=sid, student_id=uid, content=content, version=version, **kw)
    session.add(r)
    session.commit()
    return r


def test_create_read_and_defaults(session):
    s, u = _mk_session_with_student(session)
    r = _mk_rev(session, s.id, u.id, version=1)
    assert r.id is not None
    assert r.status == "draft"  # server_default（E-5）
    assert r.created_at is not None
    fetched = session.query(Revision).filter_by(id=r.id).first()
    assert fetched.content == "观点"


def test_final_status_writable(session):
    s, u = _mk_session_with_student(session)
    r = _mk_rev(session, s.id, u.id, version=1, status="final")
    assert r.status == "final"  # S4 复用原观点对比依赖定稿标记


def test_unique_session_version(session):
    s, u = _mk_session_with_student(session)
    _mk_rev(session, s.id, u.id, version=1)
    dup = Revision(session_id=s.id, student_id=u.id, content="x", version=1)
    session.add(dup)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_multiple_versions_allowed(session):
    s, u = _mk_session_with_student(session)
    _mk_rev(session, s.id, u.id, version=1, content="初稿")
    _mk_rev(session, s.id, u.id, version=2, content="修改稿")
    assert session.query(Revision).filter_by(session_id=s.id).count() == 2


def test_cascade_on_session_and_user_delete(session):
    s, u = _mk_session_with_student(session)
    r1 = _mk_rev(session, s.id, u.id, version=1)
    r2 = _mk_rev(session, s.id, u.id, version=2)
    ids = [r1.id, r2.id]

    session.delete(s)
    session.commit()
    for rid in ids:
        assert session.query(Revision).filter_by(id=rid).first() is None

    # 新会话再验证 student 级联
    s2 = TrainingSession(owner_id=u.id, topic="第二个")
    session.add(s2)
    session.commit()
    r3 = _mk_rev(session, s2.id, u.id, version=1)
    session.delete(u)
    session.commit()
    assert session.query(Revision).filter_by(id=r3.id).first() is None
