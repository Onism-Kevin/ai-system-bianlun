"""S3-2 验收：课程创建 + 成员 API（api.md:54-59，逐字对齐）。

覆盖：
- 建课：201 出参形状 + invite_code 字母表（剔 I/O/0/1）/长度 8；403 非 teacher；
  401 匿名；422 空 name
- 列表双视角：teacher→本人教的；student→已加入的；dual-role union
- 详情 invite_code 可见性：教师含码、学生**键缺席**、非成员 404
- PATCH：E-16 分层（可读非教师 403 / 不可读 404）
- 成员列表：仅学生行；E-16 分层
- join：正确码 200、错码 403（E-12）、幂等、401 匿名
"""
from __future__ import annotations

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


def _cookies(user: User) -> dict[str, str]:
    return {"access_token": create_access_token(user.id)}


def _join_db(session: Session, course: Course, student: User) -> None:
    session.add(CourseMember(course_id=course.id, user_id=student.id))
    session.commit()


@pytest.fixture()
def teacher(session: Session) -> User:
    return _mk_user(session, "teacher1", roles=("student", "teacher"))


@pytest.fixture()
def student(session: Session) -> User:
    return _mk_user(session, "student1")


# ---- POST /api/courses ----


def test_create_course_by_teacher_returns_201(
    client: TestClient, teacher: User
) -> None:
    r = client.post(
        "/api/courses",
        json={"name": "逻辑学", "description": "论证训练", "term": "2026秋"},
        cookies=_cookies(teacher),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "逻辑学"
    assert body["description"] == "论证训练"
    assert body["term"] == "2026秋"
    assert body["is_archived"] is False
    assert body["teacher_id"] == teacher.id
    assert "created_at" in body and "updated_at" in body


def test_create_course_invite_code_shape(client: TestClient, teacher: User) -> None:
    """invite_code：8 位、字母表剔 I/O/0/1（api.md:54）。"""
    r = client.post("/api/courses", json={"name": "课A"}, cookies=_cookies(teacher))
    assert r.status_code == 201, r.text
    code = r.json()["invite_code"]
    assert len(code) == CODE_LENGTH == 8
    assert set(code) <= set(CODE_ALPHABET)
    assert not set(code) & set("IO01")


def test_create_course_by_student_returns_403(
    client: TestClient, student: User
) -> None:
    r = client.post("/api/courses", json={"name": "课X"}, cookies=_cookies(student))
    assert r.status_code == 403


def test_create_course_by_admin_returns_403(
    client: TestClient, session: Session
) -> None:
    """admin 在 permissions §4 无 courses create 行 → 403。"""
    admin = _mk_user(session, "admin1", roles=("student", "admin"))
    r = client.post("/api/courses", json={"name": "课Y"}, cookies=_cookies(admin))
    assert r.status_code == 403


def test_create_course_anonymous_returns_401(client: TestClient) -> None:
    r = client.post("/api/courses", json={"name": "课Z"})
    assert r.status_code == 401


def test_create_course_empty_name_returns_422(
    client: TestClient, teacher: User
) -> None:
    r = client.post("/api/courses", json={"name": ""}, cookies=_cookies(teacher))
    assert r.status_code == 422


def test_generate_code_excludes_confusable_chars() -> None:
    """纯函数级：所有生成码都不含 I/O/0/1，长度固定 8。"""
    for _ in range(200):
        code = generate_code()
        assert len(code) == 8
        assert set(code) <= set(CODE_ALPHABET)


# ---- GET /api/courses 双视角 ----


def test_list_courses_teacher_only_own(
    client: TestClient, teacher: User, session: Session
) -> None:
    mine = _mk_course(session, teacher, "我的课")
    other = _mk_user(session, "teacher2", roles=("student", "teacher"))
    theirs = _mk_course(session, other, "别人的课")

    r = client.get("/api/courses", cookies=_cookies(teacher))
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert mine.id in ids and theirs.id not in ids


def test_list_courses_student_only_joined(
    client: TestClient, teacher: User, student: User, session: Session
) -> None:
    joined = _mk_course(session, teacher, "已加入课")
    other = _mk_user(session, "teacher3", roles=("student", "teacher"))
    not_joined = _mk_course(session, other, "未加入课")
    _join_db(session, joined, student)

    r = client.get("/api/courses", cookies=_cookies(student))
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert joined.id in ids and not_joined.id not in ids


def test_list_courses_dual_role_union(
    client: TestClient, teacher: User, session: Session
) -> None:
    dual = _mk_user(session, "dual1", roles=("student", "teacher"))
    taught = _mk_course(session, dual, "教的课")
    joined_by = _mk_course(session, teacher, "加入的课")
    _join_db(session, joined_by, dual)

    r = client.get("/api/courses", cookies=_cookies(dual))
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert taught.id in ids and joined_by.id in ids


def test_list_courses_never_exposes_invite_code(
    client: TestClient, teacher: User, session: Session
) -> None:
    """列表一律不含 invite_code（加入码由单课详情端点提供）。"""
    _mk_course(session, teacher, "列表课")
    r = client.get("/api/courses", cookies=_cookies(teacher))
    assert r.status_code == 200
    for c in r.json():
        assert "invite_code" not in c


# ---- GET /api/courses/{id} invite_code 可见性 ----


def test_get_course_teacher_includes_invite_code(
    client: TestClient, teacher: User, session: Session
) -> None:
    course = _mk_course(session, teacher, "详情课")
    r = client.get(f"/api/courses/{course.id}", cookies=_cookies(teacher))
    assert r.status_code == 200
    body = r.json()
    assert body["invite_code"] == course.invite_code


def test_get_course_student_omits_invite_code_key(
    client: TestClient, teacher: User, student: User, session: Session
) -> None:
    """学生响应**键完全缺席**（api.md:56 剔除，不是 null）。"""
    course = _mk_course(session, teacher, "学生可见课")
    _join_db(session, course, student)
    r = client.get(f"/api/courses/{course.id}", cookies=_cookies(student))
    assert r.status_code == 200
    assert "invite_code" not in r.json()


def test_get_course_non_member_returns_404(
    client: TestClient, teacher: User, student: User, session: Session
) -> None:
    course = _mk_course(session, teacher, "非成员课")
    r = client.get(f"/api/courses/{course.id}", cookies=_cookies(student))
    assert r.status_code == 404


def test_get_course_anonymous_returns_401(
    client: TestClient, teacher: User, session: Session
) -> None:
    course = _mk_course(session, teacher, "匿名课")
    assert client.get(f"/api/courses/{course.id}").status_code == 401


# ---- PATCH /api/courses/{id}（E-16 分层）----


def test_patch_course_by_teacher_updates_fields(
    client: TestClient, teacher: User, session: Session
) -> None:
    course = _mk_course(session, teacher, "原名")
    r = client.patch(
        f"/api/courses/{course.id}",
        json={"name": "新名", "term": "2027春", "is_archived": True},
        cookies=_cookies(teacher),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "新名"
    assert body["term"] == "2027春"
    assert body["is_archived"] is True
    assert body["invite_code"] == course.invite_code  # 教师视角带码


def test_patch_course_by_member_student_returns_403(
    client: TestClient, teacher: User, student: User, session: Session
) -> None:
    """E-16：可读（成员）但非教师 → 403。"""
    course = _mk_course(session, teacher, "成员可读课")
    _join_db(session, course, student)
    r = client.patch(
        f"/api/courses/{course.id}", json={"name": "改"}, cookies=_cookies(student)
    )
    assert r.status_code == 403


def test_patch_course_by_non_member_returns_404(
    client: TestClient, teacher: User, student: User, session: Session
) -> None:
    """E-16：不可读 → 404（存在性隐藏）。"""
    course = _mk_course(session, teacher, "不可读课")
    r = client.patch(
        f"/api/courses/{course.id}", json={"name": "改"}, cookies=_cookies(student)
    )
    assert r.status_code == 404


def test_patch_course_anonymous_returns_401(
    client: TestClient, teacher: User, session: Session
) -> None:
    course = _mk_course(session, teacher, "匿名改课")
    r = client.patch(f"/api/courses/{course.id}", json={"name": "改"})
    assert r.status_code == 401


def test_patch_course_name_too_long_returns_422(
    client: TestClient, teacher: User, session: Session
) -> None:
    course = _mk_course(session, teacher, "长名课")
    r = client.patch(
        f"/api/courses/{course.id}", json={"name": "x" * 101}, cookies=_cookies(teacher)
    )
    assert r.status_code == 422


# ---- GET /api/courses/{id}/members ----


def test_list_members_by_teacher_returns_student_rows_only(
    client: TestClient, teacher: User, student: User, session: Session
) -> None:
    course = _mk_course(session, teacher, "成员课")
    _join_db(session, course, student)

    r = client.get(f"/api/courses/{course.id}/members", cookies=_cookies(teacher))
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["user_id"] == student.id
    assert rows[0]["username"] == student.username
    assert "joined_at" in rows[0]
    assert all(row["user_id"] != teacher.id for row in rows), "members 仅学生行"


def test_list_members_by_member_student_returns_403(
    client: TestClient, teacher: User, student: User, session: Session
) -> None:
    course = _mk_course(session, teacher, "成员自读课")
    _join_db(session, course, student)
    r = client.get(f"/api/courses/{course.id}/members", cookies=_cookies(student))
    assert r.status_code == 403


def test_list_members_by_non_member_returns_404(
    client: TestClient, teacher: User, student: User, session: Session
) -> None:
    course = _mk_course(session, teacher, "非成员读成员课")
    r = client.get(f"/api/courses/{course.id}/members", cookies=_cookies(student))
    assert r.status_code == 404


def test_list_members_anonymous_returns_401(
    client: TestClient, teacher: User, session: Session
) -> None:
    course = _mk_course(session, teacher, "匿名成员课")
    assert client.get(f"/api/courses/{course.id}/members").status_code == 401


# ---- POST /api/courses/join ----


def test_join_course_correct_code_returns_200(
    client: TestClient, teacher: User, student: User, session: Session
) -> None:
    course = _mk_course(session, teacher, "加入课")
    r = client.post(
        "/api/courses/join",
        json={"invite_code": course.invite_code},
        cookies=_cookies(student),
    )
    assert r.status_code == 200, r.text
    assert r.json()["course_id"] == course.id


def test_join_course_wrong_code_returns_403(
    client: TestClient, student: User
) -> None:
    """E-12：错码 → 403（不暴露存在性）。"""
    r = client.post(
        "/api/courses/join",
        json={"invite_code": "ZZZZZZZZ"},
        cookies=_cookies(student),
    )
    assert r.status_code == 403


def test_join_course_is_idempotent(
    client: TestClient, teacher: User, student: User, session: Session
) -> None:
    course = _mk_course(session, teacher, "幂等加入课")
    for _ in range(2):
        r = client.post(
            "/api/courses/join",
            json={"invite_code": course.invite_code},
            cookies=_cookies(student),
        )
        assert r.status_code == 200
        assert r.json()["course_id"] == course.id


def test_join_course_anonymous_returns_401(client: TestClient) -> None:
    r = client.post("/api/courses/join", json={"invite_code": "ABCD2345"})
    assert r.status_code == 401


def test_join_course_makes_student_visible_in_list(
    client: TestClient, teacher: User, student: User, session: Session
) -> None:
    course = _mk_course(session, teacher, "加入后可见课")
    client.post(
        "/api/courses/join",
        json={"invite_code": course.invite_code},
        cookies=_cookies(student),
    )
    r = client.get("/api/courses", cookies=_cookies(student))
    assert r.status_code == 200
    assert course.id in [c["id"] for c in r.json()]
