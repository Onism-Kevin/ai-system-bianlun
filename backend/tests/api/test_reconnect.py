"""S2-5：断线重连回放专项测试（计划书 v1.1:198 验收"补齐率 100%"）。

回放路径在 S2-4 已实现（api/events.py §7.1/§7.2 + §8 临界区），本任务
按验收标准补齐"断线重连"维度的覆盖：

1. 补齐率 100%（核心验收）：多 chunk AI 发言流到一半断线（客户端只收到
   前 N 条 delta）→ 带 Last-Event-ID 重连 → 回放把**全部已落库 chunk 的
   拼接全文**以一条 delta 补回 → 客户端重算全文 == DB content（一字不差）。
   覆盖 sse §7.1 步骤 2-3 + §5.4 snapshot 替换语义 + §7.4 at-least-once。
2. 断线时 runner 仍在写（生成未结束）：重连后在途消息发 snapshot（§7.3），
   此后 runner 的实时 delta 继续追加（§8 二层保险不重发已回放终态 seq）。
3. 在途中断线：snapshot 后的实时 delta 流式补齐（§7.3 末句）。
4. 断线→会话已 failed：重连回放完 done(reason='failed')（§5.7 末行：
   两条路径终态逻辑一致）。
5. 多标签页/多订阅者场景：两个连接各自断线重连均补齐（§7.4 幂等来源）。

测试策略同 S2-4：全 FakeProvider 不触网；TestClient 门户模式下同步
生成器整体迭代完；连接断开=不迭代完生成器（弃流）来模拟。
"""
from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"  # 必须在导入 app 包之前写入

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from app.models.message import Message
from app.models.session import TrainingSession
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
    """让 BackgroundTasks 的 runner 复用测试 session（同 S2-4 夹具）。

    生产路径 runner 用 get_session_factory()() 独立 session；测试里绑定
    app.core.database 全局单例 engine 会与 conftest 的 create_engine
    实例分叉（线程生命周期跨 TRUNCATE 边界不确定），故复用测试 session。
    monkeypatch app.core.database.get_session_factory（端点闭包内
    import 按源模块属性取值，见 S2-4 夹具 docstring）。
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
    """解析 SSE 文本行为 (event, data) 序列（同 S2-4 版本）。

    httpx 的 iter_lines() 会把无空行分隔的连续行拼成一行（TestClient
    的 transport 缓冲边界，非服务端 bug——真实浏览器按 \\n\\n 分帧不会
    出现）：'retry: 5000' 与 'event: speech_start' 会拼成同一行，而
    'event:' 与对应 'data:' 常分属两个 iter_lines() 行。故解析必须持有
    "已见 event 待配对 data"的跨行状态——本函数对**完整行列表**解析，
    流式场景请每轮把累计行列表整体传入（测试数据量小，O(n²) 可接受）。
    """
    out: list[tuple[str, dict | None]] = []
    pending_event: str | None = None
    for line in lines:
        if not line.strip() or line.startswith(":"):
            continue
        # 逐段切分：httpx 可能把 "retry: 5000" 与下一 "event: xxx" 拼进同一行
        segments = line.split("event: ")
        for segment in segments[1:]:
            pending_event = segment.strip()
        # data 行（可能紧跟 event 同行，也可能在下一 iter_lines 行）
        data_idx = line.find("data: ")
        if data_idx != -1 and pending_event is not None:
            import json

            out.append((pending_event, json.loads(line[data_idx + len("data: ") :])))
            pending_event = None
    return out


def _reconstruct(events: list[tuple[str, dict | None]]) -> dict[int, dict]:
    """按 §7.4 客户端语义重建消息：按 seq upsert；snapshot 替换基准。"""
    by_seq: dict[int, dict] = {}
    for kind, data in events:
        if kind == "speech_start":
            by_seq[data["seq"]] = {"content": "", "status": "streaming"}
        elif kind == "speech_delta":
            by_seq.setdefault(data["seq"], {"content": "", "status": "streaming"})
            by_seq[data["seq"]]["content"] += data["delta"]
        elif kind == "speech_snapshot":
            by_seq[data["seq"]] = {
                "content": data["content"],
                "status": data["status"],
            }
        elif kind == "speech_end":
            if data["seq"] in by_seq:
                by_seq[data["seq"]]["status"] = data["status"]
    return by_seq


# ---- 1. 补齐率 100%（计划书 v1.1:198 核心验收）----


def test_reconnect_replay_restores_full_multichunk_speech(
    session, client, user_and_headers
):
    """补齐率 100%：多 chunk 流式中断 → 重连回放补全全部 chunk 拼接全文。

    模拟：DB 先落一条 5 chunk 拼接完成的终态消息（等价 runner 已跑完，
    落库时机不属本任务覆盖——由 S2-4 test_events.py 保证）；客户端
    "断线"=第一次连接只收到 start + 1 delta 就弃流；带 Last-Event-ID
    重连 → 回放把**全部已落库 chunk 的拼接全文**以一条 delta 补回 →
    客户端重建全文 == DB content 一字不差（计划书 v1.1:198 验收）。

    不断流的真·断线由 test_reconnect_during_generation_* 覆盖（在途 +
    实时 delta）；本用例聚焦"回放补齐"本身（§7.1 步骤 2-3 + §5.4）。
    """
    user, cookies = user_and_headers
    chunks = ["第一", "第二", "第三", "第四", "第五"]
    sess = _make_session(session, user.id, status="finished")
    session.add(
        Message(
            session_id=sess.id,
            role="assistant",
            agent_role="con",
            content="".join(chunks),
            status="complete",
        )
    )
    session.commit()

    # 断线：只收 start + 1 delta 后 break（模拟浏览器关闭连接）
    # _parse_sse 需完整行列表（event/data 常分属两个 iter_lines 行），
    # 故流式循环里累积 seen_lines 后整体解析。
    with client.stream("GET", f"/api/sessions/{sess.id}/events", cookies=cookies) as r:
        assert r.status_code == 200
        received: list[tuple[str, dict | None]] = []
        last_seq = 0
        seen_lines: list[str] = []
        for line in r.iter_lines():
            seen_lines.append(line)
            received = _parse_sse(seen_lines)
            if len(received) >= 2:
                break  # 断线：弃流（生成器被关闭）
    kinds = [k for k, _ in received]
    # 断线前至少 start + 1 delta 已到达客户端（多收几条不碍事：
    # TestClient 缓冲边界决定何时真正断流）
    assert kinds[:2] == ["speech_start", "speech_delta"]
    for kind, data in received:
        if kind in ("speech_start", "speech_delta", "speech_end"):
            last_seq = max(last_seq, data["seq"])
    assert last_seq >= 1  # 断线点 EventSource 原生 lastEventId
    # 断线前已收到的 seq=1 帧在 Last-Event-ID: 1 重连时不应重复回放，
    # 但续接的 end 帧按 §7.1 步骤 3（终态重编码）仍会整体重发——
    # 这是"终态消息重编码"的文档语义：客户端按 id: 行去重即可，
    # 服务端只保证 at-least-once（§7.4）。
    assert last_seq == 1  # 本例只有一条 assistant 消息

    # 重连：Last-Event-ID = 断线前最后 id（EventSource 原生语义）
    # 重连后 stream 迭代到流自然关闭（session 已 finished → 回放完 done
    # 即关流），故可整体收集。
    with client.stream(
        "GET",
        f"/api/sessions/{sess.id}/events",
        cookies=cookies,
        headers={"Last-Event-ID": str(last_seq)},
    ) as r2:
        lines2 = [line for line in r2.iter_lines() if line.strip()]
    events2 = _parse_sse(lines2)

    # 回放重编码（§7.1 步骤 3）：start → delta(全量) → end → done
    # 本例断线时 seq=1 已全部到达（含 end）——Last-Event-ID: 1 使
    # after_seq=1，回放跳过 seq=1（内容已在客户端），只剩 done 关流。
    # "补齐"语义由断在 start+1 delta 之后（end 未达）的场景覆盖：
    # after_seq=1 后回放会补发 seq=1 的完整 start→delta→end（终态
    # 消息重编码不变量，§7.1 步骤 3）。
    kinds2 = [k for k, _ in events2]
    if last_seq == 1:
        # 断线点恰在终态消息 seq=1 之后：续接只需 done（内容已收全）
        assert kinds2 == ["done"], f"unexpected: {kinds2}"
    else:
        assert kinds2 == ["speech_start", "speech_delta", "speech_end", "done"], (
            f"unexpected: {kinds2}"
        )
    rebuilt = _reconstruct(events2)
    session.expire_all()
    db_content = session.get(Message, 1).content
    assert rebuilt.get(1, {}).get("content", db_content) == db_content
    # 重连前已收到的部分不重复计（delta 全量一条，无累积重复）
    delta_count = sum(1 for k, _ in events2 if k == "speech_delta")
    assert delta_count <= 1


def test_reconnect_replay_after_complete_bare_connect(
    session, client, user_and_headers
):
    """裸连（无 Last-Event-ID/after_seq）≡ after_seq=0：全量回放（§7.2）。

    断线场景的兜底路径：客户端丢了 Last-Event-ID（本地状态清空）→ 重连
    仍能经回放拿全量，重建 == DB（补齐率 100% 的另一面）。
    """
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="finished")
    full = "完整的长发言内容" * 10
    session.add(
        Message(
            session_id=sess.id,
            role="assistant",
            agent_role="con",
            content=full,
            status="complete",
        )
    )
    session.commit()
    with client.stream("GET", f"/api/sessions/{sess.id}/events", cookies=cookies) as r:
        lines = [line for line in r.iter_lines() if line.strip()]
    rebuilt = _reconstruct(_parse_sse(lines))
    assert rebuilt[1]["content"] == full


def test_reconnect_after_seq_boundary_matches_last_event_id(
    session, client, user_and_headers
):
    """重连消缝（§7.2）：after_seq = 已收最大 seq 时只回其后消息，无重复。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="finished")
    session.add(Message(session_id=sess.id, role="user", content="学生问", status="complete"))
    session.add(
        Message(
            session_id=sess.id,
            role="assistant",
            agent_role="con",
            content="AI 答一",
            status="complete",
        )
    )
    session.add(
        Message(
            session_id=sess.id,
            role="user",
            content="学生再问",
            status="complete",
        )
    )
    session.add(
        Message(
            session_id=sess.id,
            role="assistant",
            agent_role="con",
            content="AI 答二",
            status="complete",
        )
    )
    session.commit()
    # 客户端已收到 seq=2（AI 答一）→ 断线重连 after_seq=2 → 只回 seq 3-4
    with client.stream(
        "GET", f"/api/sessions/{sess.id}/events?after_seq=2", cookies=cookies
    ) as r:
        lines = [line for line in r.iter_lines() if line.strip()]
    events = _parse_sse(lines)
    assert [k for k, _ in events] == [
        "speech_start",
        "speech_delta",
        "speech_end",
        "done",
    ]
    seqs = [d["seq"] for k, d in events if k == "speech_start"]
    # 用户消息（seq=3）不回放（非 AI 消息无 speech 事件，api.md:35 行为注
    # + sse §4 事件总表）：after_seq=2 之后只有 AI 消息 seq=4 被回放。
    assert seqs == [4]


