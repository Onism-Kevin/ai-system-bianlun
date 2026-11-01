"""S2-F7 前置：reflection 双端点 API 测试（G2 裁定，api.md v1.2:36-37）。

覆盖：401 / 403（课程教师可读 task 会话但非 owner）/ 404（不存在或 private
越权存在性隐藏）/ 422（空 / 超长）/ upsert（同会话覆盖保存）/ 空读取 200
content=null（不 404）。

策略：纯 CRUD（无模型调用），TestClient 门户模式。
"""
from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"  # 必须在导入 app 包之前写入

from tests.api.test_events import (  # noqa: E402
    _make_session,
    client,
    user_and_headers,
)
from tests.models.conftest import engine, session  # noqa: F401

# reflection 长度上限（app/schemas/session.py REFLECTION_MAX）
from app.schemas.session import REFLECTION_MAX  # noqa: E402


# ---- 成功路径 ----


def test_post_reflection_200_and_get_roundtrip(session, client, user_and_headers):
    """POST → 200 {updated_at}；GET → 200 {content, updated_at} 回读一致。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)

    resp = client.post(
        f"/api/sessions/{sess.id}/reflection",
        json={"content": "我忽略了反方的核心论据，下次要先复述再回应。"},
        cookies=cookies,
    )
    assert resp.status_code == 200, resp.text
    saved = resp.json()
    assert "updated_at" in saved

    resp = client.get(f"/api/sessions/{sess.id}/reflection", cookies=cookies)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["content"] == "我忽略了反方的核心论据，下次要先复述再回应。"
    assert body["updated_at"] == saved["updated_at"]


def test_get_reflection_empty_200_null(session, client, user_and_headers):
    """未填写反思 → GET 200 content=null（**不 404**，空反思非越权）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)

    resp = client.get(f"/api/sessions/{sess.id}/reflection", cookies=cookies)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["content"] is None


def test_post_reflection_upsert(session, client, user_and_headers):
    """同会话反复保存 = upsert 覆盖同一列（不新增行、不版本化）。"""
    from app.models.session import TrainingSession
    from app.models.message import Message

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)

    for text in ("第一版反思", "第二版反思"):
        resp = client.post(
            f"/api/sessions/{sess.id}/reflection",
            json={"content": text},
            cookies=cookies,
        )
        assert resp.status_code == 200, resp.text

    # 同一列覆盖：DB 行 reflection 字段为最新值，无额外行
    session.expire_all()
    rows = session.query(TrainingSession).filter_by(id=sess.id).all()
    assert len(rows) == 1
    assert rows[0].reflection == "第二版反思"
    # reflection 是 sessions 列，不产生 messages/revisions 之类的版本行
    assert session.query(Message).filter_by(session_id=sess.id).count() == 0

    resp = client.get(f"/api/sessions/{sess.id}/reflection", cookies=cookies)
    assert resp.json()["content"] == "第二版反思"


def test_post_reflection_updates_updated_at(session, client, user_and_headers):
    """保存反思触发 updated_at 刷新（E-7 应用层 onupdate）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    before = sess.updated_at

    # sessions.updated_at 为 MySQL DATETIME（秒级精度），睡过 1s 保证可观测
    import time

    time.sleep(1.1)

    resp = client.post(
        f"/api/sessions/{sess.id}/reflection",
        json={"content": "反思内容"},
        cookies=cookies,
    )
    assert resp.status_code == 200, resp.text
    session.expire_all()
    after = sess.updated_at
    assert after > before


# ---- 422 ----


def test_post_reflection_422_empty(session, client, user_and_headers):
    """空 content → 422（min_length=1）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)

    resp = client.post(
        f"/api/sessions/{sess.id}/reflection", json={"content": ""}, cookies=cookies
    )
    assert resp.status_code == 422


