"""S2-11 API 层测试：revisions 端点（api.md:50-53）。

策略：FakeProvider 不涉及（纯 CRUD，无模型调用）；TestClient 门户模式。
16 用例：201 创建/version自增、200 PATCH/GET列表/GET单条、
422 空content、403 非owner、404 private/不存在、401 未登录。
"""
from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"  # 必须在导入 app 包之前写入

import json

from tests.api.test_events import (
    _clean_bus,
    _make_session,
    client,
    user_and_headers,
)
from tests.models.conftest import engine, session  # noqa: F401


# ---- 201：创建 revision ----


def test_create_revision_201(session, client, user_and_headers):
    """POST /api/revisions → 201 {id, version, status, diff:null}（api.md:50）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)

    resp = client.post(
        "/api/revisions",
        json={"session_id": sess.id, "content": "第一版观点"},
        cookies=cookies,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["version"] == 1
    assert body["status"] == "draft"
    assert body["diff"] is None


def test_create_revision_version_2(session, client, user_and_headers):
    """第二次 POST → version 自增为 2。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)

    client.post("/api/revisions", json={"session_id": sess.id, "content": "v1"}, cookies=cookies)
    resp = client.post("/api/revisions", json={"session_id": sess.id, "content": "v2"}, cookies=cookies)
    assert resp.status_code == 201, resp.text
    assert resp.json()["version"] == 2


