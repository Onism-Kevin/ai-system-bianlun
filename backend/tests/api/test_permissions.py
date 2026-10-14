"""S2-2：can_read_session 判定函数单测（DB 底座复用 api conftest）。

覆盖 permissions §5.6 / errata E-15 的 owner 优先级与教师可见集合
（consistency_check #8 的校验路径落地验证）。
"""
from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"  # 必须在导入 app 包之前写入

from app.api.deps import can_read_session  # noqa: E402
from app.models import Course, Task, TrainingSession, User, UserRole  # noqa: E402


def _mk_user(db, username, roles=("student",)):
    user = User(username=username, password_hash="x", is_active=True)
    db.add(user)
    db.flush()
    for role in roles:
        db.add(UserRole(user_id=user.id, role=role))
    db.flush()
    return user


def _mk_course(db, teacher, name):
    course = Course(teacher_id=teacher.id, name=name, invite_code=f"C{teacher.id}{name[:1]}")
    db.add(course)
    db.flush()
    return course


def _mk_task(db, course, title):
    task = Task(course_id=course.id, title=title)
    db.add(task)
    db.flush()
    return task


def _mk_session(db, owner, *, visibility="private", task_id=None, topic="测试议题"):
    session = TrainingSession(
        owner_id=owner.id,
        topic=topic,
        visibility=visibility,
        task_id=task_id,
        status="waiting",
    )
    db.add(session)
    db.flush()
    return session


def test_owner_sees_own_private_session(session):
    """E-15/§5.6 ①：owner 本人（含 teacher 角色）可见自己的 private 会话
    （教师个人训练页，consistency_check #8）。"""
    teacher = _mk_user(session, "t_owner", roles=("teacher",))
    sess = _mk_session(session, teacher, visibility="private")
    assert can_read_session(session, teacher, sess) is True


def test_non_owner_teacher_private_is_hidden(session):
    """permissions:64：private 会话对非 owner 教师 → 404（存在性隐藏）。"""
    t1 = _mk_user(session, "t1", roles=("teacher",))
    t2 = _mk_user(session, "t2", roles=("teacher",))
    sess = _mk_session(session, t1, visibility="private")
    assert can_read_session(session, t2, sess) is False


def test_teacher_sees_task_session_of_own_course(session):
    """permissions §5.2：教师可见集合=本人课程的全部 task 会话。"""
    t1 = _mk_user(session, "t1", roles=("teacher",))
    c1 = _mk_course(session, t1, "课程A")
    k1 = _mk_task(session, c1, "任务A")
    student = _mk_user(session, "s1")
    sess = _mk_session(session, student, visibility="task", task_id=k1.id)
    assert can_read_session(session, t1, sess) is True


def test_teacher_cannot_see_task_session_of_other_course(session):
    """非本人课程的 task 会话：其他教师不可见（403/404 由端点层映射）。"""
    t1 = _mk_user(session, "t1", roles=("teacher",))
    t2 = _mk_user(session, "t2", roles=("teacher",))
    c2 = _mk_course(session, t2, "课程B")
    k2 = _mk_task(session, c2, "任务B")
    student = _mk_user(session, "s1")
    sess = _mk_session(session, student, visibility="task", task_id=k2.id)
    assert can_read_session(session, t1, sess) is False


def test_student_cannot_see_others_task_session(session):
    """学生可见集合=本人会话（owner 规则）；他人 task 会话不可见。"""
    t1 = _mk_user(session, "t1", roles=("teacher",))
    c1 = _mk_course(session, t1, "课程A")
    k1 = _mk_task(session, c1, "任务A")
    s1 = _mk_user(session, "s1")
    s2 = _mk_user(session, "s2")
    sess = _mk_session(session, s1, visibility="task", task_id=k1.id)
    assert can_read_session(session, s2, sess) is False
    assert can_read_session(session, s1, sess) is True  # owner 规则兜底


def test_admin_non_owner_task_session_is_hidden(session):
    """admin 为预留枚举（permissions §2：首版无管理员功能）：非 owner task
    会话不因 admin 角色放行（无课程归属，自然 False）。"""
    t1 = _mk_user(session, "t1", roles=("teacher",))
    c1 = _mk_course(session, t1, "课程A")
    k1 = _mk_task(session, c1, "任务A")
    admin = _mk_user(session, "admin1", roles=("admin",))
    student = _mk_user(session, "s1")
    sess = _mk_session(session, student, visibility="task", task_id=k1.id)
    assert can_read_session(session, admin, sess) is False


def test_task_session_without_role_is_hidden(session):
    """无角色行账号按 student 兜底（list_user_roles）：他人 task 会话不可见。"""
    t1 = _mk_user(session, "t1", roles=("teacher",))
    c1 = _mk_course(session, t1, "课程A")
    k1 = _mk_task(session, c1, "任务A")
    student = _mk_user(session, "s1")
    plain = _mk_user(session, "plain", roles=())
    sess = _mk_session(session, student, visibility="task", task_id=k1.id)
    assert can_read_session(session, plain, sess) is False


def test_task_session_with_missing_task_id_is_hidden(session):
    """E-2 保证正常数据 task⇔task_id 非空；防御性分支：缺 task_id 不可读。"""
    t1 = _mk_user(session, "t1", roles=("teacher",))
    student = _mk_user(session, "s1")
    sess = _mk_session(session, student, visibility="task", task_id=None)
    assert can_read_session(session, t1, sess) is False