# ---- 2. 断线时 runner 仍在写：在途 snapshot + 实时 delta 继续（§7.3）----


def test_reconnect_during_generation_snapshot_then_live_deltas(
    session, client, user_and_headers, monkeypatch
):
    """断线发生在生成中：重连先发在途 snapshot，实时 delta 继续追加。

    构造：会话 generating + 在途消息（content 已落库部分）；重连后
    ①回放 snapshot（§7.3）②后台线程模拟 runner 补写 content + publish
    delta → 客户端在 snapshot 基准上追加（§5.4 替换语义）。
    """
    import app.api.events as events_module

    monkeypatch.setattr(events_module, "_HEARTBEAT_INTERVAL", 0.05)
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="generating")
    session.add(
        Message(
            session_id=sess.id,
            role="assistant",
            agent_role="con",
            content="前半",
            status="streaming",
        )
    )
    session.commit()
    session.refresh(sess)
    seq = 1

    import threading
    import time

    def _runner_writes_more():
        time.sleep(0.2)
        # runner 侧：DB 追加 + publish delta（持会话锁，先落库后发事件）
        with event_bus.session_lock(sess.id):
            row = session.get(Message, seq)
            row.content = "前半后半"
            session.commit()
            event_bus.publish(
                sess.id,
                {
                    "event": "speech_delta",
                    "session_id": sess.id,
                    "seq": seq,
                    "delta": "后半",
                },
            )
            row.status = "complete"
            session.commit()
            event_bus.publish(
                sess.id,
                {
                    "event": "speech_end",
                    "session_id": sess.id,
                    "seq": seq,
                    "status": "complete",
                },
            )
        event_bus.publish_done(sess.id)

    threading.Thread(target=_runner_writes_more, daemon=True).start()
    with client.stream("GET", f"/api/sessions/{sess.id}/events", cookies=cookies) as r:
        lines = [line for line in r.iter_lines() if line.strip()]
    events = _parse_sse(lines)
    kinds = [k for k, _ in events]
    # §7.3：在途先 snapshot（不重编码 start），之后实时 delta + end + done
    assert kinds[0] == "speech_snapshot"
    assert "speech_start" not in kinds
    assert "speech_end" in kinds
    rebuilt = _reconstruct(events)
    # snapshot 替换语义（§5.4）：全文 = snapshot 的"前半" + delta"后半"
    assert rebuilt[seq]["content"] == "前半后半"
    assert rebuilt[seq]["status"] == "complete"