def test_create_revision_422_empty_content(session, client, user_and_headers):
    """content 为空 → 422（Pydantic min_length=1）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)

    resp = client.post("/api/revisions", json={"session_id": sess.id, "content": ""}, cookies=cookies)
    assert resp.status_code == 422


def test_create_revision_403_non_owner_task_session(session, client, user_and_headers):
    """教师对学生 task 会话 POST revision → 403（api.md:50 字面）。"""
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

    resp = client.post(
        "/api/revisions",
        json={"session_id": sess.id, "content": "教师尝试创建"},
        cookies={"access_token": create_access_token(teacher.id)},
    )
    assert resp.status_code == 403


def test_create_revision_404_private_session(session, client, user_and_headers):
    """他人 private 会话 → 404（存在性隐藏）。"""
    from app.models.user import User

    owner, cookies = user_and_headers
    other = User(username="stu2", password_hash="x", display_name="同学2")
    session.add(other)
    session.commit()
    session.refresh(other)
    sess = _make_session(session, other.id)

    resp = client.post(
        "/api/revisions", json={"session_id": sess.id, "content": "尝试创建"}, cookies=cookies
    )
    assert resp.status_code == 404


# ---- PATCH ----


def test_patch_revision_update_content(session, client, user_and_headers):
    """PATCH 更新 content → 200 {revision, diff_vs_prev}（api.md:51）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    client.post("/api/revisions", json={"session_id": sess.id, "content": "旧内容"}, cookies=cookies)

    # 查 revision id
    from sqlalchemy import select
    from app.models.revision import Revision
    rev = session.scalars(select(Revision).where(Revision.session_id == sess.id)).first()
    rev_id = rev.id

    resp = client.patch(
        f"/api/revisions/{rev_id}", json={"content": "新内容"}, cookies=cookies
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["revision"]["content"] == "新内容"
    # diff_vs_prev 非 None（version 2 有上一版）
    assert body["diff_vs_prev"] is not None
    assert "-旧内容" in body["diff_vs_prev"]
    assert "+新内容" in body["diff_vs_prev"]


def test_patch_revision_set_final(session, client, user_and_headers):
    """PATCH status='final' → 200，status='final'。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    client.post("/api/revisions", json={"session_id": sess.id, "content": "观点"}, cookies=cookies)

    from sqlalchemy import select
    from app.models.revision import Revision
    rev = session.scalars(select(Revision).where(Revision.session_id == sess.id)).first()

    resp = client.patch(f"/api/revisions/{rev.id}", json={"status": "final"}, cookies=cookies)
    assert resp.status_code == 200, resp.text
    assert resp.json()["revision"]["status"] == "final"


def test_patch_revision_final_to_draft_200(session, client, user_and_headers):
    """PATCH final → draft 允许（撤销定稿，选 A）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    client.post("/api/revisions", json={"session_id": sess.id, "content": "观点", "status": "final"},
                cookies=cookies)

    from sqlalchemy import select
    from app.models.revision import Revision
    rev = session.scalars(select(Revision).where(Revision.session_id == sess.id)).first()

    resp = client.patch(f"/api/revisions/{rev.id}", json={"status": "draft"}, cookies=cookies)
    assert resp.status_code == 200, resp.text
    assert resp.json()["revision"]["status"] == "draft"


def test_patch_revision_new_final_demotes_old(session, client, user_and_headers):
    """PATCH 设新 final 时，旧 final 自动降级为 draft（最多一个 final）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    # v1 final
    client.post("/api/revisions", json={"session_id": sess.id, "content": "v1", "status": "final"},
                cookies=cookies)
    # v2 final（应降级 v1）
    client.post("/api/revisions", json={"session_id": sess.id, "content": "v2", "status": "final"},
                cookies=cookies)

    from sqlalchemy import select
    from app.models.revision import Revision
    revs = session.scalars(
        select(Revision).where(Revision.session_id == sess.id).order_by(Revision.version.asc())
    ).all()
    assert len(revs) == 2
    assert revs[0].status == "draft"  # v1 被降级
    assert revs[1].status == "final"  # v2 是 final


def test_patch_revision_403_non_owner_task_session(session, client, user_and_headers):
    """教师对学生 task 会话的 revision PATCH → 403（E-16 分层）。"""
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

    # 学生创建 revision
    client.post("/api/revisions", json={"session_id": sess.id, "content": "学生观点"},
                cookies={"access_token": create_access_token(owner.id)})
    from sqlalchemy import select
    from app.models.revision import Revision
    rev = session.scalars(select(Revision).where(Revision.session_id == sess.id)).first()

    resp = client.patch(
        f"/api/revisions/{rev.id}", json={"content": "教师改"},
        cookies={"access_token": create_access_token(teacher.id)},
    )
    assert resp.status_code == 403


# ---- GET 列表 ----


def test_get_revisions_list(session, client, user_and_headers):
    """GET /api/revisions?session_id= → 200 列表含 diff_vs_prev（api.md:52）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    client.post("/api/revisions", json={"session_id": sess.id, "content": "v1"}, cookies=cookies)
    client.post("/api/revisions", json={"session_id": sess.id, "content": "v2"}, cookies=cookies)

    resp = client.get(f"/api/revisions?session_id={sess.id}", cookies=cookies)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 2
    assert body[0]["version"] == 1
    assert body[0]["diff_vs_prev"] is None  # 首版 null
    assert body[1]["version"] == 2
    assert body[1]["diff_vs_prev"] is not None  # 第二版有 diff


def test_get_revisions_empty_200(session, client, user_and_headers):
    """GET 列表空 → 200 + []（不 404）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)

    resp = client.get(f"/api/revisions?session_id={sess.id}", cookies=cookies)
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


# ---- GET 单条 ----


def test_get_revision_by_id_200(session, client, user_and_headers):
    """GET /api/revisions/{id} → 200 {revision, diff_vs_prev}（api.md:53）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    client.post("/api/revisions", json={"session_id": sess.id, "content": "观点"}, cookies=cookies)

    from sqlalchemy import select
    from app.models.revision import Revision
    rev = session.scalars(select(Revision).where(Revision.session_id == sess.id)).first()

    resp = client.get(f"/api/revisions/{rev.id}", cookies=cookies)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["revision"]["id"] == rev.id
    assert "diff_vs_prev" in body


def test_get_revision_first_version_diff_null(session, client, user_and_headers):
    """首版 diff_vs_prev=null（无上一版）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    client.post("/api/revisions", json={"session_id": sess.id, "content": "首版"}, cookies=cookies)

    from sqlalchemy import select
    from app.models.revision import Revision
    rev = session.scalars(select(Revision).where(Revision.session_id == sess.id)).first()

    resp = client.get(f"/api/revisions/{rev.id}", cookies=cookies)
    assert resp.status_code == 200, resp.text
    assert resp.json()["diff_vs_prev"] is None


def test_get_revision_404_nonexistent(session, client, user_and_headers):
    """GET 不存在的 id → 404。"""
    user, cookies = user_and_headers

    resp = client.get("/api/revisions/999999", cookies=cookies)
    assert resp.status_code == 404


# ---- 401：未登录 ----


def test_get_revisions_401_no_auth(session, client, user_and_headers):
    """未登录 GET 列表 → 401。"""
    user, _ = user_and_headers
    sess = _make_session(session, user.id)

    resp = client.get(f"/api/revisions?session_id={sess.id}")
    assert resp.status_code == 401
