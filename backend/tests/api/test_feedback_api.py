"""S3-5 验收：学生反馈 API（api.md:68-69，schema_v3 表 4 三维度）。

覆盖：
- POST：200 {id}；upsert 同一行；未提交该任务 404；非课程成员 404；
  匿名 401；scores 越界/缺维度 422；comment 可选
- GET（教师）：200 列表含 student_id/scores/comment/created_at；空列表 200；
  成员学生 403；非成员 404；匿名 401

feedback 三维度（schema_v3 表 4 定稿）：difficulty/coach_helpful/time_reasonable，
各 1-5，语义=学生对任务的体验评分（≠ rubric 四维度）。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.codes import generate_code
from app.core.security import create_access_token
from app.models.course import Course, CourseMember
from app.models.feedback import FeedbackForm
from app.models.session import TrainingSession
from app.models.task import Task, TaskSubmission
from app.models.user import User, UserRole


# ---- helpers ----


def _mk_user(session: Session, username: str, roles=("student",)) -> User:
    user = User(username=username, password_hash="x", is_active=True)
    session.add(user)
    session.flush()
    for role in roles:
        session.add(UserRole(user_id=user.id, role=role))
    session.commit()
    return user


def _mk_course(session: Session, teacher: User, name: str) -> Course:
    course = Course(teacher_id=teacher.id, name=name, invite_code=generate_code())
    session.add(course)
    session.flush()
    return course


def _mk_task(session: Session, course: Course, title: str) -> Task:
    task = Task(course_id=course.id, title=title, join_code=generate_code())
    session.add(task)
    session.flush()
    return task


def _join_db(session: Session, course: Course, student: User) -> None:
    session.add(CourseMember(course_id=course.id, user_id=student.id))
    session.commit()


def _submit_db(session: Session, task: Task, student: User) -> TaskSubmission:
    """直接落一条提交记录（feedback 前置：已提交该任务）。

    TaskSubmission.session_id 是 NOT NULL → 必须先建一个 task 会话。
    """
    sess = TrainingSession(
        owner_id=student.id, topic="议题", visibility="task",
        task_id=task.id, status="waiting",
    )
    session.add(sess)
    session.flush()
    sub = TaskSubmission(student_id=student.id, task_id=task.id, session_id=sess.id)
    session.add(sub)
    session.flush()
    return sub


def _cookies(user: User) -> dict[str, str]:
    return {"access_token": create_access_token(user.id)}


GOOD_SCORES = {"difficulty": 3, "coach_helpful": 4, "time_reasonable": 5}


def _post_feedback(client, task: Task, body: dict, user: User):
    return client.post(
        f"/api/tasks/{task.id}/feedback", json=body, cookies=_cookies(user)
    )


@pytest.fixture()
def teacher(session: Session) -> User:
    return _mk_user(session, "teacher1", roles=("student", "teacher"))


@pytest.fixture()
def student(session: Session) -> User:
    return _mk_user(session, "student1")


@pytest.fixture()
def student2(session: Session) -> User:
    return _mk_user(session, "student2")


@pytest.fixture()
def course_task_submitted(session: Session, teacher: User, student: User):
    """课程 + 任务 + student 已加入并已提交。"""
    course = _mk_course(session, teacher, "反馈课")
    task = _mk_task(session, course, "反馈任务")
    _join_db(session, course, student)
    _submit_db(session, task, student)
    return course, task


# ---- POST /api/tasks/{task_id}/feedback ----


def test_post_feedback_returns_id(
    client: TestClient, student: User, course_task_submitted
) -> None:
    course, task = course_task_submitted
    r = _post_feedback(
        client, task,
        {"scores": GOOD_SCORES, "comment": "难度适中"},
        student,
    )
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["id"], int)


def test_post_feedback_upsert_same_row(
    client: TestClient, student: User, course_task_submitted, session: Session
) -> None:
    """一生一任务一份：重复提交更新同一条行（DB 只留一行）。"""
    from sqlalchemy import select

    course, task = course_task_submitted
    first = _post_feedback(
        client, task, {"scores": GOOD_SCORES, "comment": "v1"}, student
    )
    second = _post_feedback(
        client, task,
        {"scores": {"difficulty": 5, "coach_helpful": 5, "time_reasonable": 5},
         "comment": "v2"},
        student,
    )
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    # DB 里只有一行
    rows = session.scalars(
        select(FeedbackForm).where(
            FeedbackForm.task_id == task.id, FeedbackForm.student_id == student.id
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].comment == "v2", "upsert 应更新 comment"
    assert rows[0].scores["difficulty"] == 5


def test_post_feedback_not_submitted_returns_404(
    client: TestClient, teacher: User, student: User, session: Session
) -> None:
    """未提交该任务 → 404（存在性隐藏）。"""
    course = _mk_course(session, teacher, "未提交课")
    task = _mk_task(session, course, "未提交任务")
    _join_db(session, course, student)
    # student 加入但未提交
    r = _post_feedback(client, task, {"scores": GOOD_SCORES}, student)
    assert r.status_code == 404


def test_post_feedback_non_member_returns_404(
    client: TestClient, teacher: User, student: User, student2: User,
    course_task_submitted,
) -> None:
    """非课程成员 → 404。"""
    course, task = course_task_submitted
    # student 是成员且已提交 → 200
    r = _post_feedback(client, task, {"scores": GOOD_SCORES}, student)
    assert r.status_code == 200  # student 是成员
    # student2 未加入 → 404
    r = client.post(
        f"/api/tasks/{task.id}/feedback",
        json={"scores": GOOD_SCORES},
        cookies=_cookies(student2),
    )
    assert r.status_code == 404


def test_post_feedback_anonymous_returns_401(
    client: TestClient, course_task_submitted
) -> None:
    course, task = course_task_submitted
    r = client.post(f"/api/tasks/{task.id}/feedback", json={"scores": GOOD_SCORES})
    assert r.status_code == 401


def test_post_feedback_score_out_of_range_returns_422(
    client: TestClient, student: User, course_task_submitted
) -> None:
    course, task = course_task_submitted
    for bad in (
        {"difficulty": 0, "coach_helpful": 3, "time_reasonable": 3},
        {"difficulty": 3, "coach_helpful": 6, "time_reasonable": 3},
    ):
        r = _post_feedback(client, task, {"scores": bad}, student)
        assert r.status_code == 422, r.text


def test_post_feedback_missing_dimension_returns_422(
    client: TestClient, student: User, course_task_submitted
) -> None:
    course, task = course_task_submitted
    r = _post_feedback(
        client, task, {"scores": {"difficulty": 3, "coach_helpful": 4}}, student
    )
    assert r.status_code == 422


def test_post_feedback_comment_optional(
    client: TestClient, student: User, course_task_submitted
) -> None:
    course, task = course_task_submitted
    r = _post_feedback(client, task, {"scores": GOOD_SCORES}, student)
    assert r.status_code == 200


# ---- GET /api/tasks/{task_id}/feedback（教师）----


def test_get_feedback_teacher(
    client: TestClient, teacher: User, student: User, course_task_submitted
) -> None:
    course, task = course_task_submitted
    _post_feedback(client, task, {"scores": GOOD_SCORES, "comment": "好评"}, student)

    r = client.get(f"/api/tasks/{task.id}/feedback", cookies=_cookies(teacher))
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["student_id"] == student.id
    assert row["scores"] == GOOD_SCORES
    assert row["comment"] == "好评"
    assert row["created_at"]


def test_get_feedback_empty_list(
    client: TestClient, teacher: User, course_task_submitted
) -> None:
    course, task = course_task_submitted
    r = client.get(f"/api/tasks/{task.id}/feedback", cookies=_cookies(teacher))
    assert r.status_code == 200
    assert r.json() == []


def test_get_feedback_member_student_returns_403(
    client: TestClient, student: User, course_task_submitted
) -> None:
    """E-16：任务可读（成员）但非课程教师 → 403。"""
    course, task = course_task_submitted
    r = client.get(f"/api/tasks/{task.id}/feedback", cookies=_cookies(student))
    assert r.status_code == 403


def test_get_feedback_non_member_returns_404(
    client: TestClient, student2: User, course_task_submitted
) -> None:
    course, task = course_task_submitted
    r = client.get(f"/api/tasks/{task.id}/feedback", cookies=_cookies(student2))
    assert r.status_code == 404


def test_get_feedback_anonymous_returns_401(
    client: TestClient, course_task_submitted
) -> None:
    course, task = course_task_submitted
    assert client.get(f"/api/tasks/{task.id}/feedback").status_code == 401
