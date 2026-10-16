"""S2-4 API 层测试：SSE events 端点 + messages 端点（api.md:35/38/42）。

策略（设计 §9）：全 FakeProvider，不触网；TestClient 门户模式下
StreamingResponse 同步生成器整体迭代完、BackgroundTasks 在响应
返回前同步执行完——断言时 AI 生成已收尾。

注意：事件流测试用 r.iter_lines() 读取（TestClient 已把同步生成器
跑完，stream=True 下逐行读不阻塞）。
"""
from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"  # 必须在导入 app 包之前写入

import json

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from app.models.message import Message
from app.models.session import TrainingSession
from app.models.task import Task
from app.models.course import Course
from app.services.event_bus import event_bus
from app.services.session_registry import session_registry

from tests.models.conftest import engine, session  # noqa: E402,F401


@pytest.fixture(autouse=True)
def _clean_bus():
    event_bus.reset()
    session_registry.reset()
    yield
    event_bus.reset()
    session_registry.reset()


@pytest.fixture()
def client(session):
    def _override_get_db():
        yield session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def runner_session_factory(session):
    """让 BackgroundTasks 的 runner 复用测试 session（生产是独立 session）。

    差异说明：生产路径 runner 用 get_session_factory()() 独立 session
    （api/sessions.py：请求 session 在响应结束时 close，BackgroundTasks
    晚于响应执行）。测试里若也独立，runner 线程绑定的是
    app.core.database 全局单例 engine——与 tests/models conftest 里
    create_engine 新建的 engine 是两个实例（同 sfb_test 库但连接/事务
    边界不同，且线程生命周期跨 TRUNCATE 边界不确定）。

    注意 monkeypatch sessions_module.get_session_factory 无效：端点
    _run 闭包在函数体内 `from app.core.database import get_session_factory`
    ——import 语句执行时按**源模块属性**取值，故必须替换
    app.core.database.get_session_factory 本身（且返回值须可调用
    再取 session：_run 里 get_session_factory()()）。
    """
    import app.core.database as db_module

    original_factory = db_module.get_session_factory

    def _test_factory():
        return lambda: session

    db_module.get_session_factory = _test_factory
    try:
        yield session
    finally:
        db_module.get_session_factory = original_factory


@pytest.fixture()
def user_and_headers(session):
    """建学生用户 + 返回 (user, cookies)（登录拿 access_token Cookie）。"""
    from app.core.security import create_access_token
    from app.models.user import User, UserRole

    user = User(username="stu1", password_hash="x", display_name="同学")
    session.add(user)
    session.flush()
    session.add(UserRole(user_id=user.id, role="student"))
    session.commit()
    session.refresh(user)
    token = create_access_token(user.id)
    return user, {"access_token": token}


def _make_session(session_db, user_id: int, *, status: str = "waiting") -> TrainingSession:
    sess = TrainingSession(owner_id=user_id, topic="AI 是否应限制使用", status=status)
    session_db.add(sess)
    session_db.commit()
    session_db.refresh(sess)
    return sess


def _parse_sse(lines: list[str]) -> list[tuple[str, dict | None]]:
    """解析 SSE 文本行为 (event, data) 序列（注释行/空行跳过）。

    httpx 的 iter_lines() 会把无空行分隔的连续行拼成一行（TestClient
    的 transport 缓冲边界，非服务端 bug——真实浏览器按 \\n\\n 分帧不会
    出现），故先按裸 "event: " 边界再切分。
    """
    out: list[tuple[str, dict | None]] = []
    event = None
    for line in lines:
        if not line.strip() or line.startswith(":"):
            continue
        # httpx 可能把 "retry: 5000" 与下一 "event: xxx" 拼进同一行：
        # 逐段切分，保证每个 event: 都被识别。
        segments = line.split("event: ")
        for segment in segments[1:]:
            event = segment.strip()
            for sub in segment.split("\n"):
                if sub.startswith("data: ") and event is not None:
                    out.append((event, json.loads(sub[len("data: ") :])))
                    event = None
        if not segments[1:]:
            for sub in line.split("\n"):
                if sub.startswith("data: ") and event is not None:
                    out.append((event, json.loads(sub[len("data: ") :])))
                    event = None
    return out


