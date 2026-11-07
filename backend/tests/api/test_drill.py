"""S3-6 验收：教师情境演练（teacher_persona + drill 模式）。

覆盖：
- prompt 内容：AI 扮演"持正方立场的学生"（不是教练/反方）、会辩护、
  被问住会承认"没想清楚"
- drill 模式映射：MODE_AGENT_ROLES["drill"]="pro" → agent_role=pro
- 端到端跑通一轮：teacher 建 session(mode=drill) → POST messages →
  runner 以 agent_role="pro" 回应
"""
from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.model_provider import FakeProvider
from app.core.security import create_access_token
from app.main import app
from app.models.message import Message
from app.models.user import User, UserRole
from app.prompts import teacher_persona
from app.services.event_bus import event_bus
from app.services.session_registry import session_registry

from tests.models.conftest import engine, session  # noqa: E402,F401


@pytest.fixture(autouse=True)
def _clean_bus():
    event_bus.reset()
    session_registry.reset()
    yield
    event_bus.reset()
    session_registry.reset()


@pytest.fixture()
def client(session):
    def _override_get_db():
        yield session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def runner_session_factory(session):
    """让 BackgroundTasks 的 runner 复用测试 session（同 test_events.py）。"""
    import app.core.database as db_module

    original_factory = db_module.get_session_factory

    def _test_factory():
        return lambda: session

    db_module.get_session_factory = _test_factory
    try:
        yield session
    finally:
        db_module.get_session_factory = original_factory


def _mk_user(session: Session, username: str, roles=("student",)) -> User:
    user = User(username=username, password_hash="x", is_active=True)
    session.add(user)
    session.flush()
    for role in roles:
        session.add(UserRole(user_id=user.id, role=role))
    session.commit()
    return user


# ---- prompt 内容 ----


def test_teacher_persona_prompt_is_student_not_coach() -> None:
    """SYSTEM_PROMPT 明确：AI 是"持正方立场的学生"，不是教练/反方。"""
    msgs = teacher_persona.build_messages(
        [{"seq": 1, "role": "user", "content": "你觉得该如何引导？"}]
    )
    system = msgs[0]["content"]
    assert "学生" in system
    assert "正方" in system
    assert "辩护" in system, "应会为论点辩护"
    assert "没想清楚" in system, "被问住时应承认而非硬撑"
    assert "不是教练" in system or "不是反方" in system


def test_teacher_persona_renders_history() -> None:
    """user 模板渲染历史消息 + 教师引导。"""
    msgs = teacher_persona.build_messages(
        [{"seq": 1, "role": "user", "content": "先明确议题"}, {"seq": 2, "role": "assistant", "agent_role": "pro", "content": "我坚持限制"}]
    )
    user_part = msgs[1]["content"]
    assert "1. [学生] 先明确议题" in user_part
    assert "2. [正方] 我坚持限制" in user_part
    assert "教师" in user_part


# ---- drill 模式映射 ----


def test_drill_mode_maps_to_pro() -> None:
    from app.prompts.debate import MODE_AGENT_ROLES, agent_role_for_mode

    assert MODE_AGENT_ROLES["drill"] == "pro"
    assert agent_role_for_mode("drill") == "pro"


def test_pro_role_uses_teacher_persona() -> None:
    from app.prompts.debate import build_generation_messages

    msgs = build_generation_messages("drill", [{"seq": 1, "role": "user", "content": "引导"}])
    assert msgs[0]["role"] == "system"
    assert "学生" in msgs[0]["content"]


# ---- 端到端跑通一轮 ----


def test_drill_round_end_to_end(
    session: Session, client: TestClient, runner_session_factory, monkeypatch
) -> None:
    """teacher 建 mode=drill 会话 → POST messages → AI 以 pro 身份回应。"""
    import app.api.sessions as sessions_module

    monkeypatch.setattr(
        sessions_module, "build_provider", lambda: FakeProvider(chunks=["正方论点"])
    )
    teacher = _mk_user(session, "teacher_drill", roles=("student", "teacher"))
    token = create_access_token(teacher.id)

    # 建 drill 会话
    r = client.post(
        "/api/sessions",
        json={"topic": "AI 是否应当限制使用", "mode": "drill"},
        cookies={"access_token": token},
    )
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    # 教师发一条引导
    r = client.post(
        f"/api/sessions/{sid}/messages",
        json={"content": "请先明确你的立场。"},
        cookies={"access_token": token},
    )
    assert r.status_code == 201, r.text

    session.expire_all()
    rows = session.scalars(
        select(Message).where(Message.session_id == sid).order_by(Message.seq)
    ).all()
    assert [(r.seq, r.role, r.agent_role, r.status) for r in rows] == [
        (1, "user", None, "complete"),
        (2, "assistant", "pro", "complete"),
    ]
    assert rows[1].content == "正方论点"


def test_drill_teacher_own_session_readable(
    session: Session, client: TestClient, runner_session_factory, monkeypatch
) -> None:
    """teacher 是 drill 会话 owner → 可见（E-15 owner 优先级）。"""
    import app.api.sessions as sessions_module

    monkeypatch.setattr(
        sessions_module, "build_provider", lambda: FakeProvider(chunks=["x"])
    )
    teacher = _mk_user(session, "teacher_own", roles=("student", "teacher"))
    token = create_access_token(teacher.id)
    r = client.post(
        "/api/sessions",
        json={"topic": "议题", "mode": "drill"},
        cookies={"access_token": token},
    )
    sid = r.json()["id"]
    r = client.get(f"/api/sessions/{sid}", cookies={"access_token": token})
    assert r.status_code == 200
    assert r.json()["id"] == sid
