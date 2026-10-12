"""S1-2 验收：users / user_roles 建表 + CRUD 冒烟（sfb_test）。"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import User, UserRole


def _new_user(username: str = "alice", **kw) -> User:
    return User(username=username, password_hash="x" * 60, **kw)


def test_user_create_read_update_delete(session):
    # CREATE
    u = _new_user(display_name="爱丽丝")
    session.add(u)
    session.commit()
    assert u.id is not None
    assert u.is_active is True  # server_default 1
    assert u.created_at is not None

    # READ
    fetched = session.get(User, u.id)
    assert fetched.username == "alice"
    assert fetched.display_name == "爱丽丝"

    # UPDATE（display_name 可空、可改）
    fetched.display_name = "Alice A."
    session.commit()
    session.refresh(fetched)
    assert fetched.display_name == "Alice A."

    # DELETE
    session.delete(fetched)
    session.commit()
    assert session.get(User, u.id) is None


def test_username_unique(session):
    session.add(_new_user("bob"))
    session.commit()
    session.add(_new_user("bob"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_multi_role_and_duplicate_role(session):
    u = _new_user()
    session.add(u)
    session.flush()
    # 同账号多角色允许（student + teacher）
    session.add(UserRole(user_id=u.id, role="student"))
    session.add(UserRole(user_id=u.id, role="teacher"))
    session.commit()
    roles = {r.role for r in session.query(UserRole).filter_by(user_id=u.id)}
    assert roles == {"student", "teacher"}

    # 同角色重复授予被拒
    session.add(UserRole(user_id=u.id, role="student"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_admin_enum_placeholder(session):
    """'admin' 为契约预留枚举值，可正常写入（不代表实现管理员功能）。"""
    u = _new_user()
    session.add(u)
    session.flush()
    session.add(UserRole(user_id=u.id, role="admin"))
    session.commit()
    assert session.query(UserRole).filter_by(user_id=u.id, role="admin").count() == 1


def test_role_cascade_on_user_delete(session):
    u = _new_user()
    session.add(u)
    session.flush()
    session.add(UserRole(user_id=u.id, role="student"))
    session.commit()
    uid = u.id

    session.delete(u)
    session.commit()
    assert session.query(UserRole).filter_by(user_id=uid).count() == 0


def test_is_active_server_default_and_off(session):
    u = _new_user(is_active=False)
    session.add(u)
    session.commit()
    session.refresh(u)
    assert u.is_active is False