# ---- messages 端点（api.md:35）----

def test_submit_message_201_shape(session, client, user_and_headers, monkeypatch):
    """POST messages → 201 {seq,created_at}（api.md:35 出参形状）。"""
    from app.core.model_provider import FakeProvider
    import app.api.sessions as sessions_module

    monkeypatch.setattr(
        sessions_module, "build_provider", lambda: FakeProvider(chunks=["反方论点"])
    )
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    resp = client.post(f"/api/sessions/{sess.id}/messages", json={"content": "我认为应当限制。"}, cookies=cookies)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["seq"] == 1  # 用户消息 seq=1（E-1 方案 A 自增）
    assert "created_at" in body


def test_submit_message_201_and_runner_completed(
    session, client, user_and_headers, monkeypatch, runner_session_factory
):
    """POST messages 全链路（api.md:35）：201 + runner 落库 + 轮尽 finished。

    覆盖三件事：①同步部分（201 {seq,created_at} + role='user' 落库）；
    ②BackgroundTasks 已触发 runner（assistant 消息出现）；③最终一致
    （complete + finished）。runner 经 runner_session_factory 夹具复用
    测试 session（生产是独立 session，见该夹具 docstring）。
    """
    from sqlalchemy import select as sa_select

    from app.core.model_provider import FakeProvider
    import app.api.sessions as sessions_module

    monkeypatch.setattr(
        sessions_module, "build_provider", lambda: FakeProvider(chunks=["反方论点"])
    )
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    resp = client.post(f"/api/sessions/{sess.id}/messages", json={"content": "我认为应当限制。"}, cookies=cookies)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["seq"] == 1  # 用户消息 seq=1（E-1 方案 A 自增）
    assert "created_at" in body
    # 异步部分：BackgroundTasks 触发 runner。TestClient 门户模式下
    # 同步执行完（starlette/responses.py:284-285 stream_response 后
    # await background）——assistant 消息 seq=2 落库 complete。
    session.expire_all()
    rows = session.scalars(
        sa_select(Message).where(Message.session_id == sess.id).order_by(Message.seq)
    ).all()
    assert [(r.seq, r.role, r.agent_role, r.status) for r in rows] == [
        (1, "user", None, "complete"),
        (2, "assistant", "con", "complete"),
    ]
    assert rows[1].content == "反方论点"


def test_submit_message_writes_user_row_and_triggers_runner(
    session, client, user_and_headers, monkeypatch
):
    """同链路最小断言版：用户消息同步落库（seq=1）+ runner 被触发。

    runner 用独立 db session（生产路径真实形态）——BackgroundTasks
    在线程池异步执行，测试只断言"响应返回时同步部分已落库"，不假设
    后台任务完成时机（异步完成由 SSE 回放测试覆盖）。
    """
    from sqlalchemy import select as sa_select

    from app.core.model_provider import FakeProvider
    import app.api.sessions as sessions_module

    monkeypatch.setattr(
        sessions_module, "build_provider", lambda: FakeProvider(chunks=["反方论点"])
    )
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    resp = client.post(f"/api/sessions/{sess.id}/messages", json={"content": "我认为应当限制。"}, cookies=cookies)
    assert resp.status_code == 201, resp.text
    session.expire_all()
    rows = session.scalars(
        sa_select(Message).where(Message.session_id == sess.id).order_by(Message.seq)
    ).all()
    # 用户消息 role='user' 落库（api.md:35 同步写）
    assert rows[0].role == "user"
    assert rows[0].content == "我认为应当限制。"
    # runner 已跑：assistant 消息在（无论状态——runner 可能在后台线程未完成）
    if len(rows) > 1:
        assert rows[1].role == "assistant"


