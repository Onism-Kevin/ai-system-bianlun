"""S3-6 验收：audit_events 写入（user.login + role.grant）。

覆盖：
- login 成功 → audit_events 有一行 user.login（actor/target 正确）
- register 不写 audit
- role.grant 成功 → audit_events 有一行 role.grant，detail 含
  {role, target_user_id}（谁给谁授予了什么角色）
- **audit 写入失败不影响主流程**：login 仍 200、grant 仍 201（旁路记录）
"""
from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.audit import AuditEvent
from app.models.user import User, UserRole

from tests.models.conftest import engine, session  # noqa: E402,F401

PASSWORD = "Passw0rd!"


def _mk_user(session: Session, username: str, roles=("student",)) -> User:
    user = User(username=username, password_hash="x", is_active=True)
    session.add(user)
    session.flush()
    for role in roles:
        session.add(UserRole(user_id=user.id, role=role))
    session.commit()
    return user


# ---- user.login ----


def test_register_does_not_write_audit(client: TestClient, session: Session) -> None:
    """注册不写 audit（只有 login / role.grant 写）。"""
    r = client.post(
        "/api/auth/register", json={"username": "audit_reg", "password": PASSWORD}
    )
    assert r.status_code == 201
    assert session.scalars(select(AuditEvent)).all() == []


def test_login_writes_user_login_audit(client: TestClient, session: Session) -> None:
    r = client.post(
        "/api/auth/register", json={"username": "audit_login", "password": PASSWORD}
    )
    assert r.status_code == 201
    user_id = r.json()["id"]

    r = client.post(
        "/api/auth/login", json={"username": "audit_login", "password": PASSWORD}
    )
    assert r.status_code == 200, r.text

    rows = session.scalars(select(AuditEvent)).all()
    assert len(rows) == 1
    assert rows[0].action == "user.login"
    assert rows[0].actor_id == user_id
    assert rows[0].target_type == "user"
    assert rows[0].target_id == user_id


def test_login_wrong_password_no_audit(client: TestClient, session: Session) -> None:
    """失败的登录不写 audit。"""
    client.post(
        "/api/auth/register", json={"username": "audit_bad", "password": PASSWORD}
    )
    r = client.post(
        "/api/auth/login", json={"username": "audit_bad", "password": "WrongPass1"}
    )
    assert r.status_code == 401
    assert session.scalars(select(AuditEvent)).all() == []


# ---- role.grant ----


def test_role_grant_writes_role_grant_audit(
    client: TestClient, session: Session
) -> None:
    admin = _mk_user(session, "audit_admin", roles=("student", "admin"))
    target = _mk_user(session, "audit_target")
    token = create_access_token(admin.id)

    r = client.post(
        "/api/user_roles",
        json={"user_id": target.id, "role": "teacher"},
        cookies={"access_token": token},
    )
    assert r.status_code == 201, r.text

    rows = session.scalars(select(AuditEvent)).all()
    assert len(rows) == 1
    assert rows[0].action == "role.grant"
    assert rows[0].actor_id == admin.id, "actor=授予者（admin）"
    assert rows[0].target_type == "user"
    assert rows[0].target_id == target.id
    assert rows[0].detail["role"] == "teacher"
    assert rows[0].detail["target_user_id"] == target.id


def test_role_grant_duplicate_no_extra_audit(
    client: TestClient, session: Session
) -> None:
    """重复授予 409 → 不写 audit（未成功授予）。"""
    admin = _mk_user(session, "audit_admin2", roles=("student", "admin"))
    target = _mk_user(session, "audit_target2")
    token = create_access_token(admin.id)

    # 第一次授予成功 → 1 行
    r = client.post(
        "/api/user_roles",
        json={"user_id": target.id, "role": "teacher"},
        cookies={"access_token": token},
    )
    assert r.status_code == 201
    # 第二次重复 → 409，不写 audit
    r = client.post(
        "/api/user_roles",
        json={"user_id": target.id, "role": "teacher"},
        cookies={"access_token": token},
    )
    assert r.status_code == 409
    assert len(session.scalars(select(AuditEvent)).all()) == 1


# ---- audit 失败不影响主流程 ----


def test_audit_failure_does_not_break_login(
    client: TestClient, session: Session, monkeypatch
) -> None:
    """audit 写入抛异常 → 登录仍 200（旁路记录）。"""
    import app.api.auth as auth_module

    class _Boom:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("audit boom")

    monkeypatch.setattr(auth_module, "AuditEvent", _Boom)

    r = client.post(
        "/api/auth/register", json={"username": "fail_login", "password": PASSWORD}
    )
    assert r.status_code == 201
    r = client.post(
        "/api/auth/login", json={"username": "fail_login", "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    assert session.scalars(select(AuditEvent)).all() == []


def test_audit_failure_does_not_break_grant(
    client: TestClient, session: Session, monkeypatch
) -> None:
    """audit 写入抛异常 → 授予仍 201（旁路记录）。"""
    import app.api.user_roles as ur_module

    class _Boom:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("audit boom")

    monkeypatch.setattr(ur_module, "AuditEvent", _Boom)

    admin = _mk_user(session, "fail_admin", roles=("student", "admin"))
    target = _mk_user(session, "fail_target")
    token = create_access_token(admin.id)

    r = client.post(
        "/api/user_roles",
        json={"user_id": target.id, "role": "teacher"},
        cookies={"access_token": token},
    )
    assert r.status_code == 201, r.text
    assert session.scalars(select(AuditEvent)).all() == []
