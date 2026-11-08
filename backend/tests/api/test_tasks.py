"""S3-3 验收：任务创建 + 加入码 + join API（api.md:60-64，逐字对齐）。

覆盖（5 端点 + E-16 分层 + E-12 加入码）：
- 建任务：201 + join_code 形状；need_join_code=false → null；403 非课程教师；
  404 课程不可读；401 匿名；422 空/超长 title
- 列表：教师/学生视角；排除归档；不含 join_code；404 不可读；401 匿名
- 详情：教师含 join_code；学生键缺席；404 非成员；401 匿名
- PATCH：教师更新；学生成员 403；非成员 404；401 匿名；422 超长 title
- join：正确码 200；错码 403；过期 410；无码 403；幂等；401 匿名；
  加入后授予课程成员（可读任务）
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.codes import CODE_ALPHABET, CODE_LENGTH, generate_code
from app.core.security import create_access_token
from app.models.course import Course, CourseMember
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


def _join_db(session: Session, course: Course, student: User) -> None:
    session.add(CourseMember(course_id=course.id, user_id=student.id))
    session.commit()


def _cookies(user: User) -> dict[str, str]:
    return {"access_token": create_access_token(user.id)}


def _create_task_via_api(
    client: TestClient, teacher: User, course: Course, body: dict
) -> dict:
    r = client.post(
        f"/api/courses/{course.id}/tasks", json=body, cookies=_cookies(teacher)
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def teacher(session: Session) -> User:
    return _mk_user(session, "teacher1", roles=("student", "teacher"))


@pytest.fixture()
def student(session: Session) -> User:
    return _mk_user(session, "student1")


@pytest.fixture()
def course(session: Session, teacher: User) -> Course:
    return _mk_course(session, teacher, "任务课")


# ---- POST /api/courses/{course_id}/tasks ----


def test_create_task_with_join_code(
    client: TestClient, teacher: User, course: Course
) -> None:
    body = _create_task_via_api(
        client, teacher, course,
        {"title": "辩论任务", "material": "议题材料", "need_join_code": True},
    )
    assert body["title"] == "辩论任务"
    assert body["material"] == "议题材料"
    assert body["course_id"] == course.id
    assert body["is_archived"] is False
    code = body["join_code"]
    assert code is not None
    assert len(code) == CODE_LENGTH == 8
    assert set(code) <= set(CODE_ALPHABET)
    assert not set(code) & set("IO01")


def test_create_task_without_join_code(
    client: TestClient, teacher: User, course: Course
) -> None:
    body = _create_task_via_api(
        client, teacher, course, {"title": "无需加入码任务"}
    )
    assert body["join_code"] is None


def test_create_task_by_member_student_returns_403(
    client: TestClient, teacher: User, student: User, course: Course, session: Session
) -> None:
    """E-16：课程可读（成员）但非课程教师 → 403。"""
    _join_db(session, course, student)
    r = client.post(
        f"/api/courses/{course.id}/tasks",
        json={"title": "学生建任务"},
        cookies=_cookies(student),
    )
    assert r.status_code == 403


def test_create_task_by_non_member_returns_404(
    client: TestClient, teacher: User, student: User, course: Course
) -> None:
    """E-16：课程不可读 → 404。"""
    r = client.post(
        f"/api/courses/{course.id}/tasks",
        json={"title": "非成员建任务"},
        cookies=_cookies(student),
    )
    assert r.status_code == 404


def test_create_task_anonymous_returns_401(
    client: TestClient, teacher: User, course: Course
) -> None:
    r = client.post(f"/api/courses/{course.id}/tasks", json={"title": "匿名建任务"})
    assert r.status_code == 401


def test_create_task_empty_title_returns_422(
    client: TestClient, teacher: User, course: Course
) -> None:
    r = client.post(
        f"/api/courses/{course.id}/tasks", json={"title": ""}, cookies=_cookies(teacher)
    )
    assert r.status_code == 422


def test_create_task_title_too_long_returns_422(
    client: TestClient, teacher: User, course: Course
) -> None:
    r = client.post(
        f"/api/courses/{course.id}/tasks",
        json={"title": "x" * 121},
        cookies=_cookies(teacher),
    )
    assert r.status_code == 422


def test_create_task_unknown_course_returns_404(
    client: TestClient, teacher: User
) -> None:
    r = client.post(
        f"/api/courses/999999/tasks", json={"title": "不存在课程"}, cookies=_cookies(teacher)
    )
    assert r.status_code == 404


# ---- GET /api/courses/{course_id}/tasks ----


def test_list_tasks_teacher_view(
    client: TestClient, teacher: User, course: Course
) -> None:
    _create_task_via_api(client, teacher, course, {"title": "任务A"})
    _create_task_via_api(client, teacher, course, {"title": "任务B"})
    r = client.get(f"/api/courses/{course.id}/tasks", cookies=_cookies(teacher))
    assert r.status_code == 200
    titles = [t["title"] for t in r.json()]
    assert titles == ["任务A", "任务B"]
    # S3-F2-B：教师视角列表含 join_code 键（无码任务值为 null）
    assert all("join_code" in t for t in r.json())


def test_list_tasks_student_member_view(
    client: TestClient, teacher: User, student: User, course: Course, session: Session
) -> None:
    _join_db(session, course, student)
    _create_task_via_api(
        client, teacher, course, {"title": "成员可见任务", "need_join_code": True}
    )
    r = client.get(f"/api/courses/{course.id}/tasks", cookies=_cookies(student))
    assert r.status_code == 200
    assert [t["title"] for t in r.json()] == ["成员可见任务"]
    # S3-F2-B：学生视角列表**不含** join_code 键（不泄露）
    assert all("join_code" not in t for t in r.json())


def test_list_tasks_non_member_returns_404(
    client: TestClient, teacher: User, student: User, course: Course
) -> None:
    r = client.get(f"/api/courses/{course.id}/tasks", cookies=_cookies(student))
    assert r.status_code == 404


def test_list_tasks_anonymous_returns_401(
    client: TestClient, teacher: User, course: Course
) -> None:
    assert client.get(f"/api/courses/{course.id}/tasks").status_code == 401


def test_list_tasks_excludes_archived(
    client: TestClient, teacher: User, course: Course
) -> None:
    active = _create_task_via_api(client, teacher, course, {"title": "活跃任务"})
    archived = _create_task_via_api(client, teacher, course, {"title": "归档任务"})
    r = client.patch(
        f"/api/tasks/{archived['id']}",
        json={"is_archived": True},
        cookies=_cookies(teacher),
    )
    assert r.status_code == 200
    r = client.get(f"/api/courses/{course.id}/tasks", cookies=_cookies(teacher))
    ids = [t["id"] for t in r.json()]
    assert active["id"] in ids and archived["id"] not in ids


def test_list_tasks_teacher_sees_join_code_value(
    client: TestClient, teacher: User, student: User, course: Course, session: Session
) -> None:
    """S3-F2-B：教师列表返回 join_code 实际值；学生列表不返回该键。"""
    created = _create_task_via_api(
        client, teacher, course, {"title": "带码任务", "need_join_code": True}
    )
    assert created["join_code"] is not None

    # 教师视角：返回 join_code 实际值
    r = client.get(f"/api/courses/{course.id}/tasks", cookies=_cookies(teacher))
    assert r.status_code == 200
    row = next(t for t in r.json() if t["id"] == created["id"])
    assert row["join_code"] == created["join_code"]

    # 学生视角（成员）：不含 join_code 键
    _join_db(session, course, student)
    r = client.get(f"/api/courses/{course.id}/tasks", cookies=_cookies(student))
    assert r.status_code == 200
    assert all("join_code" not in t for t in r.json())


# ---- GET /api/tasks/{id} ----


def test_get_task_teacher_includes_join_code(
    client: TestClient, teacher: User, course: Course
) -> None:
    created = _create_task_via_api(
        client, teacher, course, {"title": "教师详情", "need_join_code": True}
    )
    r = client.get(f"/api/tasks/{created['id']}", cookies=_cookies(teacher))
    assert r.status_code == 200
    assert r.json()["join_code"] == created["join_code"]


def test_get_task_student_omits_join_code_key(
    client: TestClient, teacher: User, student: User, course: Course, session: Session
) -> None:
    """学生响应 join_code 键完全缺席（不是 null）。"""
    _join_db(session, course, student)
    created = _create_task_via_api(
        client, teacher, course, {"title": "学生详情", "need_join_code": True}
    )
    r = client.get(f"/api/tasks/{created['id']}", cookies=_cookies(student))
    assert r.status_code == 200
    assert "join_code" not in r.json()


def test_get_task_non_member_returns_404(
    client: TestClient, teacher: User, student: User, course: Course
) -> None:
    created = _create_task_via_api(client, teacher, course, {"title": "非成员详情"})
    r = client.get(f"/api/tasks/{created['id']}", cookies=_cookies(student))
    assert r.status_code == 404


def test_get_task_anonymous_returns_401(
    client: TestClient, teacher: User, course: Course
) -> None:
    created = _create_task_via_api(client, teacher, course, {"title": "匿名详情"})
    assert client.get(f"/api/tasks/{created['id']}").status_code == 401


# ---- PATCH /api/tasks/{id} ----


def test_patch_task_by_teacher(
    client: TestClient, teacher: User, course: Course
) -> None:
    created = _create_task_via_api(client, teacher, course, {"title": "原名"})
    new_deadline = datetime.now() + timedelta(days=7)
    r = client.patch(
        f"/api/tasks/{created['id']}",
        json={
            "title": "新名",
            "deadline": new_deadline.isoformat(),
            "is_archived": True,
        },
        cookies=_cookies(teacher),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "新名"
    assert body["is_archived"] is True
    assert body["deadline"] is not None


def test_patch_task_by_member_student_returns_403(
    client: TestClient, teacher: User, student: User, course: Course, session: Session
) -> None:
    _join_db(session, course, student)
    created = _create_task_via_api(client, teacher, course, {"title": "成员可读"})
    r = client.patch(
        f"/api/tasks/{created['id']}", json={"title": "改"}, cookies=_cookies(student)
    )
    assert r.status_code == 403


def test_patch_task_by_non_member_returns_404(
    client: TestClient, teacher: User, student: User, course: Course
) -> None:
    created = _create_task_via_api(client, teacher, course, {"title": "非成员改"})
    r = client.patch(
        f"/api/tasks/{created['id']}", json={"title": "改"}, cookies=_cookies(student)
    )
    assert r.status_code == 404


def test_patch_task_anonymous_returns_401(
    client: TestClient, teacher: User, course: Course
) -> None:
    created = _create_task_via_api(client, teacher, course, {"title": "匿名改"})
    r = client.patch(f"/api/tasks/{created['id']}", json={"title": "改"})
    assert r.status_code == 401


def test_patch_task_title_too_long_returns_422(
    client: TestClient, teacher: User, course: Course
) -> None:
    created = _create_task_via_api(client, teacher, course, {"title": "长名"})
    r = client.patch(
        f"/api/tasks/{created['id']}", json={"title": "x" * 121}, cookies=_cookies(teacher)
    )
    assert r.status_code == 422


def test_patch_task_clears_deadline(
    client: TestClient, teacher: User, course: Course
) -> None:
    """显式传 deadline=null 可清空截止时间。"""
    created = _create_task_via_api(
        client, teacher, course,
        {"title": "有截止", "deadline": (datetime.now() + timedelta(days=3)).isoformat()},
    )
    assert created["deadline"] is not None
    r = client.patch(
        f"/api/tasks/{created['id']}",
        json={"deadline": None},
        cookies=_cookies(teacher),
    )
    assert r.status_code == 200
    assert r.json()["deadline"] is None


# ---- POST /api/tasks/{id}/join ----


def test_join_task_correct_code_returns_200(
    client: TestClient, teacher: User, student: User, course: Course
) -> None:
    created = _create_task_via_api(
        client, teacher, course, {"title": "加入任务", "need_join_code": True}
    )
    r = client.post(
        f"/api/tasks/{created['id']}/join",
        json={"join_code": created["join_code"]},
        cookies=_cookies(student),
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"course_id": course.id, "task_id": created["id"]}


def test_join_task_wrong_code_returns_403(
    client: TestClient, teacher: User, student: User, course: Course
) -> None:
    """E-12：错码 → 403（不暴露存在性）。"""
    created = _create_task_via_api(
        client, teacher, course, {"title": "错码任务", "need_join_code": True}
    )
    r = client.post(
        f"/api/tasks/{created['id']}/join",
        json={"join_code": "ZZZZZZZZ"},
        cookies=_cookies(student),
    )
    assert r.status_code == 403


def test_join_task_expired_returns_410(
    client: TestClient, teacher: User, student: User, course: Course
) -> None:
    """已过 deadline → 410（契约 S3-3 验收指定）。"""
    past = (datetime.now() - timedelta(days=1)).isoformat()
    created = _create_task_via_api(
        client, teacher, course,
        {"title": "过期任务", "need_join_code": True, "deadline": past},
    )
    r = client.post(
        f"/api/tasks/{created['id']}/join",
        json={"join_code": created["join_code"]},
        cookies=_cookies(student),
    )
    assert r.status_code == 410


def test_join_task_without_join_code_returns_403(
    client: TestClient, teacher: User, student: User, course: Course
) -> None:
    """need_join_code=false 的任务无码 → 任何 join 都 403。"""
    created = _create_task_via_api(
        client, teacher, course, {"title": "无码任务"}
    )
    assert created["join_code"] is None
    r = client.post(
        f"/api/tasks/{created['id']}/join",
        json={"join_code": "ABCD2345"},
        cookies=_cookies(student),
    )
    assert r.status_code == 403


def test_join_task_is_idempotent(
    client: TestClient, teacher: User, student: User, course: Course
) -> None:
    created = _create_task_via_api(
        client, teacher, course, {"title": "幂等加入", "need_join_code": True}
    )
    for _ in range(2):
        r = client.post(
            f"/api/tasks/{created['id']}/join",
            json={"join_code": created["join_code"]},
            cookies=_cookies(student),
        )
        assert r.status_code == 200
        assert r.json() == {"course_id": course.id, "task_id": created["id"]}


def test_join_task_anonymous_returns_401(
    client: TestClient, teacher: User, course: Course
) -> None:
    created = _create_task_via_api(
        client, teacher, course, {"title": "匿名加入", "need_join_code": True}
    )
    r = client.post(
        f"/api/tasks/{created['id']}/join", json={"join_code": created["join_code"]}
    )
    assert r.status_code == 401


def test_join_task_grants_course_membership(
    client: TestClient, teacher: User, student: User, course: Course
) -> None:
    """join 入组 = 加入 course_members → 学生随后可读任务（§9 Q1）。"""
    created = _create_task_via_api(
        client, teacher, course, {"title": "入组任务", "need_join_code": True}
    )
    # 加入前：学生非成员 → 404
    assert (
        client.get(f"/api/tasks/{created['id']}", cookies=_cookies(student)).status_code
        == 404
    )
    client.post(
        f"/api/tasks/{created['id']}/join",
        json={"join_code": created["join_code"]},
        cookies=_cookies(student),
    )
    # 加入后：可读 → 200
    r = client.get(f"/api/tasks/{created['id']}", cookies=_cookies(student))
    assert r.status_code == 200
    assert "join_code" not in r.json()