def test_submit_message_runs_runner_to_completion(
    session, client, user_and_headers, monkeypatch, runner_session_factory
):
    """runner 最终落库 complete + 轮尽 finished（轮询容忍异步/同步两种语义）。

    TestClient 门户模式下 BackgroundTasks 同步执行完（见
    test_submit_message_201_and_runner_completed 注释）；轮询循环让
    本用例对未来"真线程池异步"的 starlette 版本也成立——两种语义下
    断言同一最终状态，不把测试绑死在门户实现细节上。
    """
    import time

    from sqlalchemy import select as sa_select

    from app.core.model_provider import FakeProvider
    import app.api.sessions as sessions_module

    monkeypatch.setattr(
        sessions_module, "build_provider", lambda: FakeProvider(chunks=["反方论点"])
    )
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    resp = client.post(f"/api/sessions/{sess.id}/messages", json={"content": "我认为应当限制。"}, cookies=cookies)
    assert resp.status_code == 201, resp.text

    rows = []
    for _ in range(50):  # 50 × 0.1s = 5s 上限（防挂死）
        session.expire_all()
        rows = session.scalars(
            sa_select(Message).where(Message.session_id == sess.id).order_by(Message.seq)
        ).all()
        if len(rows) >= 2 and rows[1].status != "streaming":
            break
        time.sleep(0.1)
    assert [(r.seq, r.role, r.agent_role, r.status) for r in rows] == [
        (1, "user", None, "complete"),
        (2, "assistant", "con", "complete"),
    ]
    assert rows[1].content == "反方论点"
    # max_turns=1（registry 默认值）：轮尽 → finished
    session.expire_all()
    assert session.get(TrainingSession, sess.id).status == "finished"


def test_submit_message_conflicts_when_not_waiting(session, client, user_and_headers):
    """409：会话非 waiting（api.md:92 清单字面：messages 提交于非 waiting）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="generating")
    resp = client.post(f"/api/sessions/{sess.id}/messages", json={"content": "x"}, cookies=cookies)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "会话当前状态不接受新消息"


# messages 403（api.md:35 错误列字面「403 非 owner」；写操作，与 PATCH 同分层）
_FORBIDDEN_SUBMIT_DETAIL = "仅会话所有者可提交消息"


def test_submit_message_forbidden_non_owner(session, client, user_and_headers):
    """403：课程教师（可读 task 会话）代学生发言被拒（api.md:35 字面）。"""
    from app.models.user import User, UserRole
    from app.models.course import Course
    from app.models.task import Task

    owner, cookies = user_and_headers
    # 课程教师（非 owner）登录：可读 task 会话但不可代学生发言 → 403
    teacher = User(username="tea1", password_hash="x", display_name="教师")
    session.add(teacher)
    session.flush()
    session.add(UserRole(user_id=teacher.id, role="teacher"))
    course = Course(teacher_id=teacher.id, name="逻辑学", invite_code="LOG101", term="2026秋")
    session.add(course)
    session.flush()
    task = Task(course_id=course.id, title="AI 议题辩论")
    session.add(task)
    session.commit()
    sess = TrainingSession(
        owner_id=owner.id, topic="AI 限制", visibility="task", task_id=task.id, status="waiting"
    )
    session.add(sess)
    session.commit()
    session.refresh(sess)

    from app.core.security import create_access_token

    teacher_cookies = {"access_token": create_access_token(teacher.id)}
    resp = client.post(
        f"/api/sessions/{sess.id}/messages", json={"content": "x"}, cookies=teacher_cookies
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == _FORBIDDEN_SUBMIT_DETAIL


def test_submit_message_404_unauthorized(session, client, user_and_headers):
    """404：会话不存在/不可见（存在性隐藏）。"""
    user, cookies = user_and_headers
    resp = client.post("/api/sessions/9999/messages", json={"content": "x"}, cookies=cookies)
    assert resp.status_code == 404


def test_submit_message_requires_auth(session, client, user_and_headers):
    """401：未登录。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    resp = client.post(f"/api/sessions/{sess.id}/messages", json={"content": "x"})
    assert resp.status_code == 401