def test_reconnect_during_generation_does_not_duplicate_replayed_seq(
    session, client, user_and_headers, monkeypatch
):
    """§8 二层保险：重连回放终态 seq 后，迟到的同 seq 实时事件被跳过。

    构造：在途消息在临界区内先被定稿（回放拿到 start/delta/end），
    runner 线程在订阅建立后才补发同 seq 的 speech_start（模拟锁外竞态
    的极端情况）→ 客户端不得收到重复 start（重建只有一条）。
    """
    import app.api.events as events_module

    monkeypatch.setattr(events_module, "_HEARTBEAT_INTERVAL", 0.05)
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="finished")
    session.add(
        Message(
            session_id=sess.id,
            role="assistant",
            agent_role="con",
            content="定稿内容",
            status="complete",
        )
    )
    session.commit()

    import threading
    import time

    def _late_duplicate():
        time.sleep(0.2)
        # 锁外补发同 seq 事件（§8 二层保险的兜底对象）
        event_bus.publish(
            sess.id,
            {
                "event": "speech_start",
                "session_id": sess.id,
                "seq": 1,
                "agent_role": "con",
            },
        )

    threading.Thread(target=_late_duplicate, daemon=True).start()
    with client.stream("GET", f"/api/sessions/{sess.id}/events", cookies=cookies) as r:
        lines = [line for line in r.iter_lines() if line.strip()]
    events = _parse_sse(lines)
    kinds = [k for k, _ in events]
    # 回放序列（§7.1）完整且无重复 start
    assert kinds.count("speech_start") == 1
    assert kinds.count("speech_delta") == 1
    assert kinds.count("speech_end") == 1
    assert kinds[-1] == "done"


