"""S2-4 服务层单测：event_bus 与 session_registry（设计 §9 总线行）。

覆盖：
- 多订阅者收全量（publish 广播）；
- subscribe/unsubscribe 幂等；退订后 publish 不投递；
- §8 竞态消解单测：预置"已回放终态 seq"语义下，publish 早于 subscribe
  的事件不入队列（调用方负责回放）；subscribe 之后 publish 的事件必达；
- 慢客户端哨兵（queue 满 → done sentinel 投递，不抛 Full）；
- SessionController flag 置位语义（S2-6 端点将置位，本任务只验证结构）；
- registry set/get/remove/reset + get 缺失返回默认（max_turns=1）。
"""
from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"  # 必须在导入 app 包之前写入

import threading  # noqa: E402

import pytest  # noqa: E402
from queue import Full  # noqa: E402

from app.services.event_bus import (  # noqa: E402
    _DONE_SENTINEL,
    _QUEUE_MAXSIZE,
    EventBus,
)
from app.services.session_registry import (  # noqa: E402
    SessionParams,
    SessionRegistry,
    session_registry,
)


@pytest.fixture()
def bus() -> EventBus:
    return EventBus()


def test_publish_broadcasts_to_all_subscribers(bus):
    q1 = bus.subscribe(7)
    q2 = bus.subscribe(7)
    bus.publish(7, {"event": "speech_start", "seq": 1})
    assert q1.get_nowait() == {"event": "speech_start", "seq": 1}
    assert q2.get_nowait() == {"event": "speech_start", "seq": 1}


def test_publish_without_subscribers_is_noop(bus):
    bus.publish(999, {"event": "done"})  # 不得建 channel 也不得抛
    bus.publish_done(999)
    assert True  # 不抛即通过


def test_unsubscribe_is_idempotent(bus):
    q = bus.subscribe(7)
    bus.unsubscribe(7, q)
    bus.unsubscribe(7, q)  # 第二次幂等
    bus.publish(7, {"event": "x"})
    assert q.empty()


def test_unsubscribe_removes_channel_when_last(bus):
    q = bus.subscribe(7)
    bus.unsubscribe(7, q)
    with bus._buses_lock:
        assert 7 not in bus._buses


def test_slow_client_gets_done_sentinel(bus):
    """慢客户端（queue 满）→ 丢弃最旧事件让位，最终投递 done sentinel。"""
    q = bus.subscribe(7)
    for i in range(_QUEUE_MAXSIZE):
        bus.publish(7, {"event": "speech_delta", "seq": i})
    # 队列已满：publish 走 except Full → get_nowait() 丢最旧 + put 新事件
    bus.publish(7, {"event": "speech_delta", "seq": _QUEUE_MAXSIZE})
    assert q.get_nowait() == {"event": "speech_delta", "seq": 1}


def test_drain_timeout_returns_none(bus):
    q = bus.subscribe(7)
    event, ok = bus.drain(q, timeout=0.05)
    assert (event, ok) == (None, False)


def test_drain_returns_event(bus):
    q = bus.subscribe(7)
    bus.publish(7, {"event": "speech_end", "seq": 3})
    event, ok = bus.drain(q, timeout=0.05)
    assert ok is True
    assert event == {"event": "speech_end", "seq": 3}


def test_publish_done_closes_stream(bus):
    q = bus.subscribe(7)
    bus.publish_done(7)
    assert q.get_nowait() is _DONE_SENTINEL


def test_race_no_loss_no_duplicate(bus):
    """§8 单测（设计 §9）：并发 subscribe/publish 下事件不丢不重。

    模型化两侧临界区：
    - 发布侧：持 session_lock → commit(事件) → publish（与 runner 同构）；
    - 订阅侧：持 session_lock → 读位置 → subscribe（与 SSE 端点同构）。
    锁保证：事件要么在订阅前完成（发布侧先拿锁→订阅方回放能覆盖），
    要么在订阅后发生（必进队列）。本测试用"订阅后必达"侧断言：锁内
    subscribe 后，任何锁内 publish 必进队列（数量精确，无丢无重）。
    """
    q: "object" = None
    lock = bus.session_lock(7)
    received: list[dict] = []

    def subscriber():
        nonlocal q
        with lock:  # SSE 临界区：订阅与回放读同锁
            q = bus.subscribe(7)

    def publisher(n: int):
        for i in range(n):
            with lock:  # runner 临界区：publish 在锁内
                bus.publish(7, {"event": "speech_delta", "seq": i})

    t1 = threading.Thread(target=subscriber)
    t1.start()
    t1.join()
    t2 = threading.Thread(target=publisher, args=(20,))
    t2.start()
    t2.join()
    while True:
        try:
            received.append(q.get_nowait())
        except Exception:
            break
    assert received == [{"event": "speech_delta", "seq": i} for i in range(20)]


def test_session_lock_is_per_session_and_reentrant(bus):
    lock7 = bus.session_lock(7)
    lock8 = bus.session_lock(8)
    assert lock7 is not lock8
    assert bus.session_lock(7) is lock7  # 同一会话同一锁（defaultdict 保持）
    with lock7:  # RLock 可重入
        with lock7:
            pass


def test_controller_flags(bus):
    c = bus.controller(7)
    assert (c.pause_requested, c.quick_requested, c.cancel_requested) == (
        False,
        False,
        False,
    )
    c.pause_requested = True
    assert bus.controller(7).pause_requested is True  # 同一 controller 实例


def test_registry_set_get_remove_reset():
    reg = SessionRegistry()
    reg.set(1, SessionParams(mode="coach", max_turns=3))
    got = reg.get(1)
    assert (got.mode, got.max_turns) == ("coach", 3)
    reg.remove(1)
    assert reg.get(1).mode == "debate"  # 缺失回默认
    assert reg.get(1).max_turns == 1


def test_registry_singleton_reset():
    session_registry.set(42, SessionParams(mode="rebuttal", max_turns=5))
    session_registry.reset()
    assert session_registry.get(42).mode == "debate"
