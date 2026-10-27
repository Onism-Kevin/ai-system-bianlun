"""S2-8 API 层测试：analyze 端点（api.md:44）。

策略：FakeProvider 驱动，不触网；TestClient 门户模式同步执行。
9 用例：200 正常/source_ref有/source_ref无/seq过滤；422 空会话/坏JSON/空nodes；
404 private 越权；401 未登录。
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


def _analyze_json(
    *,
    node_id: str = "c1",
    node_type: str = "claim",
    node_text: str = "学生的核心主张",
    source_ref: dict | None = None,
    edges: list[dict] | None = None,
) -> str:
    """构造合法 ArgumentMap JSON。"""
    node: dict = {"id": node_id, "type": node_type, "text": node_text}
    if source_ref is not None:
        node["source_ref"] = source_ref
    return json.dumps(
        {"nodes": [node], "edges": edges or []},
        ensure_ascii=False,
    )


# ---- 200：正常返回 nodes/edges ----


def test_analyze_200_returns_nodes_edges(session, client, user_and_headers, monkeypatch):
    """POST analyze → 200 ArgumentMap nodes/edges（api.md:44）。

    FakeProvider 返回合法 JSON，验证 nodes 结构 + relation 六枚举合法值。
    """
    from app.core.model_provider import FakeProvider

    import app.api.analyze as analyze_module

    valid_json = json.dumps(
        {
            "nodes": [
                {"id": "c1", "type": "claim", "text": "学生的核心主张"},
                {"id": "e1", "type": "evidence", "text": "学生的证据"},
            ],
            "edges": [{"source": "c1", "target": "e1", "relation": "支持"}],
        },
        ensure_ascii=False,
    )
    monkeypatch.setattr(
        analyze_module, "build_provider", lambda: FakeProvider(chunks=[valid_json])
    )

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "学生的核心主张")
    resp = client.post(f"/api/sessions/{sess.id}/analyze", cookies=cookies)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "nodes" in body
    assert "edges" in body
    assert len(body["nodes"]) >= 1
    # relation 六枚举合法值
    for edge in body["edges"]:
        assert edge["relation"] in {"支持", "反驳", "补充", "依赖", "限制", "需要证据"}


# ---- 200：source_ref 有 ----


def test_analyze_200_source_ref_present(session, client, user_and_headers, monkeypatch):
    """source_ref 非 None，message_seq 在 valid set → 保留。"""
    from app.core.model_provider import FakeProvider

    import app.api.analyze as analyze_module

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    msg = _add_user_message(session, sess.id, "学生的核心主张")

    valid_json = _analyze_json(
        source_ref={"message_seq": msg.seq, "quote": "学生的核心主张"}
    )
    monkeypatch.setattr(
        analyze_module, "build_provider", lambda: FakeProvider(chunks=[valid_json])
    )

    resp = client.post(f"/api/sessions/{sess.id}/analyze", cookies=cookies)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["nodes"][0]["source_ref"] is not None
    assert body["nodes"][0]["source_ref"]["message_seq"] == msg.seq


# ---- 200：source_ref 无 ----


def test_analyze_200_source_ref_absent(session, client, user_and_headers, monkeypatch):
    """无 source_ref → 节点 source_ref 为 None。"""
    from app.core.model_provider import FakeProvider

    import app.api.analyze as analyze_module

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "学生的核心主张")

    valid_json = _analyze_json(source_ref=None)
    monkeypatch.setattr(
        analyze_module, "build_provider", lambda: FakeProvider(chunks=[valid_json])
    )

    resp = client.post(f"/api/sessions/{sess.id}/analyze", cookies=cookies)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["nodes"][0]["source_ref"] is None


# ---- 200：message_seq 不在 valid set → 过滤为 None ----


def test_analyze_200_invalid_message_seq_filtered(session, client, user_and_headers, monkeypatch):
    """source_ref.message_seq=99999（不在会话）→ 后置过滤为 None。"""
    from app.core.model_provider import FakeProvider

    import app.api.analyze as analyze_module

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "学生的核心主张")

    valid_json = _analyze_json(
        source_ref={"message_seq": 99999, "quote": "幻觉引用"}
    )
    monkeypatch.setattr(
        analyze_module, "build_provider", lambda: FakeProvider(chunks=[valid_json])
    )

    resp = client.post(f"/api/sessions/{sess.id}/analyze", cookies=cookies)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # seq 99999 不在 valid set → 过滤为 None
    assert body["nodes"][0]["source_ref"] is None


# ---- 422：空会话（无 user 消息） ----


def test_analyze_422_empty_session(session, client, user_and_headers):
    """零 user 消息 → 422 "会话无消息可分析"。"""
    user, cookies = user_and_headers
    sess = _make_session(session, user.id)

    resp = client.post(f"/api/sessions/{sess.id}/analyze", cookies=cookies)
    assert resp.status_code == 422


# ---- 422：坏 JSON（StructuredValidationError → 422，E-22） ----


def test_analyze_422_invalid_structure(session, client, user_and_headers, monkeypatch):
    """坏 JSON → 422（StructuredValidationError 映射，E-22）。"""
    from app.core.model_provider import FakeProvider

    import app.api.analyze as analyze_module

    monkeypatch.setattr(
        analyze_module,
        "build_provider",
        lambda: FakeProvider(chunks=["这不是合法 JSON"]),
    )

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "学生的核心主张")
    resp = client.post(f"/api/sessions/{sess.id}/analyze", cookies=cookies)
    assert resp.status_code == 422


# ---- 422：空 nodes（Pydantic min_length=1 拒绝） ----


def test_analyze_422_empty_nodes(session, client, user_and_headers, monkeypatch):
    """nodes:[] → Pydantic min_length=1 拒绝 → 422（E-22）。"""
    from app.core.model_provider import FakeProvider

    import app.api.analyze as analyze_module

    monkeypatch.setattr(
        analyze_module,
        "build_provider",
        lambda: FakeProvider(chunks=['{"nodes": [], "edges": []}']),
    )

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "学生的核心主张")
    resp = client.post(f"/api/sessions/{sess.id}/analyze", cookies=cookies)
    assert resp.status_code == 422


# ---- 404：private 会话越权 ----


def test_analyze_404_private_session(session, client, user_and_headers):
    """他人 private 会话 → 404（存在性隐藏）。"""
    from app.models.user import User

    owner, cookies = user_and_headers
    other = User(username="stu2", password_hash="x", display_name="同学2")
    session.add(other)
    session.commit()
    session.refresh(other)

    sess = _make_session(session, other.id)
    resp = client.post(f"/api/sessions/{sess.id}/analyze", cookies=cookies)
    assert resp.status_code == 404


# ---- 401：未登录 ----


def test_analyze_401_no_auth(session, client, user_and_headers):
    """未登录 → 401（get_current_user 依赖层）。"""
    user, _ = user_and_headers
    sess = _make_session(session, user.id)
    _add_user_message(session, sess.id, "学生的核心主张")

    resp = client.post(f"/api/sessions/{sess.id}/analyze")
    assert resp.status_code == 401
