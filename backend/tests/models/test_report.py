"""S1-4 验收：reports 复盘报告表（sfb_test）。

E-5：无 UNIQUE(session_id)——同会话允许多份报告（重跑取最新）。
"""
from __future__ import annotations

from decimal import Decimal

from app.models import Report, TrainingSession, User


def _mk_session(session):
    u = User(username="stu1", password_hash="y" * 60)
    session.add(u)
    session.commit()
    s = TrainingSession(owner_id=u.id, topic="辩题")
    session.add(s)
    session.commit()
    return s


def _mk_report(session, sid: int, overall="78.50"):
    r = Report(
        session_id=sid,
        rubric_version="v1",
        scores={"论证完整性": 80, "反驳质量": 75, "表达清晰度": 82},
        overall_score=Decimal(overall),
        summary_text="整体表现良好。",
    )
    session.add(r)
    session.commit()
    return r


def test_create_read_and_types(session):
    s = _mk_session(session)
    r = _mk_report(session, s.id)
    assert r.id is not None
    assert r.created_at is not None

    fetched = session.query(Report).filter_by(id=r.id).first()
    assert fetched.scores["论证完整性"] == 80  # JSON 往返
    assert fetched.overall_score == Decimal("78.50")
    assert fetched.rubric_version == "v1"  # 量表快照标识


def test_multiple_reports_per_session_allowed(session):
    """E-5：允许重跑复盘，同一会话两行共存，created_at 最新者为当前版。"""
    s = _mk_session(session)
    r1 = _mk_report(session, s.id, overall="60.00")
    r2 = _mk_report(session, s.id, overall="85.00")
    assert r2.id != r1.id
    assert session.query(Report).filter_by(session_id=s.id).count() == 2


def test_scores_json_flexible(session):
    """维度不锁死：任意键组合可存。"""
    s = _mk_session(session)
    r = Report(
        session_id=s.id,
        rubric_version="v2-beta",
        scores={"自定义维度A": 10, "B": {"子项": 2}},
        overall_score=Decimal("50.00"),
        summary_text="x",
    )
    session.add(r)
    session.commit()
    fetched = session.query(Report).filter_by(id=r.id).first()
    assert fetched.scores["B"]["子项"] == 2


def test_cascade_on_session_delete(session):
    s = _mk_session(session)
    r = _mk_report(session, s.id)
    rid = r.id
    session.delete(s)
    session.commit()
    assert session.query(Report).filter_by(id=rid).first() is None
