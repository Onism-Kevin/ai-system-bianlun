"""S2-4 服务层单测（docs/design/s2_4_sse_design.md §9：编排器 + 总线两层）。

全部 FakeProvider 驱动（app.core.model_provider.FakeProvider：chunks +
error + error_after），不触网；DB 用 tests.models.conftest 的 sfb_test
底座（每用例 TRUNCATE）。event_bus 每用例 reset（进程单例，跨用例
隔离）。

覆盖（§9 表编排器行）：
- 事件序列 speech_start → speech_delta* → speech_end（总线 record）；
- DB 行：assistant streaming→complete、content 拼接、agent_role 按
  mode 映射各一例（coach/coach.py、debate/con→rebuttal.py）；
- session 转移 waiting→generating→waiting（有剩余轮次）/ finished
  （轮尽 done）；
- fatal 三异常逐一类：error(fatal=true) → done(failed) 序列 +
  session=failed + 在途消息定稿 complete（Q2 拍板）；
- 非 fatal（ModelServerError 4xx）：error(fatal=false) 后不关流、
  消息留 streaming；
- prompt 只含历史（本轮空 assistant 消息不喂 prompt——组装顺序
  防回归）。
"""
from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"  # 必须在导入 app 包之前写入

import pytest  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core import exceptions  # noqa: E402
from app.core.model_provider import FakeProvider  # noqa: E402
from app.models.message import Message  # noqa: E402
from app.models.session import TrainingSession  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services.debate_runner import run_generation  # noqa: E402
from app.services.event_bus import event_bus  # noqa: E402
from app.services.session_registry import SessionParams, session_registry  # noqa: E402

# 复用 models 底座（engine 建表 + 每用例 TRUNCATE + 测试 session）
# engine fixture 定义在 tests/models/conftest.py（模块级作用域，需显式导入）
from tests.models.conftest import engine, session  # noqa: E402,F401


class RecordingBus:
    """包一层 event_bus：记录 publish/publish_done 调用序列（断言事件顺序）。"""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.events: list[dict] = []
        self.done_calls: list[int] = []

    def __getattr__(self, name):
        # 其余方法（session_lock/controller/publish_done 之外）透传真总线
        return getattr(self._inner, name)

    def session_lock(self, session_id: int):
        return self._inner.session_lock(session_id)

    def controller(self, session_id: int):
        return self._inner.controller(session_id)

    def publish(self, session_id: int, event: dict) -> None:
        self.events.append(event)
        self._inner.publish(session_id, event)

    def publish_done(self, session_id: int) -> None:
        self.done_calls.append(session_id)
        self._inner.publish_done(session_id)


@pytest.fixture()
def bus(monkeypatch) -> RecordingBus:
    """替换 debate_runner 模块级引用的 event_bus（runner import 时绑定）。"""
    recording = RecordingBus(event_bus)
    import app.services.debate_runner as runner_module

    monkeypatch.setattr(runner_module, "event_bus", recording)
    return recording


@pytest.fixture(autouse=True)
def _clean_bus():
    event_bus.reset()
    session_registry.reset()
    yield
    event_bus.reset()
    session_registry.reset()


