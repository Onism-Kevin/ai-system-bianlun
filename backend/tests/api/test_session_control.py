"""S2-6 API 层测试：pause/resume/restart/quick 四控制端点（api.md:31-34）。

策略（S2-6 设计 §9）：全 FakeProvider 不触网；TestClient 门户模式下
StreamingResponse 同步生成器整体迭代完、BackgroundTasks 同步执行完。

覆盖矩阵（api.md:31-34 四行 + 脚注 4 + §3:90 错误分层）：
- 正常路径：pause→resume 续写同一条（计划书完成信号"暂停后 DB
  status=paused + 消息标截断；恢复续写同一条"）、restart 全态合法
  （消息全保留，处置留白 S2-F6）、quick 轮尽/未轮尽两种目标。
- 409 路径：pause/quick 非 generating、resume 非 paused、restart 于
  generating 中、quick@paused（脚注 4 裁定）。
- 403/404 分层：教师可读 task 会话但不可代控制（permissions §4 字面）；
  他人 private 会话 404 存在性隐藏。

runner 交互说明：pause/quick 置位 flag 由 runner chunk 边界消费，但
本文件只测端点语义（DB 转移 + 消息 status + 事件帧），runner 停手/
续写行为由 tests/services/test_debate_runner.py 的 pause/resume 专项
覆盖（RecordingBus 记序列）。端点与 runner 的互斥由
event_bus.session_lock 保证，测试侧无需真实并发。
"""
from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"  # 必须在导入 app 包之前写入

import json  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select as sa_select  # noqa: E402

from app.core.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.message import Message  # noqa: E402
from app.models.session import TrainingSession  # noqa: E402
from app.services.event_bus import event_bus  # noqa: E402  单例对象：controller/session_lock/publish_done 是其实例方法
from app.services.session_registry import session_registry  # noqa: E402

from tests.api.test_events import (  # noqa: E402
    _clean_bus,
    _make_session,
    _parse_sse,
    client,
    runner_session_factory,
    user_and_headers,
)
from tests.models.conftest import session  # noqa: E402,F401


def _spy_publish(monkeypatch) -> list[dict]:
    """monkeypatch sessions 模块的 `_event_bus` 单例记录帧序列。

    端点 _publish 经模块级 `_event_bus.publish(...)` 发布——替换
    app.api.sessions._event_bus 为一个只记录不转发的替身即可拦截
    （session_lock/controller 等仍走真实 event_bus 单例，不受影响）。
    spy 只记录不转发：帧正确性由 events 端点回放测试覆盖，此处只断言
    端点发了哪些帧、什么顺序。
    """
    import app.api.sessions as sessions_module

    class _SpyBus:
        def __init__(self, real):
            self._real = real
            self.frames: list[dict] = []

        def publish(self, session_id, frame):
            self.frames.append(frame)

        def __getattr__(self, name):
            return getattr(self._real, name)

    spy = _SpyBus(sessions_module._event_bus)
    monkeypatch.setattr(sessions_module, "_event_bus", spy)
    return spy.frames


def _make_streaming_message(session_db, session_id: int, *, content: str = "前半段") -> Message:
    """预置一条在途 assistant 消息（status='streaming'）。

    等价 runner 已 commit 若干 chunk 后的中间态（chunk 落库时机由
    S2-4 落库专项覆盖）；端点 pause/quick 读它做截断点。
    """
    msg = Message(
        session_id=session_id,
        role="assistant",
        agent_role="con",
        content=content,
        status="streaming",
    )
    session_db.add(msg)
    session_db.commit()
    session_db.refresh(msg)
    return msg


def _make_truncated_message(session_db, session_id: int, *, content: str = "前半段") -> Message:
    """预置一条 paused_truncated 消息（等价 pause 端点执行后的中间态）。"""
    msg = Message(
        session_id=session_id,
        role="assistant",
        agent_role="con",
        content=content,
        status="paused_truncated",
    )
    session_db.add(msg)
    session_db.commit()
    session_db.refresh(msg)
    return msg


def _stream_rows(session_db, session_id: int) -> list[Message]:
    session_db.expire_all()
    return session_db.scalars(
        sa_select(Message).where(Message.session_id == session_id).order_by(Message.seq)
    ).all()


# ---- pause（api.md:31）----

