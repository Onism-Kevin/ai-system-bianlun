"""S2-3：sessions 端点测试（api.md:28-30 + 用户 2026-10-14 六条约束 + 审追问）。

覆盖清单（用户要求的最小集：创建 → 404 越权 → PATCH 非 owner 404 →
PATCH status 拒；外加 E-2 422、分层 403、task 归属 404、存在性隐藏）：
- 创建：201 + 初始 waiting + 默认 private/task_id=None；401 未登录；
  mode/max_turns 运行参数被接受；topic/visibility 校验 422；
  E-2 双向违反 422；task 不存在/已归档 422；task 跨用户引用 404
  （课程教师本人/成员可引用）；task 归属教师本人路径 201。
- GET：owner 200（七字段平铺）；不存在 404；private 非 owner（学生/教师）
  404；task 会话课程教师 200、其他教师 404。
- PATCH：status 字段 422（状态机独占）；非 owner 学生 404；课程教师
  对学生 task 会话 403（分层裁定）；owner 改 topic 200（平铺出参，
  E-17）；E-2 合并违反 422；task→private 切换 200；task 跨用户引用
  404；不存在 404；未知字段 422。
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.course import Course, CourseMember
from app.models.session import TrainingSession
from app.models.task import Task
from app.models.user import User, UserRole


def _make_user(session: Session, username: str, roles: tuple[str, ...] = ("student",)) -> User:
    """直插用户（密码哈希无关紧要：测试走 create_access_token 直签凭据）。"""
    user = User(
        username=username, password_hash="x", display_name=username, is_active=True
    )
    session.add(user)
    session.flush()
    for role in roles:
        session.add(UserRole(user_id=user.id, role=role))
    session.flush()
    return user


def _make_course(session: Session, teacher: User, invite_code: str) -> Course:
    course = Course(
        teacher_id=teacher.id,
        name=f"课程{invite_code}",
        invite_code=invite_code,
        term="2026秋",
    )
    session.add(course)
    session.flush()
    return course


def _make_task(
    session: Session, course: Course, join_code: str | None = None, archived: bool = False
) -> Task:
    task = Task(
        course_id=course.id,
        title="论证任务",
        material="材料",
        join_code=join_code,
        is_archived=archived,
    )
    session.add(task)
    session.flush()
    return task


def _join_course(session: Session, student: User, course: Course) -> None:
    """学生加入课程（S3-3 join API 的 DB 侧等价物：course_members 行）。"""
    session.add(CourseMember(course_id=course.id, user_id=student.id))
    session.flush()


def _auth(client: TestClient, user: User) -> None:
    """直签 JWT 写入 cookie jar（与 login 端点 set_cookie 同键同源）。"""
    client.cookies.set("access_token", create_access_token(user.id))


# ---------- POST 创建 ----------


def test_create_session_201_waiting_defaults(
    client: TestClient, session: Session
) -> None:
    """api.md:28：201 {id, status}；初始 waiting 不自动进 generating；默认 private。"""
    alice = _make_user(session, "alice")
    _auth(client, alice)
    resp = client.post("/api/sessions", json={"topic": "人工智能是否会取代教师"})
    assert resp.status_code == 201
    body = resp.json()
    assert set(body) == {"id", "status"}
    assert body["status"] == "waiting"
    row = session.get(TrainingSession, body["id"])
    assert row is not None
    assert row.owner_id == alice.id
    assert row.visibility == "private"
    assert row.task_id is None
    assert row.status == "waiting"


def test_create_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/sessions", json={"topic": "未登录创建"})
    assert resp.status_code == 401


def test_create_accepts_run_params(client: TestClient, session: Session) -> None:
    """脚注 1：mode/max_turns 为运行参数——接收但不落表（sessions 表无此列）。"""
    alice = _make_user(session, "alice")
    _auth(client, alice)
    resp = client.post(
        "/api/sessions",
        json={"topic": "自由辩论", "mode": "debate", "max_turns": 3},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "waiting"


def test_create_topic_validation_422(client: TestClient, session: Session) -> None:
    alice = _make_user(session, "alice")
    _auth(client, alice)
    assert client.post("/api/sessions", json={}).status_code == 422  # 缺 topic
    assert (
        client.post("/api/sessions", json={"topic": ""}).status_code == 422
    )  # 空串
    assert (
        client.post("/api/sessions", json={"topic": "题" * 201}).status_code == 422
    )  # 超 String(200)


def test_create_visibility_enum_422(client: TestClient, session: Session) -> None:
    alice = _make_user(session, "alice")
    _auth(client, alice)
    resp = client.post(
        "/api/sessions", json={"topic": "枚举外取值", "visibility": "public"}
    )
    assert resp.status_code == 422


def test_create_task_visibility_requires_task_id(
    client: TestClient, session: Session
) -> None:
    """E-2：visibility='task' ⇔ task_id 非空。"""
    alice = _make_user(session, "alice")
    _auth(client, alice)
    resp = client.post(
        "/api/sessions", json={"topic": "任务会话缺任务", "visibility": "task"}
    )
    assert resp.status_code == 422


def test_create_private_with_task_id_422(client: TestClient, session: Session) -> None:
    """E-2：private 不允许挂 task_id。"""
    alice = _make_user(session, "alice")
    teacher = _make_user(session, "teacher", roles=("teacher",))
    course = _make_course(session, teacher, "CRS00001")
    task = _make_task(session, course)
    _auth(client, alice)
    resp = client.post(
        "/api/sessions",
        json={"topic": "个人会话挂任务", "visibility": "private", "task_id": task.id},
    )
    assert resp.status_code == 422


def test_create_task_visibility_valid(client: TestClient, session: Session) -> None:
    """成员学生引用课程 task → 201（S3-3 join 后学生路径的 S2 模拟）。"""
    alice = _make_user(session, "alice")
    teacher = _make_user(session, "teacher", roles=("teacher",))
    course = _make_course(session, teacher, "CRS00002")
    _join_course(session, alice, course)
    task = _make_task(session, course, join_code="JN000001")
    _auth(client, alice)
    resp = client.post(
        "/api/sessions",
        json={"topic": "任务练习", "visibility": "task", "task_id": task.id},
    )
    assert resp.status_code == 201
    row = session.get(TrainingSession, resp.json()["id"])
    assert row is not None
    assert row.visibility == "task"
    assert row.task_id == task.id


def test_create_task_by_owner_teacher_201(client: TestClient, session: Session) -> None:
    """教师本人引用自己课程的 task → 201（归属：course.teacher_id==本人）。"""
    teacher = _make_user(session, "teacher", roles=("teacher",))
    course = _make_course(session, teacher, "CRS00009")
    task = _make_task(session, course)
    _auth(client, teacher)
    resp = client.post(
        "/api/sessions",
        json={"topic": "教师个人任务练习", "visibility": "task", "task_id": task.id},
    )
    assert resp.status_code == 201


def test_create_task_cross_teacher_404(client: TestClient, session: Session) -> None:
    """追问 2 裁定：跨教师引用 → 404 存在性隐藏（不暴露归属细节）。"""
    alice = _make_user(session, "alice")
    teacher1 = _make_user(session, "teacher1", roles=("teacher",))
    teacher2 = _make_user(session, "teacher2", roles=("teacher",))
    course = _make_course(session, teacher1, "CRS00010")
    task = _make_task(session, course)
    _auth(client, teacher2)  # teacher2 引用 teacher1 课程的 task
    resp = client.post(
        "/api/sessions",
        json={"topic": "跨教师引用", "visibility": "task", "task_id": task.id},
    )
    assert resp.status_code == 404


def test_create_task_student_non_member_404(client: TestClient, session: Session) -> None:
    """非成员学生引用 task → 404（S2 无 join API，成员表恒空）。"""
    bob = _make_user(session, "bob")
    teacher = _make_user(session, "teacher", roles=("teacher",))
    course = _make_course(session, teacher, "CRS00011")
    task = _make_task(session, course)
    _auth(client, bob)
    resp = client.post(
        "/api/sessions",
        json={"topic": "非成员引用", "visibility": "task", "task_id": task.id},
    )
    assert resp.status_code == 404


def test_create_task_not_found_422(client: TestClient, session: Session) -> None:
    alice = _make_user(session, "alice")
    _auth(client, alice)
    resp = client.post(
        "/api/sessions",
        json={"topic": "指向不存在的任务", "visibility": "task", "task_id": 999},
    )
    assert resp.status_code == 422


def test_create_task_archived_422(client: TestClient, session: Session) -> None:
    alice = _make_user(session, "alice")
    teacher = _make_user(session, "teacher", roles=("teacher",))
    course = _make_course(session, teacher, "CRS00003")
    task = _make_task(session, course, archived=True)
    _auth(client, alice)
    resp = client.post(
        "/api/sessions",
        json={"topic": "指向已归档任务", "visibility": "task", "task_id": task.id},
    )
    assert resp.status_code == 422


# ---------- GET 详情 ----------


def test_get_own_session_200(client: TestClient, session: Session) -> None:
    """api.md:29：200 七字段齐。"""
    alice = _make_user(session, "alice")
    _auth(client, alice)
    created = client.post("/api/sessions", json={"topic": "我的议题"}).json()
    resp = client.get(f"/api/sessions/{created['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "id",
        "topic",
        "visibility",
        "task_id",
        "status",
        "created_at",
        "updated_at",
    }
    assert body["topic"] == "我的议题"
    assert body["visibility"] == "private"
    assert body["task_id"] is None
    assert body["status"] == "waiting"


def test_get_nonexistent_404(client: TestClient, session: Session) -> None:
    alice = _make_user(session, "alice")
    _auth(client, alice)
    assert client.get("/api/sessions/999").status_code == 404


def test_get_private_non_owner_404(client: TestClient, session: Session) -> None:
    """用户约束②：private 非 owner → 404（存在性隐藏，学生越权）。"""
    alice = _make_user(session, "alice")
    bob = _make_user(session, "bob")
    _auth(client, alice)
    created = client.post("/api/sessions", json={"topic": "alice 的私有议题"}).json()
    _auth(client, bob)
    resp = client.get(f"/api/sessions/{created['id']}")
    assert resp.status_code == 404


def test_get_private_teacher_404(client: TestClient, session: Session) -> None:
    """api.md:29 字面：private → 教师 404。"""
    alice = _make_user(session, "alice")
    teacher = _make_user(session, "teacher", roles=("teacher",))
    _auth(client, alice)
    created = client.post("/api/sessions", json={"topic": "学生的私有议题"}).json()
    _auth(client, teacher)
    assert client.get(f"/api/sessions/{created['id']}").status_code == 404


def test_get_task_session_teacher_of_course_200(
    client: TestClient, session: Session
) -> None:
    """api.md:29：task → 课程教师可见集合（can_read_session ②）。"""
    alice = _make_user(session, "alice")
    teacher = _make_user(session, "teacher", roles=("teacher",))
    course = _make_course(session, teacher, "CRS00004")
    _join_course(session, alice, course)
    task = _make_task(session, course)
    _auth(client, alice)
    created = client.post(
        "/api/sessions",
        json={"topic": "任务练习", "visibility": "task", "task_id": task.id},
    ).json()
    _auth(client, teacher)
    resp = client.get(f"/api/sessions/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["task_id"] == task.id


def test_get_task_session_other_teacher_404(client: TestClient, session: Session) -> None:
    """其他课程教师不在可见集合 → 404。"""
    alice = _make_user(session, "alice")
    teacher = _make_user(session, "teacher", roles=("teacher",))
    other = _make_user(session, "other_teacher", roles=("teacher",))
    course = _make_course(session, teacher, "CRS00005")
    _join_course(session, alice, course)
    task = _make_task(session, course)
    _auth(client, alice)
    created = client.post(
        "/api/sessions",
        json={"topic": "任务练习", "visibility": "task", "task_id": task.id},
    ).json()
    _auth(client, other)
    assert client.get(f"/api/sessions/{created['id']}").status_code == 404


# ---------- PATCH 修改 ----------


def test_patch_status_field_422(client: TestClient, session: Session) -> None:
    """用户约束③+api.md:30：status 状态机独占，PATCH 收到即 422（不静默忽略）。"""
    alice = _make_user(session, "alice")
    _auth(client, alice)
    created = client.post("/api/sessions", json={"topic": "改状态"}).json()
    resp = client.patch(f"/api/sessions/{created['id']}", json={"status": "paused"})
    assert resp.status_code == 422
    assert "状态机" in resp.text


def test_patch_non_owner_student_404(client: TestClient, session: Session) -> None:
    """用户约束③：PATCH 走 can_read_session——学生非 owner → 404。"""
    alice = _make_user(session, "alice")
    bob = _make_user(session, "bob")
    _auth(client, alice)
    created = client.post("/api/sessions", json={"topic": "alice 的议题"}).json()
    _auth(client, bob)
    resp = client.patch(f"/api/sessions/{created['id']}", json={"topic": "越权改题"})
    assert resp.status_code == 404


def test_patch_teacher_readable_task_session_403(
    client: TestClient, session: Session
) -> None:
    """分层裁定（用户 2026-10-14 选项 A）：课程教师对学生 task 会话可读但
    无 update 授权（permissions:64）→ 403 非 owner（api.md:30 字面）。"""
    alice = _make_user(session, "alice")
    teacher = _make_user(session, "teacher", roles=("teacher",))
    course = _make_course(session, teacher, "CRS00006")
    _join_course(session, alice, course)
    task = _make_task(session, course)
    _auth(client, alice)
    created = client.post(
        "/api/sessions",
        json={"topic": "任务练习", "visibility": "task", "task_id": task.id},
    ).json()
    _auth(client, teacher)
    resp = client.patch(f"/api/sessions/{created['id']}", json={"topic": "教师改题"})
    assert resp.status_code == 403


def test_patch_owner_topic_200(client: TestClient, session: Session) -> None:
    """api.md:30 + E-17：owner 改 topic → 200 平铺（与 GET 同构）。"""
    alice = _make_user(session, "alice")
    _auth(client, alice)
    created = client.post("/api/sessions", json={"topic": "旧题"}).json()
    resp = client.patch(f"/api/sessions/{created['id']}", json={"topic": "新题"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "id",
        "topic",
        "visibility",
        "task_id",
        "status",
        "created_at",
        "updated_at",
    }
    assert body["topic"] == "新题"
    assert body["status"] == "waiting"  # 状态不动
    row = session.get(TrainingSession, created["id"])
    assert row is not None
    assert row.topic == "新题"


def test_patch_task_id_only_on_private_422(client: TestClient, session: Session) -> None:
    """E-2 约束合并后的组合：private 会话单独挂 task_id → 422。"""
    alice = _make_user(session, "alice")
    teacher = _make_user(session, "teacher", roles=("teacher",))
    course = _make_course(session, teacher, "CRS00007")
    task = _make_task(session, course)
    _auth(client, alice)
    created = client.post("/api/sessions", json={"topic": "私有议题"}).json()
    resp = client.patch(f"/api/sessions/{created['id']}", json={"task_id": task.id})
    assert resp.status_code == 422


def test_patch_task_to_private_200(client: TestClient, session: Session) -> None:
    """显式 null 与不传区分（model_fields_set）：task→private 需 task_id:null。"""
    alice = _make_user(session, "alice")
    teacher = _make_user(session, "teacher", roles=("teacher",))
    course = _make_course(session, teacher, "CRS00008")
    _join_course(session, alice, course)
    task = _make_task(session, course)
    _auth(client, alice)
    created = client.post(
        "/api/sessions",
        json={"topic": "任务练习", "visibility": "task", "task_id": task.id},
    ).json()
    resp = client.patch(
        f"/api/sessions/{created['id']}",
        json={"visibility": "private", "task_id": None},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["visibility"] == "private"
    assert body["task_id"] is None


def test_patch_task_cross_teacher_404(client: TestClient, session: Session) -> None:
    """PATCH 挂他人课程的 task（归属不符）→ 404（同 POST 裁定）。"""
    alice = _make_user(session, "alice")
    teacher1 = _make_user(session, "teacher1", roles=("teacher",))
    teacher2 = _make_user(session, "teacher2", roles=("teacher",))
    course1 = _make_course(session, teacher1, "CRS00012")
    course2 = _make_course(session, teacher2, "CRS00013")
    _join_course(session, alice, course1)
    task1 = _make_task(session, course1)
    task2 = _make_task(session, course2)
    _auth(client, alice)
    created = client.post(
        "/api/sessions",
        json={"topic": "任务练习", "visibility": "task", "task_id": task1.id},
    ).json()
    resp = client.patch(
        f"/api/sessions/{created['id']}",
        json={"visibility": "task", "task_id": task2.id},
    )
    assert resp.status_code == 404


def test_patch_nonexistent_404(client: TestClient, session: Session) -> None:
    alice = _make_user(session, "alice")
    _auth(client, alice)
    resp = client.patch("/api/sessions/999", json={"topic": "改不存在的会话"})
    assert resp.status_code == 404


def test_patch_forbids_extra_field_422(client: TestClient, session: Session) -> None:
    alice = _make_user(session, "alice")
    _auth(client, alice)
    created = client.post("/api/sessions", json={"topic": "议题"}).json()
    resp = client.patch(f"/api/sessions/{created['id']}", json={"foo": 1})
    assert resp.status_code == 422
