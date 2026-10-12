"""S1-2 验收：courses / course_members 建表 + CRUD 冒烟（sfb_test）。"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Course, CourseMember, User


@pytest.fixture()
def teacher(session) -> User:
    t = User(username="teacher1", password_hash="x" * 60)
    session.add(t)
    session.commit()
    return t


def _new_course(teacher_id: int, code: str = "ABCD1234", **kw) -> Course:
    return Course(teacher_id=teacher_id, name="辩论入门", invite_code=code, **kw)


def test_course_create_read_update(session, teacher):
    c = _new_course(teacher.id, description="面向零基础", term="2026秋")
    session.add(c)
    session.commit()
    assert c.id is not None
    assert c.is_archived is False

    fetched = session.get(Course, c.id)
    assert fetched.name == "辩论入门"
    assert fetched.term == "2026秋"

    fetched.is_archived = True
    session.commit()
    session.refresh(fetched)
    assert fetched.is_archived is True


def test_invite_code_unique(session, teacher):
    session.add(_new_course(teacher.id, code="SAME0001"))
    session.commit()
    session.add(_new_course(teacher.id, code="SAME0001"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_term_nullable(session, teacher):
    c = _new_course(teacher.id)  # 不传 term
    session.add(c)
    session.commit()
    session.refresh(c)
    assert c.term is None


def test_member_join_and_dedup(session, teacher):
    c = _new_course(teacher.id)
    s = User(username="stu1", password_hash="y" * 60)
    session.add_all([c, s])
    session.commit()

    session.add(CourseMember(course_id=c.id, user_id=s.id))
    session.commit()
    assert session.query(CourseMember).filter_by(course_id=c.id).count() == 1

    # 重复加入被拒
    session.add(CourseMember(course_id=c.id, user_id=s.id))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_member_cascade_on_course_delete(session, teacher):
    c = _new_course(teacher.id)
    s = User(username="stu2", password_hash="y" * 60)
    session.add_all([c, s])
    session.commit()
    session.add(CourseMember(course_id=c.id, user_id=s.id))
    session.commit()
    cid = c.id

    session.delete(c)
    session.commit()
    assert session.query(CourseMember).filter_by(course_id=cid).count() == 0


def test_member_cascade_on_user_delete(session, teacher):
    c = _new_course(teacher.id)
    s = User(username="stu3", password_hash="y" * 60)
    session.add_all([c, s])
    session.commit()
    session.add(CourseMember(course_id=c.id, user_id=s.id))
    session.commit()
    sid = s.id

    session.delete(s)
    session.commit()
    assert session.query(CourseMember).filter_by(user_id=sid).count() == 0


def test_teacher_delete_restricted_with_course(session, teacher):
    """courses.teacher_id ON DELETE RESTRICT：有课教师账号不可直接删。"""
    c = _new_course(teacher.id)
    session.add(c)
    session.commit()

    session.delete(teacher)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    # 先删课，再删教师 → 放行
    session.delete(c)
    session.commit()
    session.delete(teacher)
    session.commit()
    assert session.get(User, teacher.id) is None
