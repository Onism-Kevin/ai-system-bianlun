"""S1-4 验收：feedback_forms 学生反馈表（sfb_test）。"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Course, FeedbackForm, Task, User


def _mk_task_with_student(session):
    t = User(username="teacher1", password_hash="x" * 60)
    session.add(t)
    session.flush()
    c = Course(teacher_id=t.id, name="课", invite_code="ABC123")
    session.add(c)
    session.flush()
    tk = Task(course_id=c.id, title="任务")
    session.add(tk)
    session.commit()
    stu = User(username="stu1", password_hash="y" * 60)
    session.add(stu)
    session.commit()
    return tk, stu


def test_create_read_and_optional_comment(session):
    tk, stu = _mk_task_with_student(session)
    f = FeedbackForm(
        task_id=tk.id,
        student_id=stu.id,
        scores={"难度": 3, "收获": 4},
    )
    session.add(f)
    session.commit()
    assert f.id is not None
    assert f.comment is None  # 可选
    assert f.submitted_at is not None

    fetched = session.query(FeedbackForm).filter_by(id=f.id).first()
    assert fetched.scores["收获"] == 4


def test_unique_task_student(session):
    tk, stu = _mk_task_with_student(session)
    f1 = FeedbackForm(task_id=tk.id, student_id=stu.id, scores={"a": 1})
    session.add(f1)
    session.commit()

    # 同一生同一任务第二份 → 拒（一生一任务一份反馈）
    f2 = FeedbackForm(task_id=tk.id, student_id=stu.id, scores={"a": 2})
    session.add(f2)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_cascade_on_task_and_user_delete(session):
    tk, stu = _mk_task_with_student(session)
    f = FeedbackForm(task_id=tk.id, student_id=stu.id, scores={"a": 1})
    session.add(f)
    session.commit()
    fid = f.id

    session.delete(tk)
    session.commit()
    assert session.query(FeedbackForm).filter_by(id=fid).first() is None

    # 再验 user 级联
    tk2 = Task(course_id=tk.course_id, title="任务2")
    session.add(tk2)
    session.commit()
    f2 = FeedbackForm(task_id=tk2.id, student_id=stu.id, scores={"a": 1})
    session.add(f2)
    session.commit()
    session.delete(stu)
    session.commit()
    assert session.query(FeedbackForm).filter_by(id=f2.id).first() is None
