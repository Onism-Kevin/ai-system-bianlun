"""S3-4 验收：提交 API（api.md:65-67，E-5 upsert + E-8 归档处置）。

覆盖：
- POST 提交：200 {id, session_id, submitted_at, replaced}；upsert 换会话重做
  replaced=true + 旧会话 visibility→private；非 owner 404；会话不存在 404；
  会话非本任务 404；匿名 401
- GET 列表（教师）：仅已提交行；未提交学生无行；成员学生 403；非成员 404；
  匿名 401
- GET /me：本人提交 200；未提交 404；非成员 404；匿名 401
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.codes import generate_code
from app.core.security import create_access_token
from app.models.course import Course, CourseMember
from app.models.session import TrainingSession
from app.models.task import Task
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


def _mk_session(session: Session, owner: User, task: Task, topic: str = "议题") -> TrainingSession:
    sess = TrainingSession(
        owner_id=owner.id, topic=topic, visibility="task", task_id=task.id, status="waiting"
    )
    session.add(sess)
    session.flush()
    return sess


def _join_db(session: Session, course: Course, student: User) -> None:
    session.add(CourseMember(course_id=course.id, user_id=student.id))
    session.commit()


def _cookies(user: User) -> dict[str, str]:
    return {"access_token": create_access_token(user.id)}


def _submit(client, task: Task, session_id: int, user: User) -> "object":
    return client.post(
        f"/api/tasks/{task.id}/submissions",
        json={"session_id": session_id},
        cookies=_cookies(user),
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
def course_task(session: Session, teacher: User) -> tuple[Course, Task]:
    course = _mk_course(session, teacher, "提交课")
    task = _mk_task(session, course, "提交任务")
    return course, task


# ---- POST /api/tasks/{task_id}/submissions ----


def test_submit_new_submission(
    client: TestClient, student: User, course_task, session: Session
) -> None:
    course, task = course_task
    _join_db(session, course, student)
    sess = _mk_session(session, student, task)

    r = _submit(client, task, sess.id, student)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_id"] == sess.id
    assert body["replaced"] is False
    assert body["id"] > 0
    assert body["submitted_at"]


def test_submit_same_session_twice_is_upsert(
    client: TestClient, student: User, course_task, session: Session
) -> None:
    course, task = course_task
    _join_db(session, course, student)
    sess = _mk_session(session, student, task)

    first = _submit(client, task, sess.id, student)
    assert first.status_code == 200 and first.json()["replaced"] is False
    second = _submit(client, task, sess.id, student)
    assert second.status_code == 200, second.text
    assert second.json()["replaced"] is True
    assert second.json()["id"] == first.json()["id"], "upsert 应更新同一条行"


def test_submit_new_session_replaces_old_and_archives_old_session(
    client: TestClient, student: User, course_task, session: Session
) -> None:
    """换会话重做：旧会话 visibility→private（计划书 S3-4 备注）。"""
    course, task = course_task
    _join_db(session, course, student)
    old_sess = _mk_session(session, student, task, topic="旧会话")
    new_sess = _mk_session(session, student, task, topic="新会话")

    first = _submit(client, task, old_sess.id, student)
    assert first.status_code == 200 and first.json()["replaced"] is False

    second = _submit(client, task, new_sess.id, student)
    assert second.status_code == 200, second.text
    assert second.json()["replaced"] is True
    assert second.json()["session_id"] == new_sess.id

    session.refresh(old_sess)
    assert old_sess.visibility == "private", "旧会话应改为 private"


def test_resubmission_persists_new_session_in_db(
    client: TestClient, student: User, course_task, session: Session
) -> None:
    """回归：响应 session_id 与 DB 行必须一致（防"响应对但未提交"）。"""
    from sqlalchemy import select

    from app.models.task import TaskSubmission

    course, task = course_task
    _join_db(session, course, student)
    old_sess = _mk_session(session, student, task, topic="旧")
    new_sess = _mk_session(session, student, task, topic="新")

    _submit(client, task, old_sess.id, student)
    second = _submit(client, task, new_sess.id, student)
    assert second.json()["session_id"] == new_sess.id

    # 直接查 DB，验证提交行真的指向新会话（而非仅响应体正确）
    row = session.scalar(
        select(TaskSubmission).where(
            TaskSubmission.task_id == task.id,
            TaskSubmission.student_id == student.id,
        )
    )
    assert row is not None
    assert row.session_id == new_sess.id, "DB 行的 session_id 必须是新会话"


def test_submit_non_owner_session_returns_404(
    client: TestClient, student: User, course_task, session: Session
) -> None:
    """他人会话 → 404（存在性隐藏）。"""
    course, task = course_task
    owner = _mk_user(session, "owner2")
    _join_db(session, course, owner)
    sess = _mk_session(session, owner, task)
    _join_db(session, course, student)

    r = _submit(client, task, sess.id, student)
    assert r.status_code == 404


def test_submit_unknown_session_returns_404(
    client: TestClient, student: User, course_task, session: Session
) -> None:
    course, task = course_task
    _join_db(session, course, student)
    r = _submit(client, task, 999999, student)
    assert r.status_code == 404


def test_submit_session_of_other_task_returns_404(
    client: TestClient, student: User, course_task, session: Session
) -> None:
    """会话属于其他任务 → 404。"""
    course, task = course_task
    _join_db(session, course, student)
    other_task = _mk_task(session, course, "其他任务")
    other_sess = _mk_session(session, student, other_task)

    r = _submit(client, task, other_sess.id, student)
    assert r.status_code == 404


def test_submit_anonymous_returns_401(
    client: TestClient, student: User, course_task, session: Session
) -> None:
    course, task = course_task
    _join_db(session, course, student)
    sess = _mk_session(session, student, task)
    r = client.post(
        f"/api/tasks/{task.id}/submissions", json={"session_id": sess.id}
    )
    assert r.status_code == 401


def test_submit_unknown_task_returns_404(
    client: TestClient, student: User, course_task, session: Session
) -> None:
    course, task = course_task
    _join_db(session, course, student)
    sess = _mk_session(session, student, task)
    r = client.post(
        "/api/tasks/999999/submissions",
        json={"session_id": sess.id},
        cookies=_cookies(student),
    )
    assert r.status_code == 404


# ---- GET /api/tasks/{task_id}/submissions（教师列表）----


def test_list_submissions_teacher_only_submitted(
    client: TestClient, teacher: User, student: User, course_task, session: Session
) -> None:
    course, task = course_task
    _join_db(session, course, student)
    sess = _mk_session(session, student, task)
    _submit(client, task, sess.id, student)

    r = client.get(f"/api/tasks/{task.id}/submissions", cookies=_cookies(teacher))
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["student_id"] == student.id
    assert rows[0]["session_id"] == sess.id


def test_list_submissions_excludes_unsubmitted(
    client: TestClient,
    teacher: User,
    student: User,
    student2: User,
    course_task,
    session: Session,
) -> None:
    """未提交的学生不在列表（契约：仅已提交行）。"""
    course, task = course_task
    _join_db(session, course, student)
    _join_db(session, course, student2)
    sess = _mk_session(session, student, task)
    _submit(client, task, sess.id, student)

    r = client.get(f"/api/tasks/{task.id}/submissions", cookies=_cookies(teacher))
    student_ids = [row["student_id"] for row in r.json()]
    assert student.id in student_ids
    assert student2.id not in student_ids


def test_list_submissions_member_student_returns_403(
    client: TestClient, student: User, course_task, session: Session
) -> None:
    """E-16：任务可读（成员）但非课程教师 → 403。"""
    course, task = course_task
    _join_db(session, course, student)
    r = client.get(f"/api/tasks/{task.id}/submissions", cookies=_cookies(student))
    assert r.status_code == 403


def test_list_submissions_non_member_returns_404(
    client: TestClient, student: User, course_task
) -> None:
    """E-16：任务不可读 → 404。"""
    course, task = course_task
    r = client.get(f"/api/tasks/{task.id}/submissions", cookies=_cookies(student))
    assert r.status_code == 404


def test_list_submissions_anonymous_returns_401(
    client: TestClient, course_task
) -> None:
    course, task = course_task
    assert client.get(f"/api/tasks/{task.id}/submissions").status_code == 401


# ---- GET /api/tasks/{task_id}/submissions/me ----


def test_get_my_submission(
    client: TestClient, student: User, course_task, session: Session
) -> None:
    course, task = course_task
    _join_db(session, course, student)
    sess = _mk_session(session, student, task)
    _submit(client, task, sess.id, student)

    r = client.get(
        f"/api/tasks/{task.id}/submissions/me", cookies=_cookies(student)
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["student_id"] == student.id
    assert body["session_id"] == sess.id
    assert body["task_id"] == task.id


def test_get_my_submission_not_submitted_returns_404(
    client: TestClient, student: User, course_task, session: Session
) -> None:
    course, task = course_task
    _join_db(session, course, student)
    r = client.get(
        f"/api/tasks/{task.id}/submissions/me", cookies=_cookies(student)
    )
    assert r.status_code == 404


def test_get_my_submission_non_member_returns_404(
    client: TestClient, student: User, course_task
) -> None:
    course, task = course_task
    r = client.get(
        f"/api/tasks/{task.id}/submissions/me", cookies=_cookies(student)
    )
    assert r.status_code == 404


def test_get_my_submission_anonymous_returns_401(
    client: TestClient, student: User, course_task, session: Session
) -> None:
    course, task = course_task
    _join_db(session, course, student)
    r = client.get(f"/api/tasks/{task.id}/submissions/me")
    assert r.status_code == 401