def test_pause_200_truncates_message_and_transitions(
    session, client, user_and_headers, monkeypatch
):
    """pause 正常路径：generating→paused + 在途消息 paused_truncated + speech_end 帧。

    计划书完成信号字面：「暂停后 DB status=paused + 消息标截断」。
    事件帧断言 speech_end(status='paused_truncated')（§5.3 暂停不关流，
    paused 非终态——done 由后续 restart/quick/自然耗尽 发）。
    """
    events = _spy_publish(monkeypatch)
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="generating")
    msg = _make_streaming_message(session, sess.id, content="已生成的前半段")
    resp = client.post(f"/api/sessions/{sess.id}/pause", cookies=cookies)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"id": sess.id, "status": "paused"}
    session.expire_all()
    assert session.get(TrainingSession, sess.id).status == "paused"
    rows = _stream_rows(session, sess.id)
    assert rows[0].status == "paused_truncated"
    assert rows[0].content == "已生成的前半段"  # 截断点=已 commit 全文
    assert event_bus.controller(sess.id).pause_requested is True
    ends = [e for e in events if e["event"] == "speech_end"]
    assert len(ends) == 1
    assert ends[0]["seq"] == msg.seq
    assert ends[0]["status"] == "paused_truncated"


def test_pause_409_when_not_generating(session, client, user_and_headers):
    """409：pause 于 waiting/paused/finished/failed（api.md:92 清单字面）。"""
    user, cookies = user_and_headers
    for bad_status in ("waiting", "paused", "finished", "failed"):
        sess = _make_session(session, user.id, status=bad_status)
        resp = client.post(f"/api/sessions/{sess.id}/pause", cookies=cookies)
        assert resp.status_code == 409, bad_status
        assert resp.json()["detail"] == "仅生成中可暂停/加速"


def test_pause_403_non_owner(session, client, user_and_headers):
    """403：课程教师（可读 task 会话）代学生暂停被拒（permissions §4 字面）。"""
    from app.core.security import create_access_token
    from app.models.course import Course
    from app.models.task import Task
    from app.models.user import User, UserRole

    owner, _ = user_and_headers
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
        owner_id=owner.id, topic="AI 限制", visibility="task", task_id=task.id, status="generating"
    )
    session.add(sess)
    session.commit()
    session.refresh(sess)
    _make_streaming_message(session, sess.id)
    resp = client.post(
        f"/api/sessions/{sess.id}/pause", cookies={"access_token": create_access_token(teacher.id)}
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "仅会话创建者可修改"


def test_pause_404_unauthorized(session, client, user_and_headers):
    """404：他人 private 会话（存在性隐藏）。"""
    from app.models.user import User

    owner, cookies = user_and_headers
    other = User(username="stu2", password_hash="x", display_name="同学2")
    session.add(other)
    session.commit()
    session.refresh(other)
    sess = _make_session(session, other.id, status="generating")
    resp = client.post(f"/api/sessions/{sess.id}/pause", cookies=cookies)
    assert resp.status_code == 404


def test_pause_401_requires_auth(session, client, user_and_headers):
    """401：未登录。"""
    user, _ = user_and_headers
    sess = _make_session(session, user.id, status="generating")
    resp = client.post(f"/api/sessions/{sess.id}/pause")
    assert resp.status_code == 401


def test_pause_500_when_no_streaming_message(session, client, user_and_headers):
    """500：generating 却无在途消息=状态与消息不一致（防御分支）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="generating")
    resp = client.post(f"/api/sessions/{sess.id}/pause", cookies=cookies)
    assert resp.status_code == 500
    assert resp.json()["detail"] == "会话状态与消息不一致"
    session.expire_all()
    assert session.get(TrainingSession, sess.id).status == "generating"  # 未转移


# ---- resume（api.md:32）----

def test_resume_200_restores_streaming_and_same_seq(
    session, client, user_and_headers, monkeypatch
):
    """resume 正常路径：paused→generating + 截断消息回 streaming + 重发 speech_start 同 seq。

    计划书完成信号字面：「恢复续写同一条」——seq 不变（§5.3：resume
    服务端重发 speech_start 同 seq，start 永不清）。
    """
    events = _spy_publish(monkeypatch)
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="paused")
    msg = _make_truncated_message(session, sess.id, content="已生成的前半段")
    resp = client.post(f"/api/sessions/{sess.id}/resume", cookies=cookies)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"id": sess.id, "status": "generating"}
    session.expire_all()
    assert session.get(TrainingSession, sess.id).status == "generating"
    rows = _stream_rows(session, sess.id)
    assert rows[0].status == "streaming"
    controller = event_bus.controller(sess.id)
    assert controller.pause_requested is False
    starts = [e for e in events if e["event"] == "speech_start"]
    assert len(starts) == 1
    assert starts[0]["seq"] == msg.seq  # 同一条续写
    assert starts[0]["agent_role"] == "con"


def test_resume_409_when_not_paused(session, client, user_and_headers):
    """409：resume 于 waiting/generating/finished/failed（api.md:92 清单字面）。"""
    user, cookies = user_and_headers
    for bad_status in ("waiting", "generating", "finished", "failed"):
        sess = _make_session(session, user.id, status=bad_status)
        resp = client.post(f"/api/sessions/{sess.id}/resume", cookies=cookies)
        assert resp.status_code == 409, bad_status
        assert resp.json()["detail"] == "会话当前未处于暂停态"


def test_resume_403_non_owner(session, client, user_and_headers):
    """403：课程教师代学生恢复被拒（permissions §4 字面）。"""
    from app.core.security import create_access_token
    from app.models.course import Course
    from app.models.task import Task
    from app.models.user import User, UserRole

    owner, _ = user_and_headers
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
        owner_id=owner.id, topic="AI 限制", visibility="task", task_id=task.id, status="paused"
    )
    session.add(sess)
    session.commit()
    session.refresh(sess)
    _make_truncated_message(session, sess.id)
    resp = client.post(
        f"/api/sessions/{sess.id}/resume", cookies={"access_token": create_access_token(teacher.id)}
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "仅会话创建者可修改"


def test_resume_404_unauthorized(session, client, user_and_headers):
    """404：他人 private 会话（存在性隐藏）。"""
    from app.models.user import User

    owner, cookies = user_and_headers
    other = User(username="stu2", password_hash="x", display_name="同学2")
    session.add(other)
    session.commit()
    session.refresh(other)
    sess = _make_session(session, other.id, status="paused")
    resp = client.post(f"/api/sessions/{sess.id}/resume", cookies=cookies)
    assert resp.status_code == 404


def test_resume_500_when_no_truncated_message(session, client, user_and_headers):
    """500：paused 却无截断消息=状态与消息不一致（防御分支）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="paused")
    resp = client.post(f"/api/sessions/{sess.id}/resume", cookies=cookies)
    assert resp.status_code == 500
    assert resp.json()["detail"] == "会话状态与消息不一致"
    session.expire_all()
    assert session.get(TrainingSession, sess.id).status == "paused"  # 未转移


