"""S1-4 验收：audit_events 审计留痕表（sfb_test）。

关键：actor_id ON DELETE SET NULL——删账号后事件保留（断链人、保事件）。
"""
from __future__ import annotations

from sqlalchemy import inspect, text

from app.models import AuditEvent, User


def test_create_read_and_ip(session):
    u = User(username="teacher1", password_hash="x" * 60)
    session.add(u)
    session.commit()
    e = AuditEvent(
        actor_id=u.id,
        action="user.login",
        target_type="user",
        target_id=u.id,
        detail={"method": "password"},
        ip="127.0.0.1",
    )
    session.add(e)
    session.commit()
    assert e.id is not None
    assert e.created_at is not None

    fetched = session.query(AuditEvent).filter_by(id=e.id).first()
    assert fetched.ip == "127.0.0.1"
    assert fetched.detail["method"] == "password"


def test_system_action_null_actor_and_optional_fields(session):
    e = AuditEvent(action="task.create", target_type="task", target_id=1)
    session.add(e)
    session.commit()
    assert e.actor_id is None  # NULL=系统动作
    assert e.detail is None
    assert e.ip is None
    assert e.target_type == "task"


def test_actor_delete_keeps_event_with_null_actor(session):
    """删账号后留痕保留、actor 断链为 NULL——审计表的核心语义。"""
    u = User(username="stu1", password_hash="y" * 60)
    session.add(u)
    session.commit()
    e1 = AuditEvent(actor_id=u.id, action="user.deactivate", target_type="user")
    e2 = AuditEvent(actor_id=u.id, action="submission.view", target_type="session")
    session.add_all([e1, e2])
    session.commit()
    ids = [e1.id, e2.id]

    session.delete(u)
    session.commit()
    session.expire_all()  # expire_on_commit=False：身份映射里的 e1/e2 仍是删除前的旧值
    for eid in ids:
        row = session.query(AuditEvent).filter_by(id=eid).first()
        assert row is not None  # 事件不删
        assert row.actor_id is None  # 人断链


def test_created_at_index_exists(session):
    """(created_at) 索引供按时间审计查询（契约 8.1 用例10）。"""
    cols = [
        ix["column_names"]
        for ix in inspect(session.bind).get_indexes("audit_events")
    ]
    assert ["created_at"] in cols


def test_ip_ipv6_length_supported(session):
    e = AuditEvent(action="user.login", ip="2001:0db8:85a3:0000:0000:8a2e:0370:7334")
    session.add(e)
    session.commit()
    assert session.query(AuditEvent).filter_by(id=e.id).first() is not None
    # 空表清理，避免影响其他用例计数
    session.execute(text("DELETE FROM audit_events"))
    session.commit()
