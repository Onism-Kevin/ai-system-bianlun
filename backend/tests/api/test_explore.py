"""S2-7 API 层测试：explore 端点（api.md:43）。

策略：FakeProvider 驱动，不触网；TestClient 门户模式同步执行。
5 用例：200 四字段 / 422 空 topic / 404 private 越权 / 401 未登录 / 422 坏 JSON。
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


def _valid_explore_json() -> str:
    """构造合法 ExploreOut JSON（四字段齐备）。"""
    return json.dumps(
        {
            "concepts": ["学术诚信：指学术研究中遵循诚实、公正原则的行为规范"],
            "scope": "高校学术评价体系内的诚信问题",
            "subquestions": ["评价标准：用什么指标衡量学术诚信水平"],
            "stakeholders": ["学生：关注成绩公平性"],
        },
        ensure_ascii=False,
    )


# ---- 200：四字段齐备 ----


def test_explore_200_returns_four_fields(session, client, user_and_headers, monkeypatch):
    """POST explore → 200 ExploreOut 四字段齐备（api.md:43）。

    FakeProvider 返回合法 JSON，验证四字段存在 + Pydantic 校验通过。
    不验证"："格式（prompt 约定，FakeProvider 无法测模型行为——补充 1）。
    """
    from app.core.model_provider import FakeProvider

    import app.api.explore as explore_module

    valid_json = _valid_explore_json()
    monkeypatch.setattr(
        explore_module, "build_provider", lambda: FakeProvider(chunks=[valid_json])
    )

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    resp = client.post(f"/api/sessions/{sess.id}/explore", cookies=cookies)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 四字段齐备
    assert "concepts" in body
    assert "scope" in body
    assert "subquestions" in body
    assert "stakeholders" in body
    # 类型校验（Pydantic 已保证，此处防御性断言）
    assert isinstance(body["concepts"], list)
    assert isinstance(body["scope"], str)
    assert isinstance(body["subquestions"], list)
    assert isinstance(body["stakeholders"], list)


# ---- 422：空 topic ----


def test_explore_422_empty_topic(session, client, user_and_headers):
    """空 topic → 422（api.md:43 字面）。

    session.topic 为纯空白时 422（not topic.strip()）。
    """
    from app.models.session import TrainingSession

    user, cookies = user_and_headers
    sess = TrainingSession(owner_id=user.id, topic="   ", status="waiting")
    session.add(sess)
    session.commit()
    session.refresh(sess)

    resp = client.post(f"/api/sessions/{sess.id}/explore", cookies=cookies)
    assert resp.status_code == 422


# ---- 404：private 会话越权 ----


def test_explore_404_private_session(session, client, user_and_headers):
    """他人 private 会话 → 404（存在性隐藏，permissions §5.1）。"""
    from app.models.user import User

    owner, cookies = user_and_headers
    other = User(username="stu2", password_hash="x", display_name="同学2")
    session.add(other)
    session.commit()
    session.refresh(other)

    sess = _make_session(session, other.id)
    # visibility 默认 private → owner 外 404
    resp = client.post(f"/api/sessions/{sess.id}/explore", cookies=cookies)
    assert resp.status_code == 404


# ---- 401：未登录 ----


def test_explore_401_no_auth(session, client, user_and_headers):
    """未登录 → 401（get_current_user 依赖层）。"""
    user, _ = user_and_headers
    sess = _make_session(session, user.id)

    resp = client.post(f"/api/sessions/{sess.id}/explore")
    assert resp.status_code == 401


# ---- 422：structured 校验失败 ----


def test_explore_422_invalid_structure(session, client, user_and_headers, monkeypatch):
    """坏 JSON → 422（StructuredValidationError 映射）。

    FakeProvider 返回无法解析的文本，generate_structured 重试后抛
    StructuredValidationError → 422（api.md:43 错误码列）。
    """
    from app.core.model_provider import FakeProvider

    import app.api.explore as explore_module

    monkeypatch.setattr(
        explore_module,
        "build_provider",
        lambda: FakeProvider(chunks=["这不是合法 JSON"]),
    )

    user, cookies = user_and_headers
    sess = _make_session(session, user.id)
    resp = client.post(f"/api/sessions/{sess.id}/explore", cookies=cookies)
    assert resp.status_code == 422
