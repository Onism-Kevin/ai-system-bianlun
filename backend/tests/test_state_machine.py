"""S2-2 状态机单测（纯逻辑，无 DB、无 fixture）。

对照 api.md:92 的 409 清单、api.md:31-35 端点行与 sse_events.md §10
一致性表逐条覆盖：固定转移、参数化转移（quick/speech_end_complete）、
全矩阵穷举非法转移、终态仅 restart、错误信息可读性。
"""
from __future__ import annotations

import pytest

from app.core.state_machine import (
    SESSION_STATES,
    TRANSITIONS,
    IllegalTransition,
    can_transition,
    legal_events,
    transition,
)

# 全部事件名（用于全矩阵穷举）
ALL_EVENTS = sorted({e for m in TRANSITIONS.values() for e in m})


@pytest.mark.parametrize(
    "current,event,target,expected",
    [
        # 端点级固定转移（api.md:31-35, 92）
        ("waiting", "submit_message", None, "generating"),
        ("generating", "pause", None, "paused"),
        ("paused", "resume", None, "generating"),
        ("generating", "fatal_error", None, "failed"),
        ("paused", "fatal_error", None, "failed"),
        ("waiting", "restart", None, "waiting"),
        ("paused", "restart", None, "waiting"),
        ("finished", "restart", None, "waiting"),
        ("failed", "restart", None, "waiting"),
        # 参数化转移（quick / speech_end_complete，契约留白目标）
        ("generating", "quick", "waiting", "waiting"),
        ("generating", "quick", "finished", "finished"),
        ("generating", "speech_end_complete", "waiting", "waiting"),
        ("generating", "speech_end_complete", "finished", "finished"),
    ],
)
def test_legal_transitions(current, event, target, expected):
    """每条登记转移都返回契约目标态。"""
    assert transition(current, event, target) == expected
    assert can_transition(current, event, target)


@pytest.mark.parametrize("state", SESSION_STATES)
def test_illegal_matrix(state):
    """全矩阵穷举：除 TRANSITIONS 登记的 (state, event, target) 外一律抛
    IllegalTransition（含未知 target、终态误触发、restart 于 generating 等）。"""
    for event in ALL_EVENTS:
        for target in [None, *SESSION_STATES]:
            if can_transition(state, event, target):
                transition(state, event, target)  # 合法：不抛即过
            else:
                with pytest.raises(IllegalTransition) as exc:
                    transition(state, event, target)
                # 错误信息含当前状态与事件（端点 409 detail 的来源）
                assert state in str(exc.value)
                assert event in str(exc.value)


def test_restart_illegal_while_generating():
    """api.md:33/92：generating 中 restart → 409（先暂停）。"""
    with pytest.raises(IllegalTransition):
        transition("generating", "restart")


def test_parameterized_event_requires_target():
    """quick/speech_end_complete 目标留白：缺省 target 必须报错（不猜默认值），
    非法目标（generating/paused/failed）同样报错。"""
    for event in ("quick", "speech_end_complete"):
        with pytest.raises(IllegalTransition):
            transition("generating", event)
        for bad in ("generating", "paused", "failed"):
            with pytest.raises(IllegalTransition):
                transition("generating", event, bad)


def test_quick_illegal_outside_generating():
    """api.md:92：quick 非 generating → 409；paused 语义留白（脚注 4）不在表内。"""
    for state in ("waiting", "paused", "finished", "failed"):
        assert not can_transition(state, "quick", "waiting")
        with pytest.raises(IllegalTransition):
            transition(state, "quick", "waiting")


def test_terminal_states_only_restart():
    """finished/failed 只接受 restart（done 已落库确认终态，不触发转移——sse §10）。"""
    assert legal_events("finished") == ("restart",)
    assert legal_events("failed") == ("restart",)


def test_unknown_state_and_event():
    """未知状态/未知事件同样抛 IllegalTransition（防御性分支）。"""
    with pytest.raises(IllegalTransition):
        transition("archived", "pause")
    with pytest.raises(IllegalTransition):
        transition("waiting", "unknown_event")


def test_illegal_transition_attributes():
    """异常携带 current/event 属性（端点层可据此生成 409 detail）。"""
    with pytest.raises(IllegalTransition) as exc:
        transition("generating", "resume")
    assert exc.value.current == "generating"
    assert exc.value.event == "resume"
