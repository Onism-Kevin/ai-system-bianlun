"""S2-10 API 层测试：reports 端点（api.md:47-49）。

策略：FakeProvider 驱动，不触网；TestClient 门户模式同步执行。
9 用例：200 正常/落库/无反思/无final；502 坏JSON/缺维度；
404 private/无报告；401 未登录。
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


def _add_user_message(session_db, session_id: int, content: str, status: str = "complete"):
    """创建一条 user 消息，返回 Message ORM 对象（含 seq）。"""
    from app.models.message import Message

    msg = Message(
        session_id=session_id, role="user", agent_role=None, content=content, status=status
    )
    session_db.add(msg)
    session_db.commit()
    session_db.refresh(msg)
    return msg


def _valid_report_json() -> str:
    """构造合法 ReviewReport JSON（含四维度 scores）。"""
    return json.dumps(
        {
            "summary": "学生在论证结构方面表现良好，证据质量有待提高。",
            "strengths": ["论点清晰", "逻辑连贯"],
            "weaknesses": ["证据不够具体", "未回应反例"],
            "sections": [
                {"heading": "论证结构", "body": "主张明确，推理链完整。", "dimension_id": "argument_structure"},
                {"heading": "证据质量", "body": "部分证据笼统，来源不可查。", "dimension_id": "evidence_quality"},
                {"heading": "反驳与回应", "body": "未系统识别反例。", "dimension_id": "rebuttal_response"},
                {"heading": "观点修订与反思", "body": "反思缺失。", "dimension_id": "revision_reflection"},
            ],
            "scores": {
                "argument_structure": 80,
                "evidence_quality": 70,
                "rebuttal_response": 65,
                "revision_reflection": 55,
            },
        },
        ensure_ascii=False,
    )


# ---- 201：正常生成报告 ----


def test_reports_201_full_report(session, client, user_and_headers, monkeypatch):
    """POST reports → 201 ReviewReport 五字段 + scores 四维（api.md:47）。"""
    from app.core.model_provider import FakeProvider

    import app.api.reports as reports_module

    monkeypatch.setattr(
        reports_module, "build_provider", lambda: FakeProvider(chunks=[_valid_report_json()])
    )

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "我认为AI应该限制使用")

    resp = client.post(f"/api/sessions/{sess.id}/reports", cookies=cookies)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "summary" in body
    assert "strengths" in body
    assert "weaknesses" in body
    assert "sections" in body
    assert "scores" in body
    # scores 四维
    assert set(body["scores"].keys()) == {
        "argument_structure", "evidence_quality", "rebuttal_response", "revision_reflection"
    }


# ---- 201：报告落库 reports 表 ----


def test_reports_201_persisted(session, client, user_and_headers, monkeypatch):
    """POST reports → 201，reports 表有行，scores JSON + overall_score 正确。

    overall_score = 80×0.3 + 70×0.25 + 65×0.25 + 55×0.2 = 24 + 17.5 + 16.25 + 11 = 68.75
    """
    from app.core.model_provider import FakeProvider

    import app.api.reports as reports_module
    from app.models.report import Report

    monkeypatch.setattr(
        reports_module, "build_provider", lambda: FakeProvider(chunks=[_valid_report_json()])
    )

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "我认为AI应该限制使用")

    resp = client.post(f"/api/sessions/{sess.id}/reports", cookies=cookies)
    assert resp.status_code == 201, resp.text

    session.expire_all()
    row = session.scalars(
        __import__("sqlalchemy").select(Report)
        .where(Report.session_id == sess.id)
        .order_by(Report.id.desc())
        .limit(1)
    ).first()
    assert row is not None
    assert row.rubric_version == "v1.0"
    assert set(row.scores.keys()) == {
        "argument_structure", "evidence_quality", "rebuttal_response", "revision_reflection"
    }
    # overall_score = 68.75
    assert float(row.overall_score) == 68.75
    assert "论证结构" in row.summary_text


# ---- 201：反思为空 ----


def test_reports_201_no_reflection(session, client, user_and_headers, monkeypatch):
    """sessions.reflection=NULL → 报告正常生成（不 422）。"""
    from app.core.model_provider import FakeProvider

    import app.api.reports as reports_module

    monkeypatch.setattr(
        reports_module, "build_provider", lambda: FakeProvider(chunks=[_valid_report_json()])
    )

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "我认为AI应该限制使用")
    # reflection 默认 NULL

    resp = client.post(f"/api/sessions/{sess.id}/reports", cookies=cookies)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "summary" in body


# ---- 201：无 final revision（回退 draft） ----


def test_reports_201_no_final_revision(session, client, user_and_headers, monkeypatch):
    """revisions 无 final → 回退到 draft，报告正常生成。"""
    from app.core.model_provider import FakeProvider

    import app.api.reports as reports_module
    from app.models.revision import Revision

    monkeypatch.setattr(
        reports_module, "build_provider", lambda: FakeProvider(chunks=[_valid_report_json()])
    )

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "我认为AI应该限制使用")
    # 只创建 draft revision，不创建 final
    session.add(Revision(
        session_id=sess.id, student_id=user.id, content="草稿版本", version=1, status="draft"
    ))
    session.commit()

    resp = client.post(f"/api/sessions/{sess.id}/reports", cookies=cookies)
    assert resp.status_code == 201, resp.text


# ---- 502：坏 JSON（E-23：reports 端点映射 502） ----


def test_reports_502_invalid_structure(session, client, user_and_headers, monkeypatch):
    """坏 JSON → 502（E-23：reports 端点映射 502，非 422）。"""
    from app.core.model_provider import FakeProvider

    import app.api.reports as reports_module

    monkeypatch.setattr(
        reports_module,
        "build_provider",
        lambda: FakeProvider(chunks=["这不是合法 JSON"]),
    )

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "学生的核心主张")
    resp = client.post(f"/api/sessions/{sess.id}/reports", cookies=cookies)
    assert resp.status_code == 502


# ---- 502：scores 缺维度 ----


def test_reports_502_missing_dimension(session, client, user_and_headers, monkeypatch):
    """scores 缺一个维度 → StructuredValidationError → 502。"""
    from app.core.model_provider import FakeProvider

    import app.api.reports as reports_module

    # 缺 revision_reflection 维度
    bad_json = json.dumps(
        {
            "summary": "评价",
            "strengths": [],
            "weaknesses": [],
            "sections": [],
            "scores": {
                "argument_structure": 80,
                "evidence_quality": 70,
                "rebuttal_response": 65,
            },
        },
        ensure_ascii=False,
    )
    monkeypatch.setattr(
        reports_module, "build_provider", lambda: FakeProvider(chunks=[bad_json])
    )

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "学生的核心主张")
    resp = client.post(f"/api/sessions/{sess.id}/reports", cookies=cookies)
    assert resp.status_code == 502


# ---- 404：private 会话越权 ----


def test_reports_404_private_session(session, client, user_and_headers):
    """他人 private 会话 → 404（存在性隐藏）。"""
    from app.models.user import User

    owner, cookies = user_and_headers
    other = User(username="stu2", password_hash="x", display_name="同学2")
    session.add(other)
    session.commit()
    session.refresh(other)

    sess = _make_session(session, other.id)
    resp = client.post(f"/api/sessions/{sess.id}/reports", cookies=cookies)
    assert resp.status_code == 404


# ---- 401：未登录 ----


def test_reports_401_no_auth(session, client, user_and_headers):
    """未登录 → 401（get_current_user 依赖层）。"""
    user, _ = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "学生的核心主张")

    resp = client.post(f"/api/sessions/{sess.id}/reports")
    assert resp.status_code == 401


# ---- 404：GET 无报告 ----


def test_reports_404_no_report(session, client, user_and_headers):
    """GET /api/sessions/{id}/reports 无报告 → 404。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)

    resp = client.get(f"/api/sessions/{sess.id}/reports", cookies=cookies)
    assert resp.status_code == 404


