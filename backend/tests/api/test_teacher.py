"""S3-5 验收：班级汇总统计 API（api.md:70，GET /api/courses/{course_id}/summary）。

覆盖：
- 教师：无 task_id → submitted_count=课程全部提交数，total_students=成员数；
  有 task_id → 该任务提交数；task_id 非本课程 → 0；top_pending_verification=[]
  （errata E-29）
- 成员学生 → 403；非成员 → 404；匿名 → 401
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.codes import generate_code
from app.core.security import create_access_token
from app.models.course import Course, CourseMember
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


def _submit_db(session: Session, task: Task, student: User) -> None:
    """落一条提交记录（TaskSubmission.session_id NOT NULL → 先建会话）。"""
    sess = TrainingSession(
        owner_id=student.id, topic="议题", visibility="task",
        task_id=task.id, status="waiting",
    )
    session.add(sess)
    session.flush()
    session.add(
        TaskSubmission(student_id=student.id, task_id=task.id, session_id=sess.id)
    )
    session.commit()


def _cookies(user: User) -> dict[str, str]:
    return {"access_token": create_access_token(user.id)}


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
def course_two_tasks(session: Session, teacher: User, student: User, student2: User):
    """课程 2 成员 2 任务；student 提交 task1，student2 提交 task2。"""
    course = _mk_course(session, teacher, "汇总课")
    task1 = _mk_task(session, course, "任务1")
    task2 = _mk_task(session, course, "任务2")
    _join_db(session, course, student)
    _join_db(session, course, student2)
    _submit_db(session, task1, student)
    _submit_db(session, task2, student2)
    return course, task1, task2


# ---- GET /api/courses/{course_id}/summary ----


def test_summary_course_level(
    client: TestClient, teacher: User, course_two_tasks
) -> None:
    course, task1, task2 = course_two_tasks
    r = client.get(f"/api/courses/{course.id}/summary", cookies=_cookies(teacher))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["submitted_count"] == 2
    assert body["total_students"] == 2
    assert body["top_pending_verification"] == []  # E-29


def test_summary_task_level(
    client: TestClient, teacher: User, course_two_tasks
) -> None:
    course, task1, task2 = course_two_tasks
    r = client.get(
        f"/api/courses/{course.id}/summary?task_id={task1.id}",
        cookies=_cookies(teacher),
    )
    assert r.status_code == 200
    assert r.json()["submitted_count"] == 1

    r = client.get(
        f"/api/courses/{course.id}/summary?task_id={task2.id}",
        cookies=_cookies(teacher),
    )
    assert r.status_code == 200
    assert r.json()["submitted_count"] == 1


def test_summary_task_not_in_course_returns_zero(
    client: TestClient, teacher: User, student: User, session: Session, course_two_tasks
) -> None:
    course, task1, task2 = course_two_tasks
    other_course = _mk_course(session, teacher, "其他课")
    other_task = _mk_task(session, other_course, "其他任务")
    r = client.get(
        f"/api/courses/{course.id}/summary?task_id={other_task.id}",
        cookies=_cookies(teacher),
    )
    assert r.status_code == 200
    assert r.json()["submitted_count"] == 0


def test_summary_member_student_returns_403(
    client: TestClient, student: User, course_two_tasks
) -> None:
    """E-16：课程可读（成员）但非课程教师 → 403。"""
    course, task1, task2 = course_two_tasks
    r = client.get(f"/api/courses/{course.id}/summary", cookies=_cookies(student))
    assert r.status_code == 403


def test_summary_non_member_returns_404(
    client: TestClient, student2: User, course_two_tasks, session: Session
) -> None:
    """E-16：课程不可读 → 404。"""
    course, task1, task2 = course_two_tasks
    # student2 已加入 → 是成员 → 403。用未加入的第三个学生测 404。
    stranger = _mk_user(session, "stranger")
    r = client.get(f"/api/courses/{course.id}/summary", cookies=_cookies(stranger))
    assert r.status_code == 404


def test_summary_anonymous_returns_401(
    client: TestClient, course_two_tasks
) -> None:
    course, task1, task2 = course_two_tasks
    assert client.get(f"/api/courses/{course.id}/summary").status_code == 401