# ---- restart（api.md:33）----

@pytest.mark.parametrize("start_status", ["waiting", "paused", "finished", "failed"])
def test_restart_200_from_non_generating(
    session, client, user_and_headers, start_status
):
    """restart 正常路径：waiting/paused/finished/failed → waiting，消息全保留。

    api.md:33：「消息处置由 S2-F6 实现定」——S2-6 裁定 6=全保留，
    仅 paused_truncated 兜底回 complete（防回放把截断消息当在途）。
    """
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status=start_status)
    if start_status == "paused":
        _make_truncated_message(session, sess.id)
    session.add(Message(session_id=sess.id, role="user", content="学生提问", status="complete"))
    session.commit()
    resp = client.post(f"/api/sessions/{sess.id}/restart", cookies=cookies)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"id": sess.id, "status": "waiting"}
    session.expire_all()
    assert session.get(TrainingSession, sess.id).status == "waiting"
    rows = _stream_rows(session, sess.id)
    # 消息一条不少（S2-F6 前不清空）；截断消息兜底回 complete
    statuses = [(r.role, r.status) for r in rows]
    assert ("user", "complete") in statuses
    if start_status == "paused":
        assert ("assistant", "complete") in statuses
        assert ("assistant", "paused_truncated") not in statuses


def test_restart_409_when_generating(session, client, user_and_headers):
    """409：generating 中 restart（api.md:92 清单字面「先生成中，请先暂停」）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="generating")
    _make_streaming_message(session, sess.id)
    resp = client.post(f"/api/sessions/{sess.id}/restart", cookies=cookies)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "生成中，请先暂停"
    session.expire_all()
    assert session.get(TrainingSession, sess.id).status == "generating"  # 未转移


def test_restart_403_non_owner(session, client, user_and_headers):
    """403：课程教师代学生重开被拒（permissions §4 字面）。"""
    from app.core.security import create_access_token
    from app.models.course import Course
    from app.models.task import Task
    from app.models.user import User, UserRole

    owner, _ = user_and_headers
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
        owner_id=owner.id, topic="AI 限制", visibility="task", task_id=task.id, status="finished"
    )
    session.add(sess)
    session.commit()
    session.refresh(sess)
    resp = client.post(
        f"/api/sessions/{sess.id}/restart", cookies={"access_token": create_access_token(teacher.id)}
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "仅会话创建者可修改"


def test_restart_404_unauthorized(session, client, user_and_headers):
    """404：他人 private 会话（存在性隐藏）。"""
    from app.models.user import User

    owner, cookies = user_and_headers
    other = User(username="stu2", password_hash="x", display_name="同学2")
    session.add(other)
    session.commit()
    session.refresh(other)
    sess = _make_session(session, other.id, status="finished")
    resp = client.post(f"/api/sessions/{sess.id}/restart", cookies=cookies)
    assert resp.status_code == 404


# ---- quick（api.md:34 + 脚注 4）----

def test_quick_200_finishes_when_turns_exhausted(
    session, client, user_and_headers, monkeypatch, runner_session_factory
):
    """quick 轮尽路径：generating→finished + 消息 complete + speech_end(complete)+done(finished)。

    轮次判定与 _finalize_complete 共用 plan_finalize_target；max_turns=1
    （registry 默认）时当前轮即最后一轮 → finished（api.md:34 目标留白）。
    """
    events = _spy_publish(monkeypatch)
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="generating")
    msg = _make_streaming_message(session, sess.id, content="加速定稿全文")
    resp = client.post(f"/api/sessions/{sess.id}/quick", cookies=cookies)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"id": sess.id, "status": "finished"}
    session.expire_all()
    assert session.get(TrainingSession, sess.id).status == "finished"
    rows = _stream_rows(session, sess.id)
    assert rows[0].status == "complete"
    assert rows[0].content == "加速定稿全文"  # 立即定稿=截断到当前全文
    ends = [e for e in events if e["event"] == "speech_end"]
    assert ends[0]["seq"] == msg.seq
    assert ends[0]["status"] == "complete"
    dones = [e for e in events if e["event"] == "done"]
    assert dones == [{"event": "done", "session_id": sess.id, "reason": "finished"}]


def test_quick_200_back_to_waiting_when_turns_remain(
    session, client, user_and_headers, monkeypatch
):
    """quick 未轮尽路径：max_turns=3 + 已有 1 条 complete → waiting（不起 done）。

    registry 预置 SessionParams(max_turns=3)：turns_done=1（已有 complete
    一条）+ 本轮 1 = 2 < 3 → waiting；不发 done（SSE 流保持，等学生下一条
    消息）。注意 plan_finalize_target 的 +1 即本轮（turns_done=1 时
    1+1=2，max_turns=2 已轮尽——故此处用 3 才能落到未轮尽分支）。
    """
    from app.core.model_provider import FakeProvider
    from app.services.session_registry import SessionParams
    import app.api.sessions as sessions_module

    events = _spy_publish(monkeypatch)
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="generating")
    session.add(
        Message(session_id=sess.id, role="assistant", agent_role="con", content="上一轮", status="complete")
    )
    session.commit()
    session_registry.set(sess.id, SessionParams(mode="debate", max_turns=3))
    msg = _make_streaming_message(session, sess.id, content="本轮加速")
    resp = client.post(f"/api/sessions/{sess.id}/quick", cookies=cookies)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"id": sess.id, "status": "waiting"}
    session.expire_all()
    assert session.get(TrainingSession, sess.id).status == "waiting"
    rows = _stream_rows(session, sess.id)
    assert rows[-1].status == "complete"
    ends = [e for e in events if e["event"] == "speech_end"]
    assert ends[0]["status"] == "complete"
    assert [e for e in events if e["event"] == "done"] == []  # 未轮尽不发 done


def test_quick_409_when_not_generating(session, client, user_and_headers):
    """409：quick 于 waiting/paused/finished/failed（api.md:92 清单字面）。"""
    user, cookies = user_and_headers
    for bad_status in ("waiting", "finished", "failed"):
        sess = _make_session(session, user.id, status=bad_status)
        resp = client.post(f"/api/sessions/{sess.id}/quick", cookies=cookies)
        assert resp.status_code == 409, bad_status
        assert resp.json()["detail"] == "仅生成中可暂停/加速"


def test_quick_409_when_paused(session, client, user_and_headers):
    """409：quick@paused（api.md:80 脚注 4 已裁定：跨线程无法保证先落库后发事件）。

    边界留白在 S2-6 实现时定为 409——语义上要求先 resume 再 quick，
    而非自动 resume+quick（自动路径在锁外交给 runner，违反 §10 有序性）。
    """
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="paused")
    _make_truncated_message(session, sess.id)
    resp = client.post(f"/api/sessions/{sess.id}/quick", cookies=cookies)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "仅生成中可暂停/加速"
    session.expire_all()
    assert session.get(TrainingSession, sess.id).status == "paused"  # 未转移


def test_quick_403_non_owner(session, client, user_and_headers):
    """403：课程教师代学生加速被拒（permissions §4 字面）。"""
    from app.core.security import create_access_token
    from app.models.course import Course
    from app.models.task import Task
    from app.models.user import User, UserRole

    owner, _ = user_and_headers
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
        owner_id=owner.id, topic="AI 限制", visibility="task", task_id=task.id, status="generating"
    )
    session.add(sess)
    session.commit()
    session.refresh(sess)
    _make_streaming_message(session, sess.id)
    resp = client.post(
        f"/api/sessions/{sess.id}/quick", cookies={"access_token": create_access_token(teacher.id)}
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "仅会话创建者可修改"


def test_quick_404_unauthorized(session, client, user_and_headers):
    """404：他人 private 会话（存在性隐藏）。"""
    from app.models.user import User

    owner, cookies = user_and_headers
    other = User(username="stu2", password_hash="x", display_name="同学2")
    session.add(other)
    session.commit()
    session.refresh(other)
    sess = _make_session(session, other.id, status="generating")
    resp = client.post(f"/api/sessions/{sess.id}/quick", cookies=cookies)
    assert resp.status_code == 404


def test_quick_500_when_no_streaming_message(session, client, user_and_headers):
    """500：generating 却无在途消息=状态与消息不一致（防御分支）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="generating")
    resp = client.post(f"/api/sessions/{sess.id}/quick", cookies=cookies)
    assert resp.status_code == 500
    assert resp.json()["detail"] == "会话状态与消息不一致"
    session.expire_all()
    assert session.get(TrainingSession, sess.id).status == "generating"  # 未转移