def _make_session(db, *, status: str = "waiting", mode: str = "debate", max_turns: int = 1):
    user = User(username="stu1", password_hash="x", display_name="同学")
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role="student"))
    sess = TrainingSession(
        owner_id=user.id, topic="AI 是否应限制使用", status=status
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def _run(db, session_id: int, provider: FakeProvider, params: SessionParams):
    run_generation(
        session_id,
        db=db,
        provider=provider,
        model="fake-model",
        params=params,
    )


def _events_of(bus: RecordingBus, name: str) -> list[dict]:
    return [e for e in bus.events if e["event"] == name]


# ---- 正常路径 ----

def test_event_sequence_start_delta_end(session, bus):
    sess = _make_session(session)
    _run(
        session,
        sess.id,
        FakeProvider(chunks=["我认为", "应当限制。"]),
        SessionParams(mode="debate", max_turns=1),
    )
    kinds = [e["event"] for e in bus.events]
    assert kinds == [
        "speech_start",
        "speech_delta",
        "speech_delta",
        "speech_end",
        "done",
    ]
    assert _events_of(bus, "speech_delta")[0]["delta"] == "我认为"
    assert bus.done_calls == [sess.id]


def test_message_row_landed_complete_with_full_content(session, bus):
    sess = _make_session(session)
    _run(
        session,
        sess.id,
        FakeProvider(chunks=["第一", "第二"]),
        SessionParams(mode="debate", max_turns=1),
    )
    session.expire_all()
    msg = session.scalar(
        select(Message).where(Message.session_id == sess.id, Message.role == "assistant")
    )
    assert msg is not None
    assert msg.status == "complete"
    assert msg.content == "第一第二"
    assert msg.role == "assistant"  # schema_v3:22：AI='assistant'（非 'agent'）


def test_agent_role_by_mode_coach(session, bus):
    sess = _make_session(session)
    _run(
        session,
        sess.id,
        FakeProvider(chunks=["你的论据？"]),
        SessionParams(mode="coach", max_turns=1),
    )
    session.expire_all()
    msg = session.scalar(select(Message).where(Message.session_id == sess.id))
    assert msg.agent_role == "coach"


def test_agent_role_by_mode_debate_is_con(session, bus):
    sess = _make_session(session)
    _run(
        session,
        sess.id,
        FakeProvider(chunks=["反方观点"]),
        SessionParams(mode="debate", max_turns=1),
    )
    session.expire_all()
    msg = session.scalar(select(Message).where(Message.session_id == sess.id))
    assert msg.agent_role == "con"  # 拍板 1：debate 固定 con


def test_session_transition_to_waiting_when_turns_remain(session, bus):
    sess = _make_session(session)
    _run(
        session,
        sess.id,
        FakeProvider(chunks=["一条发言"]),
        SessionParams(mode="debate", max_turns=2),
    )
    session.expire_all()
    assert session.get(TrainingSession, sess.id).status == "waiting"
    assert bus.done_calls == []  # 轮未尽不发 done（sse §5.10）


def test_session_transition_to_finished_when_turns_exhausted(session, bus):
    sess = _make_session(session)
    _run(
        session,
        sess.id,
        FakeProvider(chunks=["最后一条"]),
        SessionParams(mode="debate", max_turns=1),
    )
    session.expire_all()
    assert session.get(TrainingSession, sess.id).status == "finished"
    done = _events_of(bus, "done")
    assert done == [{"event": "done", "session_id": sess.id, "reason": "finished"}]


def test_prompt_excludes_inflight_assistant_message(session, bus, monkeypatch):
    """历史先读后 INSERT：本轮空 assistant 消息不得进 prompt（防回归）。"""
    sess = _make_session(session)
    captured: list[list[dict]] = []

    class CapturingProvider(FakeProvider):
        def generate_stream(self, *, model, messages, temperature=0.7, timeout=120.0):
            captured.append(messages)
            return super().generate_stream(
                model=model, messages=messages, temperature=temperature, timeout=timeout
            )

    user_msg = Message(session_id=sess.id, role="user", content="我认为应当限制")
    session.add(user_msg)
    session.commit()

    _run(
        session,
        sess.id,
        CapturingProvider(chunks=["反驳"]),
        SessionParams(mode="debate", max_turns=1),
    )
    assert captured, "provider 未被调用"
    rendered = captured[0][-1]["content"]
    assert "1. [学生] 我认为应当限制" in rendered
    assert "2. [反方]" not in rendered  # 本轮空消息不入 prompt


# ---- fatal 路径（sse §5.7 表逐一类） ----

@pytest.mark.parametrize(
    "exc",
    [
        exceptions.ModelConnectionError("拒绝连接"),
        exceptions.ModelTimeoutError("读超时"),
        exceptions.ModelServerError("502 坏网关", http_status=502),
    ],
)
def test_fatal_errors_sequence_and_landing(session, bus, exc):
    sess = _make_session(session)
    _run(
        session,
        sess.id,
        FakeProvider(chunks=["半句话"], error=exc, error_after=1),
        SessionParams(mode="debate", max_turns=1),
    )
    kinds = [e["event"] for e in bus.events]
    assert kinds == ["speech_start", "speech_delta", "error", "done"]
    err = bus.events[-2]
    assert err["fatal"] is True
    assert err["retryable"] is True
    assert err["code"] in {"model_connection", "model_timeout", "model_server"}
    done = bus.events[-1]
    assert done == {"event": "done", "session_id": sess.id, "reason": "failed"}

    session.expire_all()
    assert session.get(TrainingSession, sess.id).status == "failed"
    msg = session.scalar(select(Message).where(Message.session_id == sess.id))
    assert msg.status == "complete"  # Q2 拍板：fatal 不可 resume
    assert msg.content == "半句话"  # 已生成部分保留


def test_internal_error_is_fatal_not_retryable(session, bus):
    sess = _make_session(session)
    _run(
        session,
        sess.id,
        FakeProvider(chunks=["x"], error=RuntimeError("炸了"), error_after=1),
        SessionParams(mode="debate", max_turns=1),
    )
    err = bus.events[-2]
    assert err["code"] == "internal"
    assert err["fatal"] is True
    assert err["retryable"] is False


# ---- 非 fatal 路径 ----

def test_non_fatal_4xx_error_keeps_stream_open(session, bus):
    sess = _make_session(session)
    _run(
        session,
        sess.id,
        FakeProvider(
            chunks=["片段"],
            error=exceptions.ModelServerError("400 坏请求", http_status=400),
            error_after=1,
        ),
        SessionParams(mode="debate", max_turns=1),
    )
    kinds = [e["event"] for e in bus.events]
    assert kinds == ["speech_start", "speech_delta", "error"]
    err = bus.events[-1]
    assert err["fatal"] is False
    assert err["retryable"] is False
    assert err["code"] == "model_server"
    assert bus.done_calls == []  # 不关流（§5.7 fatal=false 语义）

    session.expire_all()
    assert session.get(TrainingSession, sess.id).status == "generating"  # 未转移
    msg = session.scalar(select(Message).where(Message.session_id == sess.id))
    assert msg.status == "streaming"  # 命运留待后续 speech_end/新 error


def test_structured_validation_is_non_fatal(session, bus):
    sess = _make_session(session)
    _run(
        session,
        sess.id,
        FakeProvider(
            chunks=["片段"],
            error=exceptions.StructuredValidationError("结构不符", raw_text="…"),
            error_after=1,
        ),
        SessionParams(mode="debate", max_turns=1),
    )
    err = bus.events[-1]
    assert err["code"] == "structured_validation"
    assert err["fatal"] is False
    assert bus.done_calls == []


# ---- 防御路径 ----

def test_missing_session_aborts_without_events(session, bus):
    _run(
        session,
        999999,
        FakeProvider(chunks=["x"]),
        SessionParams(mode="debate", max_turns=1),
    )
    assert bus.events == []
    assert bus.done_calls == []


def test_non_waiting_session_aborts_without_events(session, bus):
    sess = _make_session(session, status="generating")
    _run(
        session,
        sess.id,
        FakeProvider(chunks=["x"]),
        SessionParams(mode="debate", max_turns=1),
    )
    assert bus.events == []
    session.expire_all()
    assert session.get(TrainingSession, sess.id).status == "generating"  # 未被改动
