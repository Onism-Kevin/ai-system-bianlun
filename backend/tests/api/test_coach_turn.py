"""S2-9 API 层测试：coach_turn 端点（api.md:45）。

策略：FakeProvider 驱动，不触网；TestClient 门户模式同步执行。
9 用例：200 coach/rebuttal/首轮/quote_refs过滤；422 非法mode/空会话/坏JSON；
404 private；401 未登录。
"""
from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"  # 必须在导入 app 包之前写入

import json

from tests.api.test_events import (
    _clean_bus,
    _make_session,
    client,
    user_and_headers,
)
from tests.models.conftest import engine, session  # noqa: F401


def _add_user_message(session_db, session_id: int, content: str, status: str = "complete"):
    """创建一条 user 消息，返回 Message ORM 对象（含 seq）。"""
    from app.models.message import Message

    msg = Message(
        session_id=session_id,
        role="user",
        agent_role=None,
        content=content,
        status=status,
    )
    session_db.add(msg)
    session_db.commit()
    session_db.refresh(msg)
    return msg


def _add_assistant_message(session_db, session_id: int, content: str, status: str = "complete"):
    """创建一条 assistant 消息，返回 Message ORM 对象（含 seq）。"""
    from app.models.message import Message

    msg = Message(
        session_id=session_id,
        role="assistant",
        agent_role="con",
        content=content,
        status=status,
    )
    session_db.add(msg)
    session_db.commit()
    session_db.refresh(msg)
    return msg


def _coach_turn_json(
    *,
    quote_refs: list[dict] | None = None,
) -> str:
    """构造合法 CoachTurn JSON。"""
    data = {
        "question": "你是否考虑过数据来源的时效性？",
        "focus": "区分相关与因果",
        "hints": ["可以追问数据的时间范围"],
    }
    if quote_refs is not None:
        data["quote_refs"] = quote_refs
    return json.dumps(data, ensure_ascii=False)


# ---- 200：coach 模式 ----