# ---- 状态机联动：pause→resume→quick 全链路 ----

def test_pause_resume_quick_chain_same_message(
    session, client, user_and_headers, monkeypatch, runner_session_factory
):
    """全链路：pause（截断）→ resume（同 seq 续写）→ quick（定稿+finished）。

    验证同一条消息 seq 贯穿三个端点不变（计划书完成信号「恢复续写
    同一条」），且各端点 DB 终态正确。
    """
    import app.api.sessions as sessions_module

    monkeypatch.setattr(sessions_module, "build_provider", lambda: None)
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="generating")
    msg = _make_streaming_message(session, sess.id, content="第一段")
    r1 = client.post(f"/api/sessions/{sess.id}/pause", cookies=cookies)
    assert r1.status_code == 200
    rows = _stream_rows(session, sess.id)
    assert rows[0].seq == msg.seq and rows[0].status == "paused_truncated"
    r2 = client.post(f"/api/sessions/{sess.id}/resume", cookies=cookies)
    assert r2.status_code == 200
    rows = _stream_rows(session, sess.id)
    assert rows[0].seq == msg.seq and rows[0].status == "streaming"
    r3 = client.post(f"/api/sessions/{sess.id}/quick", cookies=cookies)
    assert r3.status_code == 200
    assert r3.json()["status"] == "finished"
    rows = _stream_rows(session, sess.id)
    assert rows[0].seq == msg.seq and rows[0].status == "complete"
    session.expire_all()
    assert session.get(TrainingSession, sess.id).status == "finished"
