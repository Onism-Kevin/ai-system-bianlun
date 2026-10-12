"""S1-3 验收：tasks / task_submissions 建表 + CRUD 冒烟（sfb_test）。

覆盖定稿契约：join_code 唯一且允许多 NULL、课程带任务删不掉（RESTRICT）、
提交双唯一键（task_id+session_id / task_id+student_id）、三类级联删除。
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Course, Task, TaskSubmission, TrainingSession, User


@pytest.fixture()
def course(session) -> Course:
    t = User(username="teacher1", password_hash="x" * 60)
    session.add(t)
    session.flush()
    c = Course(teacher_id=t.id, name="辩论课", invite_code="ABC123")
    session.add(c)
    session.commit()
    return c


def _mk_task(session, course_id: int, code: str | None = None, **kw) -> Task:
    tk = Task(course_id=course_id, title=kw.pop("title", "任务"), join_code=code, **kw)
    session.add(tk)
    session.commit()
    return tk


def _mk_session(session, owner_id: int, **kw) -> TrainingSession:
    s = TrainingSession(owner_id=owner_id, topic=kw.pop("topic", "辩题"), **kw)
    session.add(s)
    session.commit()
    return s


def test_task_create_read_update(session, course):
    tk = _mk_task(session, course.id, title="立论训练", material="背景材料")
    assert tk.id is not None
    assert tk.is_archived is False

    fetched = session.get(Task, tk.id)
    assert fetched.title == "立论训练"
    assert fetched.material == "背景材料"

    fetched.is_archived = True
    session.commit()
    session.refresh(fetched)
    assert fetched.is_archived is True


def test_join_code_unique_and_null_allowed(session, course):
    _mk_task(session, course.id, code="JOIN001")
    # 同码重复插入被拒（契约：任务级加入码唯一）
    dup = Task(course_id=course.id, title="撞码", join_code="JOIN001")
    session.add(dup)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    # 多个 NULL join_code 允许（MySQL UNIQUE 不约束 NULL）
    _mk_task(session, course.id, code=None)
    _mk_task(session, course.id, code=None)
    nulls = session.query(Task).filter_by(join_code=None).count()
    assert nulls == 2


def test_course_delete_restricted_with_task(session, course):
    tk = _mk_task(session, course.id)
    session.delete(course)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    # 先删任务再删课程 → 放行
    session.delete(tk)
    session.commit()
    session.delete(course)
    session.commit()


def test_submission_create_and_read(session, course):
    tk = _mk_task(session, course.id)
    stu = User(username="stu1", password_hash="y" * 60)
    session.add(stu)
    session.commit()
    s = _mk_session(session, stu.id)

    sub = TaskSubmission(student_id=stu.id, task_id=tk.id, session_id=s.id)
    session.add(sub)
    session.commit()
    assert sub.id is not None
    assert sub.submitted_at is not None
    assert session.get(TaskSubmission, sub.id).session_id == s.id


def test_submission_unique_task_session(session, course):
    tk = _mk_task(session, course.id)
    stu = User(username="stu1", password_hash="y" * 60)
    session.add(stu)
    session.commit()
    s = _mk_session(session, stu.id)
    session.add(TaskSubmission(student_id=stu.id, task_id=tk.id, session_id=s.id))
    session.commit()

    # 同一会话重复提交到同一任务 → 拒（契约 5.3）
    session.add(TaskSubmission(student_id=stu.id, task_id=tk.id, session_id=s.id))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_submission_unique_task_student(session, course):
    """换会话重提也被拒——S3-4 提交 API 必须 upsert 的直接依据。"""
    tk = _mk_task(session, course.id)
    stu = User(username="stu1", password_hash="y" * 60)
    session.add(stu)
    session.commit()
    s1 = _mk_session(session, stu.id, topic="第一次练习")
    s2 = _mk_session(session, stu.id, topic="重做练习")
    session.add(TaskSubmission(student_id=stu.id, task_id=tk.id, session_id=s1.id))
    session.commit()

    session.add(TaskSubmission(student_id=stu.id, task_id=tk.id, session_id=s2.id))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_submission_cascade_on_session_delete(session, course):
    tk = _mk_task(session, course.id)
    stu = User(username="stu1", password_hash="y" * 60)
    session.add(stu)
    session.commit()
    s = _mk_session(session, stu.id)
    sub = TaskSubmission(student_id=stu.id, task_id=tk.id, session_id=s.id)
    session.add(sub)
    session.commit()
    sid = sub.id

    session.delete(s)
    session.commit()
    # 用 query 绕过身份映射断言 DB 真实状态（conftest expire_on_commit=False，
    # session.get() 会返回陈旧对象而不查库）
    assert session.query(TaskSubmission).filter_by(id=sid).first() is None


def test_submission_cascade_on_task_delete(session, course):
    tk = _mk_task(session, course.id)
    stu = User(username="stu1", password_hash="y" * 60)
    session.add(stu)
    session.commit()
    s = _mk_session(session, stu.id)
    sub = TaskSubmission(student_id=stu.id, task_id=tk.id, session_id=s.id)
    session.add(sub)
    session.commit()
    sid = sub.id

    session.delete(tk)
    session.commit()
    assert session.query(TaskSubmission).filter_by(id=sid).first() is None


def test_submission_cascade_on_user_delete(session, course):
    tk = _mk_task(session, course.id)
    stu = User(username="stu1", password_hash="y" * 60)
    session.add(stu)
    session.commit()
    s = _mk_session(session, stu.id)
    sub = TaskSubmission(student_id=stu.id, task_id=tk.id, session_id=s.id)
    session.add(sub)
    session.commit()
    sid = sub.id

    session.delete(stu)
    session.commit()
    assert session.query(TaskSubmission).filter_by(id=sid).first() is None