def test_post_reflection_422_too_long(session, client, user_and_headers):
    """超 REFLECTION_MAX → 422。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)

    resp = client.post(
        f"/api/sessions/{sess.id}/reflection",
        json={"content": "x" * (REFLECTION_MAX + 1)},
        cookies=cookies,
    )
    assert resp.status_code == 422

    # 边界值恰好通过
    resp = client.post(
        f"/api/sessions/{sess.id}/reflection",
        json={"content": "x" * REFLECTION_MAX},
        cookies=cookies,
    )
    assert resp.status_code == 200


# ---- 401 / 404 ----


def test_post_reflection_401_no_auth(session, client, user_and_headers):
    user, _ = user_and_headers
    sess = _make_session(session, user.id)
    resp = client.post(f"/api/sessions/{sess.id}/reflection", json={"content": "x"})
    assert resp.status_code == 401


def test_get_reflection_401_no_auth(session, client, user_and_headers):
    user, _ = user_and_headers
    sess = _make_session(session, user.id)
    resp = client.get(f"/api/sessions/{sess.id}/reflection")
    assert resp.status_code == 401


def test_post_reflection_404_nonexistent(session, client, user_and_headers):
    user, cookies = user_and_headers
    resp = client.post(
        "/api/sessions/999999/reflection", json={"content": "x"}, cookies=cookies
    )
    assert resp.status_code == 404


def test_get_reflection_404_nonexistent(session, client, user_and_headers):
    user, cookies = user_and_headers
    resp = client.get("/api/sessions/999999/reflection", cookies=cookies)
    assert resp.status_code == 404


def test_post_reflection_404_other_private(session, client, user_and_headers):
    """他人 private 会话 → 404（存在性隐藏）。"""
    from app.models.user import User

    owner, cookies = user_and_headers
    other = User(username="stu2", password_hash="x", display_name="同学2")
    session.add(other)
    session.commit()
    session.refresh(other)
    sess = _make_session(session, other.id)

    resp = client.post(
        f"/api/sessions/{sess.id}/reflection", json={"content": "x"}, cookies=cookies
    )
    assert resp.status_code == 404


# ---- 403（课程教师可读 task 会话但非 owner）----


def _mk_teacher_task_session(session_db, owner_id: int):
    """建教师 + 其课程任务 + 学生 owner 的 task 会话；返回 (teacher, session)。"""
    from app.core.security import create_access_token
    from app.models.course import Course
    from app.models.session import TrainingSession
    from app.models.task import Task
    from app.models.user import User, UserRole

    teacher = User(username="tea_ref", password_hash="x", display_name="教师")
    session_db.add(teacher)
    session_db.flush()
    session_db.add(UserRole(user_id=teacher.id, role="teacher"))
    course = Course(teacher_id=teacher.id, name="逻辑学", invite_code="LOGREF", term="2026秋")
    session_db.add(course)
    session_db.flush()
    task = Task(course_id=course.id, title="AI 议题辩论")
    session_db.add(task)
    session_db.flush()
    sess = TrainingSession(
        owner_id=owner_id, topic="AI 限制", visibility="task", task_id=task.id, status="waiting"
    )
    session_db.add(sess)
    session_db.commit()
    session_db.refresh(sess)
    return teacher, create_access_token(teacher.id), sess


def test_post_reflection_403_teacher_task_session(session, client, user_and_headers):
    """教师可读学生 task 会话（can_read_session 通过）但非 owner → 403。"""
    owner, _ = user_and_headers
    teacher, teacher_cookies, sess = _mk_teacher_task_session(session, owner.id)

    resp = client.post(
        f"/api/sessions/{sess.id}/reflection",
        json={"content": "教师代填"},
        cookies={"access_token": teacher_cookies},
    )
    assert resp.status_code == 403


def test_get_reflection_403_teacher_task_session(session, client, user_and_headers):
    owner, _ = user_and_headers
    teacher, teacher_cookies, sess = _mk_teacher_task_session(session, owner.id)

    resp = client.get(
        f"/api/sessions/{sess.id}/reflection",
        cookies={"access_token": teacher_cookies},
    )
    assert resp.status_code == 403