# ---- 201：无 revisions（回退 messages） ----


def test_reports_201_no_revision_at_all(session, client, user_and_headers, monkeypatch):
    """revisions 表为空 → 回退到 messages 拼接，报告正常生成。"""
    from app.core.model_provider import FakeProvider

    import app.api.reports as reports_module

    monkeypatch.setattr(
        reports_module, "build_provider", lambda: FakeProvider(chunks=[_valid_report_json()])
    )

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "我认为AI应该限制使用")
    _add_user_message(session, sess.id, "因为隐私风险很大")
    # 不创建任何 Revision 行

    resp = client.post(f"/api/sessions/{sess.id}/reports", cookies=cookies)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "summary" in body


# ---- 403：教师对 student task 会话调 POST ----


def test_reports_403_non_owner_task_session(session, client, user_and_headers):
    """教师对学生 task 会话调 POST reports → 403（api.md:47 字面）。"""
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
    _add_user_message(session, sess.id, "学生的核心主张")

    resp = client.post(
        f"/api/sessions/{sess.id}/reports",
        cookies={"access_token": create_access_token(teacher.id)},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "仅会话所有者可生成报告"


# ---- GET /api/reports/{id} 200 ----


def test_get_report_by_id_200(session, client, user_and_headers, monkeypatch):
    """GET /api/reports/{id} → 200，返回完整报告（api.md:49）。"""
    from app.core.model_provider import FakeProvider

    import app.api.reports as reports_module
    from sqlalchemy import select
    from app.models.report import Report

    monkeypatch.setattr(
        reports_module, "build_provider", lambda: FakeProvider(chunks=[_valid_report_json()])
    )

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "我认为AI应该限制使用")

    # POST 生成报告
    resp = client.post(f"/api/sessions/{sess.id}/reports", cookies=cookies)
    assert resp.status_code == 201, resp.text

    # 查 DB 获取 report id
    session.expire_all()
    row = session.scalars(
        select(Report).where(Report.session_id == sess.id).order_by(Report.id.desc()).limit(1)
    ).first()
    assert row is not None
    report_id = row.id

    # GET /api/reports/{id}
    resp = client.get(f"/api/reports/{report_id}", cookies=cookies)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == report_id
    assert body["session_id"] == sess.id
    assert body["rubric_version"] == "v1.0"
    assert "scores" in body
    assert "overall_score" in body
    assert "summary_text" in body
    assert body["overall_score"] == 68.75


# ---- GET /api/reports/{id} 404 ----


def test_get_report_by_id_404(session, client, user_and_headers):
    """GET /api/reports/{nonexistent_id} → 404。"""
    user, cookies = user_and_headers

    resp = client.get("/api/reports/999999", cookies=cookies)
    assert resp.status_code == 404