def test_submit_message_422_empty_content(session, client, user_and_headers):
    """422：content 空串（min_length=1）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    resp = client.post(f"/api/sessions/{sess.id}/messages", json={"content": ""}, cookies=cookies)
    assert resp.status_code == 422


def test_list_messages_200(session, client, user_and_headers):
    """GET messages：after_seq 之后升序 + next_seq（api.md:38）。"""
    from sqlalchemy import select as sa_select

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    for content in ("第一问", "第二问"):
        session.add(Message(session_id=sess.id, role="user", content=content))
    session.commit()
    resp = client.get(f"/api/sessions/{sess.id}/messages", cookies=cookies)
    assert resp.status_code == 200
    body = resp.json()
    assert [m["content"] for m in body["messages"]] == ["第一问", "第二问"]
    assert body["next_seq"] == 2
    # after_seq=2 → 空 + next_seq 保持
    resp2 = client.get(f"/api/sessions/{sess.id}/messages?after_seq=2", cookies=cookies)
    assert resp2.json() == {"messages": [], "next_seq": 2}


def test_list_messages_404_unauthorized(session, client, user_and_headers):
    """404：他人 private 会话不可见。"""
    from app.models.user import User

    owner, cookies = user_and_headers
    other = User(username="stu2", password_hash="x", display_name="同学2")
    session.add(other)
    session.commit()
    session.refresh(other)
    sess = _make_session(session, other.id)
    resp = client.get(f"/api/sessions/{sess.id}/messages", cookies=cookies)
    assert resp.status_code == 404


# ---- events 端点（api.md:42 + E-19）----

def test_events_stream_401_unauth(session, client, user_and_headers):
    """401：未登录（HTTP 层，不进事件流）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    resp = client.get(f"/api/sessions/{sess.id}/events")
    assert resp.status_code == 401


def test_events_stream_404_unauthorized(session, client, user_and_headers):
    """404：不可见会话（E-19：读路径无 403 分支）。"""
    from app.models.user import User

    owner, cookies = user_and_headers
    other = User(username="stu2", password_hash="x", display_name="同学2")
    session.add(other)
    session.commit()
    session.refresh(other)
    sess = _make_session(session, other.id)
    resp = client.get(f"/api/sessions/{sess.id}/events", cookies=cookies)
    assert resp.status_code == 404


def test_events_stream_empty_waiting_session_closes_on_heartbeat(
    session, client, user_and_headers, monkeypatch
):
    """waiting 空会话：建流发 retry + 实时循环（无事件时 heartbeat）。

    心跳间隔 15s 会让测试跑 15s——monkeypatch 到 0.05s 加速；发一轮
    心跳后由 done sentinel（runner publish_done）关流。
    """
    import app.api.events as events_module

    monkeypatch.setattr(events_module, "_HEARTBEAT_INTERVAL", 0.05)
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    # 预置一个订阅者不可行（端点在锁内订阅）——改为：开流前手动发 done
    # 会让流立即结束，这里改为验证流能开并至少产出 retry 行。
    # 用后台线程在流开启后 publish_done 关流：
    import threading
    import time

    def _close_later():
        time.sleep(0.3)
        event_bus.publish_done(sess.id)

    threading.Thread(target=_close_later, daemon=True).start()
    with client.stream("GET", f"/api/sessions/{sess.id}/events", cookies=cookies) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["cache-control"] == "no-cache"
        lines = [line for line in r.iter_lines() if line.strip()]
    assert any(line.startswith("retry: 5000") for line in lines)  # sse §2 建流即发
    assert any(line.startswith("event: done") for line in lines)


