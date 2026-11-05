"""S3-1 验收：POST /api/user_roles 角色授予 + ADMIN_USERNAME 种子。

逐字对齐 docs/contracts/api.md v1.2 :28（用户 2026-11-03 裁定 1，漏收补登）
与 permissions §4（admin | user_roles | grant）。

覆盖（用户 S3-1 验收要点 4）：
- 401 未登录
- 403 非 admin（student 与 teacher 都拒）
- 404 user 不存在
- 409 重复授予（IntegrityError 1062，不先查后插）
- 422 role 非法（student 不在 Literal 内）
- 201 正常授予（teacher / admin 含 admin 自授 teacher，多角色并存）
- admin 种子：ADMIN_USERNAME 指定的用户名注册时自动获得 admin
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.api.auth as auth_mod
from app.core.config import get_settings
from app.core.security import hash_password
from app.models.user import User, UserRole

PASSWORD = "Passw0rd!"
ADMIN_USER = "root_admin"


def _mk_user(session: Session, username: str, roles=("student",)) -> User:
    user = User(username=username, password_hash=hash_password(PASSWORD), is_active=True)
    session.add(user)
    session.flush()
    for role in roles:
        session.add(UserRole(user_id=user.id, role=role))
    session.commit()
    return user


def _login(client: TestClient, username: str) -> None:
    r = client.post(
        "/api/auth/login", json={"username": username, "password": PASSWORD}
    )
    assert r.status_code == 200, r.text


def _grant(client: TestClient, user_id: int, role: str):
    return client.post("/api/user_roles", json={"user_id": user_id, "role": role})


def _settings_with_admin(username: str):
    """构造 admin_username 指定值的 Settings（不影响进程内 lru_cache）。"""
    return get_settings().model_copy(update={"admin_username": username})


@pytest.fixture()
def admin_client(client: TestClient, session: Session) -> TestClient:
    """登录为 admin 的 client（同一 cookie jar）。"""
    _mk_user(session, ADMIN_USER, roles=("student", "admin"))
    _login(client, ADMIN_USER)
    return client


# ---------------- 错误码 ----------------


def test_grant_without_cookie_returns_401(client: TestClient, session: Session) -> None:
    """401：未登录（get_current_user 先于 require_role）。"""
    target = _mk_user(session, "noauth_target")
    assert _grant(client, target.id, "teacher").status_code == 401


def test_student_grant_returns_403(client: TestClient, session: Session) -> None:
    """403：普通 student 授予 → 动作不符（permissions §3），非 404。"""
    _mk_user(session, "plain_student")
    _login(client, "plain_student")
    target = _mk_user(session, "target_for_student")
    assert _grant(client, target.id, "teacher").status_code == 403


def test_teacher_grant_returns_403(client: TestClient, session: Session) -> None:
    """403：teacher 只读本人角色行（§4 :49），不得授予他人。"""
    _mk_user(session, "teacher_only", roles=("student", "teacher"))
    _login(client, "teacher_only")
    target = _mk_user(session, "target_for_teacher")
    assert _grant(client, target.id, "teacher").status_code == 403


def test_grant_unknown_user_returns_404(admin_client: TestClient) -> None:
    """404：目标用户不存在（admin 门槛已过，存在性明确 → 404）。"""
    assert _grant(admin_client, 999_999, "teacher").status_code == 404


def test_grant_invalid_role_returns_422(admin_client: TestClient, session: Session) -> None:
    """422：role=student 不在 Literal{teacher,admin} 内（Pydantic 校验）。"""
    target = _mk_user(session, "target_422")
    assert _grant(admin_client, target.id, "student").status_code == 422


def test_grant_duplicate_role_returns_409(
    admin_client: TestClient, session: Session
) -> None:
    """409：UNIQUE(user_id, role) 冲突 → IntegrityError(1062) 捕获。

    并发安全：端点不先查后插（用户 S3-1 验收要点 3）。
    """
    u = _mk_user(session, "dup_target", roles=("student", "teacher"))
    assert _grant(admin_client, u.id, "teacher").status_code == 409


# ---------------- 正常授予 ----------------


def test_admin_grants_teacher(admin_client: TestClient, session: Session) -> None:
    """201：admin 授予 teacher，出参 {user_id, role, granted_at}。"""
    u = _mk_user(session, "grant_teacher_target")
    r = _grant(admin_client, u.id, "teacher")
    assert r.status_code == 201
    body = r.json()
    assert body["user_id"] == u.id
    assert body["role"] == "teacher"
    assert body["granted_at"], "granted_at 必须有值（user_roles.created_at）"


def test_admin_grants_admin_role(admin_client: TestClient, session: Session) -> None:
    """201：admin 可授予 admin 角色（多角色并存，UNIQUE(user_id, role)）。"""
    u = _mk_user(session, "grant_admin_target")
    assert _grant(admin_client, u.id, "admin").status_code == 201


def test_admin_grants_teacher_to_self(admin_client: TestClient) -> None:
    """201：admin 给自己授予 teacher 允许（多角色并存，§2）。"""
    me = admin_client.get("/api/auth/me").json()["user"]
    assert _grant(admin_client, me["id"], "teacher").status_code == 201
    roles = admin_client.get("/api/auth/me").json()["roles"]
    assert roles == ["admin", "student", "teacher"]


# ---------------- admin 种子（裁定 2）----------------


def test_register_admin_seed_grants_admin(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADMIN_USERNAME 指定的用户名注册时自动获得 admin（先 student 后 admin）。"""
    monkeypatch.setattr(auth_mod, "get_settings", lambda: _settings_with_admin("seed_boss"))
    r = client.post(
        "/api/auth/register", json={"username": "seed_boss", "password": PASSWORD}
    )
    assert r.status_code == 201, r.text
    assert r.json()["roles"] == ["admin", "student"]


def test_register_normal_user_only_student(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADMIN_USERNAME 之外的用户名注册只授予 student（默认角色）。"""
    monkeypatch.setattr(auth_mod, "get_settings", lambda: _settings_with_admin("someone_else"))
    r = client.post(
        "/api/auth/register", json={"username": "normal_u", "password": PASSWORD}
    )
    assert r.status_code == 201, r.text
    assert r.json()["roles"] == ["student"]
