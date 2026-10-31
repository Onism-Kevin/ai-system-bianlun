"""S2-12 API 层测试：history 端点（api.md:40-41）。

策略：纯 CRUD（无模型调用），TestClient 门户模式。
12 用例：列表 200/空/401/排序；详情 200/消息排序/含streaming/
空消息/404 private/教师task 200/教师private 404/401。
"""
from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"

import time

from tests.api.test_events import (
    _clean_bus,
    _make_session,
    client,
    user_and_headers,
)
from tests.models.conftest import engine, session  # noqa: F401


def _add_user_message(session_db, session_id: int, content: str, status: str = "complete"):
    from app.models.message import Message

    msg = Message(
        session_id=session_id, role="user", agent_role=None, content=content, status=status
    )
    session_db.add(msg)
    session_db.commit()
    session_db.refresh(msg)
    return msg


def _add_assistant_message(session_db, session_id: int, content: str, status: str = "complete"):
    from app.models.message import Message

    msg = Message(
        session_id=session_id, role="assistant", agent_role="con", content=content, status=status
    )
    session_db.add(msg)
    session_db.commit()
    session_db.refresh(msg)
    return msg


# ---- 列表 ----


def test_history_list_200(session, client, user_and_headers):
    """GET /api/history → 200 [{id, topic, status, created_at, updated_at}]。"""
    user, cookies = user_and_headers
    _make_session(session, user.id)
    _make_session(session, user.id)

    resp = client.get("/api/history", cookies=cookies)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 2
    for item in body:
        assert "id" in item
        assert "topic" in item
        assert "status" in item
        assert "created_at" in item
        assert "updated_at" in item


def test_history_list_empty_200(session, client, user_and_headers):
    """无会话 → 200 + []（不 404）。"""
    user, cookies = user_and_headers

    resp = client.get("/api/history", cookies=cookies)
    assert resp.status_code == 200
    assert resp.json() == []


def test_history_list_401_no_auth(session, client, user_and_headers):
    """未登录 → 401。"""
    user, _ = user_and_headers
    _make_session(session, user.id)

    resp = client.get("/api/history")
    assert resp.status_code == 401


def test_history_list_ordered_by_updated_at_desc(session, client, user_and_headers):
    """列表按 updated_at DESC 排序（最近更新的排前面）。"""
    user, cookies = user_and_headers
    sess_a = _make_session(session, user.id)
    sess_b = _make_session(session, user.id)
    # PATCH 会话 A（触发 updated_at 更新）
    client.patch(f"/api/sessions/{sess_a.id}", json={"topic": "议题A改"}, cookies=cookies)

    resp = client.get("/api/history", cookies=cookies)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    # A 的 updated_at 更新了，应排在前面
    assert body[0]["id"] == sess_a.id
    assert body[1]["id"] == sess_b.id


# ---- 详情 ----


def test_history_detail_200(session, client, user_and_headers):
    """GET /api/history/{id} → 200 {session, messages:[按 seq 升序]}。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "学生发言")
    _add_assistant_message(session, sess.id, "AI 回应")

    resp = client.get(f"/api/history/{sess.id}", cookies=cookies)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "session" in body
    assert "messages" in body
    assert len(body["messages"]) == 2


def test_history_detail_messages_ordered(session, client, user_and_headers):
    """messages 按 seq 升序。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "第一条")
    _add_assistant_message(session, sess.id, "第二条")
    _add_user_message(session, sess.id, "第三条")

    resp = client.get(f"/api/history/{sess.id}", cookies=cookies)
    assert resp.status_code == 200
    body = resp.json()
    seqs = [m["seq"] for m in body["messages"]]
    assert seqs == sorted(seqs)  # 升序


def test_history_detail_includes_streaming(session, client, user_and_headers):
    """messages 包含 streaming 状态消息（完整重建，不过滤）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "学生发言", status="complete")
    _add_assistant_message(session, sess.id, "AI 回应", status="streaming")

    resp = client.get(f"/api/history/{sess.id}", cookies=cookies)
    assert resp.status_code == 200
    body = resp.json()
    statuses = [m["status"] for m in body["messages"]]
    assert "streaming" in statuses  # 包含 streaming


def test_history_detail_empty_messages(session, client, user_and_headers):
    """无消息 → 200 + messages: []（不 404）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)

    resp = client.get(f"/api/history/{sess.id}", cookies=cookies)
    assert resp.status_code == 200
    assert resp.json()["messages"] == []


def test_history_detail_404_private(session, client, user_and_headers):
    """他人 private 会话 → 404（存在性隐藏）。"""
    from app.models.user import User

    owner, cookies = user_and_headers
    other = User(username="stu2", password_hash="x", display_name="同学2")
    session.add(other)
    session.commit()
    session.refresh(other)
    sess = _make_session(session, other.id)

    resp = client.get(f"/api/history/{sess.id}", cookies=cookies)
    assert resp.status_code == 404


def test_history_detail_teacher_task_session_200(session, client, user_and_headers):
    """教师查学生 task 会话详情 → 200（can_read_session 通过）。"""
    from app.core.security import create_access_token
    from app.models.course import Course
    from app.models.session import TrainingSession
    from app.models.task import Task
    from app.models.user import User, UserRole

    owner, _ = user_and_headers
    teacher = User(username="tea1", password_hash="x", display_name="教师")
    session.add(teacher)
    session.flush()
    session.add(UserRole(user_id=teacher.id, role="teacher"))
    course = Course(teacher_id=teacher.id, name="逻辑学", invite_code="LOG101", term="2026秋")
    session.add(course)
    session.flush()
    task = Task(course_id=course.id, title="AI 议题辩论")
    session.add(task)
    session.commit()
    sess = TrainingSession(
        owner_id=owner.id, topic="AI 限制", visibility="task", task_id=task.id, status="waiting"
    )
    session.add(sess)
    session.commit()
    session.refresh(sess)

    resp = client.get(
        f"/api/history/{sess.id}",
        cookies={"access_token": create_access_token(teacher.id)},
    )
    assert resp.status_code == 200


def test_history_detail_teacher_private_404(session, client, user_and_headers):
    """教师查学生 private 会话 → 404（permissions §5.1 硬规则）。"""
    from app.core.security import create_access_token
    from app.models.user import User, UserRole

    owner, _ = user_and_headers
    teacher = User(username="tea1", password_hash="x", display_name="教师")
    session.add(teacher)
    session.flush()
    session.add(UserRole(user_id=teacher.id, role="teacher"))
    session.commit()

    sess = _make_session(session, owner.id)  # visibility 默认 private

    resp = client.get(
        f"/api/history/{sess.id}",
        cookies={"access_token": create_access_token(teacher.id)},
    )
    assert resp.status_code == 404


def test_history_detail_401_no_auth(session, client, user_and_headers):
    """未登录 → 401。"""
    user, _ = user_and_headers
    sess = _make_session(session, user.id)

    resp = client.get(f"/api/history/{sess.id}")
    assert resp.status_code == 401