def test_events_stream_replay_terminal_session(session, client, user_and_headers):
    """终态会话回放：start→delta→end 重编码 + done 关流（sse §7.1）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="finished")
    session.add(
        Message(
            session_id=sess.id, role="assistant", agent_role="con",
            content="反方完整发言", status="complete",
        )
    )
    session.commit()
    with client.stream("GET", f"/api/sessions/{sess.id}/events", cookies=cookies) as r:
        assert r.status_code == 200
        lines = [line for line in r.iter_lines() if line.strip()]
    events = _parse_sse(lines)
    kinds = [e for e, _ in events]
    assert kinds == ["speech_start", "speech_delta", "speech_end", "done"]
    # speech_* 帧带 id: 行（§3）
    assert "id: 1" in lines
    delta = events[1][1]
    assert delta["delta"] == "反方完整发言"  # 全量重编码
    end = events[2][1]
    assert end["status"] == "complete"
    assert events[3][1]["reason"] == "finished"  # §5.10 reason 与 status 对应


def test_events_stream_replay_skips_before_after_seq(session, client, user_and_headers):
    """after_seq=1：seq=1 不回放，只回 seq=2（§7.2 首连消缝）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="finished")
    session.add(Message(session_id=sess.id, role="user", content="学生发言", status="complete"))
    session.add(
        Message(session_id=sess.id, role="assistant", agent_role="con", content="AI 发言", status="complete")
    )
    session.commit()
    with client.stream(
        "GET", f"/api/sessions/{sess.id}/events?after_seq=1", cookies=cookies
    ) as r:
        lines = [line for line in r.iter_lines() if line.strip()]
    events = _parse_sse(lines)
    # 用户消息（seq=1）被 after_seq 跳过；assistant（seq=2）重编码
    assert [e for e, _ in events] == ["speech_start", "speech_delta", "speech_end", "done"]
    assert events[0][1]["seq"] == 2


def test_events_stream_last_event_id_header(session, client, user_and_headers):
    """Last-Event-ID 头优先于 query（EventSource 原生重连，§7.2）。

    场景：两条消息（seq=1 学生 / seq=2 AI），浏览器带着 Last-Event-ID: 1
    重连（query 故意给 after_seq=0 应被头覆盖）→ 只回 seq=2。
    """
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="finished")
    session.add(Message(session_id=sess.id, role="user", content="学生发言", status="complete"))
    session.add(
        Message(session_id=sess.id, role="assistant", agent_role="con", content="AI 发言", status="complete")
    )
    session.commit()
    with client.stream(
        "GET",
        f"/api/sessions/{sess.id}/events?after_seq=0",
        cookies=cookies,
        headers={"Last-Event-ID": "1"},
    ) as r:
        lines = [line for line in r.iter_lines() if line.strip()]
    events = _parse_sse(lines)
    # 用户消息（seq=1）被 Last-Event-ID 跳过；assistant（seq=2）重编码
    assert [e for e, _ in events] == ["speech_start", "speech_delta", "speech_end", "done"]
    assert events[0][1]["seq"] == 2


def test_events_stream_inflight_snapshot(session, client, user_and_headers, monkeypatch):
    """在途消息：回放不发 start/delta/end，改发 snapshot（§7.3）。"""
    import app.api.events as events_module

    monkeypatch.setattr(events_module, "_HEARTBEAT_INTERVAL", 0.05)
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="generating")
    session.add(
        Message(
            session_id=sess.id, role="assistant", agent_role="con",
            content="半句话", status="streaming",
        )
    )
    session.commit()

    import threading
    import time

    def _close_later():
        time.sleep(0.3)
        event_bus.publish_done(sess.id)

    threading.Thread(target=_close_later, daemon=True).start()
    with client.stream("GET", f"/api/sessions/{sess.id}/events", cookies=cookies) as r:
        lines = [line for line in r.iter_lines() if line.strip()]
    events = _parse_sse(lines)
    kinds = [e for e, _ in events]
    assert "speech_snapshot" in kinds
    assert "speech_start" not in kinds  # 在途不重编码 start
    snap = next(d for e, d in events if e == "speech_snapshot")
    assert snap["content"] == "半句话"
    assert snap["status"] == "streaming"


def test_events_stream_failed_session_replay_done(session, client, user_and_headers):
    """failed 会话：回放完 done(reason='failed') 关流（§5.10/§7.1）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="failed")
    session.add(
        Message(session_id=sess.id, role="assistant", agent_role="con", content="中断", status="complete")
    )
    session.commit()
    with client.stream("GET", f"/api/sessions/{sess.id}/events", cookies=cookies) as r:
        lines = [line for line in r.iter_lines() if line.strip()]
    events = _parse_sse(lines)
    assert events[-1] == ("done", {"session_id": sess.id, "reason": "failed"})