# ---- SSE 侧联动：paused 回放 + quick 后 done ----

def test_events_replay_paused_truncated_message(
    session, client, user_and_headers, monkeypatch
):
    """paused 会话回放：截断消息重编码 + done(reason='paused')？——不发 done。

    §5.3：paused 非终态，回放完不起 done、不关流（连接保持，等 resume）。
    心跳后台关流收尾（测试辅助）。
    """
    import app.api.events as events_module

    monkeypatch.setattr(events_module, "_HEARTBEAT_INTERVAL", 0.05)
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="paused")
    session.add(
        Message(
            session_id=sess.id, role="assistant", agent_role="con",
            content="截断内容", status="paused_truncated",
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
    assert "speech_start" in kinds
    assert "speech_end" in kinds
    end = next(d for e, d in events if e == "speech_end")
    assert end["status"] == "paused_truncated"
    # §5.3：paused 非终态——回放帧（retry/start/delta/end）之后不起 done、
    # 不关流。此处唯一 done 由后台 publish_done 哨兵触发（events.py:239
    # sentinel 分支 reason 硬编码 "finished"，与 session.status 无关），
    # 且必为末帧——证明回放路径本身没产 done。
    done_indexes = [i for i, (e, _) in enumerate(events) if e == "done"]
    assert len(done_indexes) == 1 and done_indexes[0] == len(events) - 1
    # 回放段（done 之前）无 done 帧
    assert "done" not in kinds[:-1]
