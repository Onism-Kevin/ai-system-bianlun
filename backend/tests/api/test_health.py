"""S2-13 API 层测试：health 端点（api.md:74）。

策略：monkeypatch _probe_mysql/_probe_gateway 模拟各种故障场景。
5 用例：ok / mysql down / gateway down / gateway degraded / 匿名。
"""
from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"

from tests.api.test_events import _clean_bus, client  # noqa: F401
from tests.models.conftest import engine, session  # noqa: F401


# ---- 200：全部 ok ----


def test_health_200_ok(session, client, monkeypatch):
    """GET /api/health → 200 {mysql:"ok", model_gateway:"ok"}。"""
    import app.api.health as health_module

    monkeypatch.setattr(health_module, "_probe_mysql", lambda: "ok")
    monkeypatch.setattr(health_module, "_probe_gateway", lambda: "ok")

    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mysql"] == "ok"
    assert body["model_gateway"] == "ok"


# ---- 200：MySQL down ----


def test_health_mysql_down(session, client, monkeypatch):
    """MySQL down → 200 {mysql:"down", ...}（降级也 200）。"""
    import app.api.health as health_module

    monkeypatch.setattr(health_module, "_probe_mysql", lambda: "down")
    monkeypatch.setattr(health_module, "_probe_gateway", lambda: "ok")

    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mysql"] == "down"
    assert body["model_gateway"] == "ok"


# ---- 200：gateway down ----


def test_health_gateway_down(session, client, monkeypatch):
    """网关连接拒绝 → 200 {..., model_gateway:"down"}。"""
    import app.api.health as health_module

    monkeypatch.setattr(health_module, "_probe_mysql", lambda: "ok")
    monkeypatch.setattr(health_module, "_probe_gateway", lambda: "down")

    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mysql"] == "ok"
    assert body["model_gateway"] == "down"


# ---- 200：gateway degraded ----


def test_health_gateway_degraded(session, client, monkeypatch):
    """网关超时 → 200 {..., model_gateway:"degraded"}。"""
    import app.api.health as health_module

    monkeypatch.setattr(health_module, "_probe_mysql", lambda: "ok")
    monkeypatch.setattr(health_module, "_probe_gateway", lambda: "degraded")

    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mysql"] == "ok"
    assert body["model_gateway"] == "degraded"


# ---- 200：匿名访问 ----


def test_health_no_auth(session, client):
    """匿名访问 → 200（health 无鉴权）。"""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "mysql" in body
    assert "model_gateway" in body