def test_coach_turn_200_coach_mode(session, client, user_and_headers, monkeypatch):
    """POST coach_turn mode=coach → 200 CoachTurn 四字段（api.md:45）。"""
    from app.core.model_provider import FakeProvider

    import app.api.coach_turn as coach_module

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    msg = _add_user_message(session, sess.id, "我认为AI应该限制使用")

    valid_json = _coach_turn_json(quote_refs=[{"seq": msg.seq, "quote": "我认为AI应该限制使用"}])
    monkeypatch.setattr(
        coach_module, "build_provider", lambda: FakeProvider(chunks=[valid_json])
    )

    resp = client.post(
        f"/api/sessions/{sess.id}/coach_turn",
        json={"mode": "coach"},
        cookies=cookies,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "question" in body
    assert "focus" in body
    assert "hints" in body
    assert "quote_refs" in body


# ---- 200：rebuttal 模式 ----


def test_coach_turn_200_rebuttal_mode(session, client, user_and_headers, monkeypatch):
    """POST coach_turn mode=rebuttal → 200 CoachTurn 四字段。"""
    from app.core.model_provider import FakeProvider

    import app.api.coach_turn as coach_module

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    msg = _add_user_message(session, sess.id, "我认为AI应该限制使用")

    valid_json = _coach_turn_json(quote_refs=[{"seq": msg.seq, "quote": "我认为AI应该限制使用"}])
    monkeypatch.setattr(
        coach_module, "build_provider", lambda: FakeProvider(chunks=[valid_json])
    )

    resp = client.post(
        f"/api/sessions/{sess.id}/coach_turn",
        json={"mode": "rebuttal"},
        cookies=cookies,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "question" in body
    assert "focus" in body
    assert "hints" in body
    assert "quote_refs" in body


# ---- 422：非法 mode ----


def test_coach_turn_422_invalid_mode(session, client, user_and_headers):
    """mode='unknown' → Pydantic Literal 拒绝 → 422。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "学生的核心主张")

    resp = client.post(
        f"/api/sessions/{sess.id}/coach_turn",
        json={"mode": "unknown"},
        cookies=cookies,
    )
    assert resp.status_code == 422


# ---- 422：空会话（无 user 消息） ----


def test_coach_turn_422_empty_session(session, client, user_and_headers):
    """零 user 消息 → 422 "会话无消息可分析"。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)

    resp = client.post(
        f"/api/sessions/{sess.id}/coach_turn",
        json={"mode": "coach"},
        cookies=cookies,
    )
    assert resp.status_code == 422


# ---- 200：quote_refs 过滤（无效 seq 被移除） ----


def test_coach_turn_200_quote_refs_filtered(session, client, user_and_headers, monkeypatch):
    """quote_refs 含无效 seq → 过滤后移除（200，不是 422）。"""
    from app.core.model_provider import FakeProvider

    import app.api.coach_turn as coach_module

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    msg = _add_user_message(session, sess.id, "学生的核心主张")

    # quote_refs 含一条有效（msg.seq）一条无效（99999）
    valid_json = _coach_turn_json(
        quote_refs=[
            {"seq": msg.seq, "quote": "学生的核心主张"},
            {"seq": 99999, "quote": "幻觉引用"},
        ]
    )
    monkeypatch.setattr(
        coach_module, "build_provider", lambda: FakeProvider(chunks=[valid_json])
    )

    resp = client.post(
        f"/api/sessions/{sess.id}/coach_turn",
        json={"mode": "coach"},
        cookies=cookies,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 有效条目保留，无效条目移除
    assert len(body["quote_refs"]) == 1
    assert body["quote_refs"][0]["seq"] == msg.seq


# ---- 422：坏 JSON（StructuredValidationError → 422，E-22） ----


def test_coach_turn_422_invalid_structure(session, client, user_and_headers, monkeypatch):
    """坏 JSON → 422（StructuredValidationError 映射，E-22）。"""
    from app.core.model_provider import FakeProvider

    import app.api.coach_turn as coach_module

    monkeypatch.setattr(
        coach_module,
        "build_provider",
        lambda: FakeProvider(chunks=["这不是合法 JSON"]),
    )

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "学生的核心主张")
    resp = client.post(
        f"/api/sessions/{sess.id}/coach_turn",
        json={"mode": "coach"},
        cookies=cookies,
    )
    assert resp.status_code == 422


# ---- 404：private 会话越权 ----


def test_coach_turn_404_private_session(session, client, user_and_headers):
    """他人 private 会话 → 404（存在性隐藏）。"""
    from app.models.user import User

    owner, cookies = user_and_headers
    other = User(username="stu2", password_hash="x", display_name="同学2")
    session.add(other)
    session.commit()
    session.refresh(other)

    sess = _make_session(session, other.id)
    resp = client.post(
        f"/api/sessions/{sess.id}/coach_turn",
        json={"mode": "coach"},
        cookies=cookies,
    )
    assert resp.status_code == 404


# ---- 401：未登录 ----


def test_coach_turn_401_no_auth(session, client, user_and_headers):
    """未登录 → 401（get_current_user 依赖层）。"""
    user, _ = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "学生的核心主张")

    resp = client.post(
        f"/api/sessions/{sess.id}/coach_turn",
        json={"mode": "coach"},
    )
    assert resp.status_code == 401


# ---- 200：首轮（无 assistant 消息） ----


def test_coach_turn_200_first_turn_no_assistant(session, client, user_and_headers, monkeypatch):
    """仅 1 条 user 消息，assistant 消息为 0 → coach_turn 正常返回 200。

    首轮是真实使用中的常见场景——学生第一次训练时 AI 还没追问过。
    验证 assistant 消息为空时端点不报错。
    """
    from app.core.model_provider import FakeProvider

    import app.api.coach_turn as coach_module

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    msg = _add_user_message(session, sess.id, "我认为AI应该限制使用")

    valid_json = _coach_turn_json(quote_refs=[{"seq": msg.seq, "quote": "我认为AI应该限制使用"}])
    monkeypatch.setattr(
        coach_module, "build_provider", lambda: FakeProvider(chunks=[valid_json])
    )

    resp = client.post(
        f"/api/sessions/{sess.id}/coach_turn",
        json={"mode": "coach"},
        cookies=cookies,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "question" in body
    assert "focus" in body
    assert "hints" in body
    assert "quote_refs" in body
