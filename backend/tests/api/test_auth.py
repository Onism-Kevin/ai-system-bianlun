"""S2-1 验收：注册→登录→me 三连（E-10：cookie jar 而非 Bearer）。

验收路径（用户任务书 + E-10 + api.md auth 三行）：
1. register → 201，响应 {id, username, roles:["student"]}
2. login → 200 {user} + Set-Cookie access_token（httpOnly + SameSite=Lax）
3. me → 200 {user, roles}，凭据即同一个 cookie jar（自动携带）
边界：重名 409；错密码 401；未知用户 401；未登录/垃圾 token/过期 token → me 401；
停用账号（正确密码）401；弱用户名/密码 422。
"""
from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.user import User, UserRole

GOOD_PASSWORD = "Passw0rd!"


def _register(client: TestClient, username: str = "alice") -> dict:
    r = client.post(
        "/api/auth/register",
        json={"username": username, "password": GOOD_PASSWORD},
    )
    assert r.status_code == 201
    return r.json()


def _login(client: TestClient, username: str, password: str):
    return client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )


def test_register_login_me_three_step(client: TestClient) -> None:
    """三连验收：注册 → 登录（写 Cookie）→ me（带 Cookie 取本人信息）。"""
    # 1) 注册：201 + {id, username, roles}
    body = _register(client)
    assert body["username"] == "alice"
    assert isinstance(body["id"], int)
    assert body["roles"] == ["student"]  # 注册默认授予 student（permissions §2）

    # 2) 登录：200 + {user} + Set-Cookie（E-10 载体）
    r = _login(client, "alice", GOOD_PASSWORD)
    assert r.status_code == 200
    assert r.json()["user"]["username"] == "alice"
    assert r.json()["user"]["id"] == body["id"]
    assert "password" not in r.json()["user"]
    assert "password_hash" not in r.json()["user"]
    assert client.cookies.get("access_token"), "login 必须写入 access_token cookie"

    # 3) me：同一 cookie jar → 200 {user, roles}
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    me = r.json()
    assert me["user"]["username"] == "alice"
    assert me["user"]["id"] == body["id"]
    assert me["roles"] == ["student"]


def test_jwt_payload_and_expiry(client: TestClient) -> None:
    """JWT：sub=用户 id，exp-iat = config.jwt_expire_days 天（默认 7）。"""
    body = _register(client, "bob")
    _login(client, "bob", GOOD_PASSWORD)
    token = client.cookies.get("access_token")
    payload = jwt.decode(
        token, get_settings().jwt_secret.get_secret_value(), algorithms=["HS256"]
    )
    assert payload["sub"] == str(body["id"])
    assert payload["exp"] - payload["iat"] == get_settings().jwt_expire_days * 24 * 3600


def test_register_duplicate_returns_409(client: TestClient) -> None:
    """重名 → 409（api.md auth 表）。"""
    _register(client, "carol")
    r = client.post(
        "/api/auth/register", json={"username": "carol", "password": GOOD_PASSWORD}
    )
    assert r.status_code == 409
    assert r.json()["detail"]


def test_login_wrong_password_returns_401(client: TestClient) -> None:
    """错密码 → 401（E-10）。"""
    _register(client, "dave")
    r = _login(client, "dave", "wrong-password")
    assert r.status_code == 401
    assert not client.cookies.get("access_token")


def test_login_unknown_user_returns_401(client: TestClient) -> None:
    """未知用户 → 401（与错密码同码，不外泄存在性）。"""
    r = _login(client, "nobody", GOOD_PASSWORD)
    assert r.status_code == 401


def test_me_without_cookie_returns_401(client: TestClient) -> None:
    """未带 Cookie 访问 me → 401。"""
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_with_garbage_token_returns_401(client: TestClient) -> None:
    """Cookie 里放垃圾 token → me 401（验签失败）。"""
    client.cookies.set("access_token", "not-a-jwt")
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_with_expired_token_returns_401(client: TestClient) -> None:
    """过期 token → me 401（JWT exp 校验）。"""
    body = _register(client, "erin")
    expired = jwt.encode(
        {"sub": str(body["id"]), "exp": 0},
        get_settings().jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    client.cookies.set("access_token", expired)
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_login_inactive_user_rejected(client: TestClient, session: Session) -> None:
    """停用账号（is_active=0）即使密码正确也拒登录（schema_v1 users 注）。"""
    user = User(username="ghost", password_hash=hash_password(GOOD_PASSWORD), is_active=False)
    session.add(user)
    session.flush()
    session.add(UserRole(user_id=user.id, role="student"))
    session.commit()

    r = _login(client, "ghost", GOOD_PASSWORD)
    assert r.status_code == 401
    assert not client.cookies.get("access_token")


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "ab", "password": GOOD_PASSWORD},  # username 太短
        {"username": "has space", "password": GOOD_PASSWORD},  # 非法字符
        {"username": "ok_user", "password": "short"},  # 密码太短
        {"username": "ok_user", "password": "x" * 73},  # 超 72 字符上限
        {"username": "ok_user", "password": "汉" * 40},  # 40 汉字=120 字节，超 bcrypt 72 字节
    ],
)
def test_register_validation_rejected(client: TestClient, payload: dict) -> None:
    """入参非法 → 422（api.md auth 表 + schemas/auth.py 规则）。"""
    r = client.post("/api/auth/register", json=payload)
    assert r.status_code == 422