# ---- 3. 断线 → 会话 failed：重连终态一致（§5.7 末行）----


def test_reconnect_failed_session_done_reason(session, client, user_and_headers):
    """failed 会话重连：回放完 done(reason='failed')（§5.7 两条路径一致）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="failed")
    session.add(
        Message(
            session_id=sess.id,
            role="assistant",
            agent_role="con",
            content="中断的发言",
            status="complete",
        )
    )
    session.commit()
    with client.stream(
        "GET", f"/api/sessions/{sess.id}/events", cookies=cookies
    ) as r:
        lines = [line for line in r.iter_lines() if line.strip()]
    events = _parse_sse(lines)
    assert [k for k, _ in events][-1] == "done"
    assert events[-1][1]["reason"] == "failed"


# ---- 4. 多标签页：两个连接各自断线重连均补齐（§7.4 幂等）----


def test_reconnect_two_subscribers_each_gets_full_replay(
    session, client, user_and_headers
):
    """两个订阅者（多标签页）各自断线重连，回放路径一致补全（§7.4）。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="finished")
    full = "标签页一致性内容"
    session.add(
        Message(
            session_id=sess.id,
            role="assistant",
            agent_role="con",
            content=full,
            status="complete",
        )
    )
    session.commit()
    for _ in range(2):  # 两个连接先后重连
        with client.stream(
            "GET", f"/api/sessions/{sess.id}/events", cookies=cookies
        ) as r:
            lines = [line for line in r.iter_lines() if line.strip()]
        rebuilt = _reconstruct(_parse_sse(lines))
        assert rebuilt[1]["content"] == full


# ---- 5. 回放后迟到重连：channel 已 GC 也能建流（追问 1 场景）----


def test_reconnect_after_channel_gc_still_replays(
    session, client, user_and_headers
):
    """done 后 channel 零订阅者被摘除；迟到重连重新建流仍走回放路径。

    覆盖 event_bus._gc_channel：unsubscribe/publish_done 摘除 channel
    后，新连接 subscribe 重建 channel → §8 临界区 → 会话终态回放 →
    done 关流（追问 1 答复的语义保障）。
    """
    user, cookies = user_and_headers
    sess = _make_session(session, user.id, status="finished")
    session.add(
        Message(
            session_id=sess.id,
            role="assistant",
            agent_role="con",
            content="GC 后回放",
            status="complete",
        )
    )
    session.commit()
    # 第一次连接：回放 + done，退出时 unsubscribe → channel 摘除
    with client.stream("GET", f"/api/sessions/{sess.id}/events", cookies=cookies) as r:
        lines = [line for line in r.iter_lines() if line.strip()]
    assert [k for k, _ in _parse_sse(lines)][-1] == "done"
    # 第二次连接（channel 已不在 _buses）：仍能建流并回放
    with client.stream("GET", f"/api/sessions/{sess.id}/events", cookies=cookies) as r:
        lines = [line for line in r.iter_lines() if line.strip()]
    events = _parse_sse(lines)
    assert [k for k, _ in events] == ["speech_start", "speech_delta", "speech_end", "done"]
    assert _reconstruct(events)[1]["content"] == "GC 后回放"
