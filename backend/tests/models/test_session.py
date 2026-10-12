"""S1-3 验收：sessions 建表 + CRUD + 应用层 visibility 校验（sfb_test）。

errata E-2 定稿：DB 无 CHECK，`validate_session_visibility()` 是唯一校验入口。
本文件对该函数与 ORM 行为都做断言。
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    Course,
    Task,
    TrainingSession,
    User,
    validate_session_visibility,
)


@pytest.fixture()
def course(session) -> Course:
    t = User(username="teacher1", password_hash="x" * 60)
    session.add(t)
    session.flush()
    c = Course(teacher_id=t.id, name="辩论课", invite_code="ABC123")
    session.add(c)
    session.commit()
    return c


@pytest.fixture()
def task(session, course) -> Task:
    tk = Task(course_id=course.id, title="任务A")
    session.add(tk)
    session.commit()
    return tk


@pytest.fixture()
def student(session) -> User:
    stu = User(username="stu1", password_hash="y" * 60)
    session.add(stu)
    session.commit()
    return stu


# ---- validate_session_visibility 应用层校验（errata E-2 验收点） ----


def test_validator_rejects_task_without_task_id():
    with pytest.raises(ValueError, match="必须关联任务"):
        validate_session_visibility("task", None)


def test_validator_rejects_private_with_task_id():
    with pytest.raises(ValueError, match="不能关联任务"):
        validate_session_visibility("private", 42)


def test_validator_accepts_valid_pairs():
    validate_session_visibility("task", 42)  # 不抛
    validate_session_visibility("private", None)  # 不抛


# ---- ORM 行为 ----


def test_private_session_create_read_update(session, student):
    s = TrainingSession(owner_id=student.id, topic="自由辩题")
    session.add(s)
    session.commit()
    assert s.visibility == "private"  # server_default
    assert s.status == "waiting"  # server_default

    fetched = session.get(TrainingSession, s.id)
    fetched.status = "generating"
    session.commit()
    session.refresh(fetched)
    assert fetched.status == "generating"


def test_task_session_create(session, student, task):
    validate_session_visibility("task", task.id)  # 先过应用层校验（API 层的职责）
    s = TrainingSession(owner_id=student.id, topic="任务辩题", visibility="task", task_id=task.id)
    session.add(s)
    session.commit()
    assert s.visibility == "task"
    assert s.task_id == task.id


def test_task_session_cascade_on_task_delete(session, student, task):
    s = TrainingSession(owner_id=student.id, topic="任务辩题", visibility="task", task_id=task.id)
    session.add(s)
    session.commit()
    sid = s.id

    session.delete(task)
    session.commit()
    # query 绕过身份映射（expire_on_commit=False 下 session.get() 返回陈旧对象）
    assert session.query(TrainingSession).filter_by(id=sid).first() is None


def test_session_cascade_on_owner_delete(session, student):
    s1 = TrainingSession(owner_id=student.id, topic="练习一")
    s2 = TrainingSession(owner_id=student.id, topic="练习二")
    session.add_all([s1, s2])
    session.commit()
    ids = [s1.id, s2.id]

    session.delete(student)
    session.commit()
    for sid in ids:
        assert session.query(TrainingSession).filter_by(id=sid).first() is None


def test_status_enum_values(session, student):
    """五态枚举全部可写入（与 S2-2 状态机一致）。"""
    s = TrainingSession(owner_id=student.id, topic="状态遍历")
    session.add(s)
    session.commit()
    for state in ("waiting", "generating", "paused", "finished", "failed"):
        s.status = state
        session.commit()
        session.refresh(s)
        assert s.status == state


def test_topic_required(session, student):
    s = TrainingSession(owner_id=student.id, topic=None)
    session.add(s)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
