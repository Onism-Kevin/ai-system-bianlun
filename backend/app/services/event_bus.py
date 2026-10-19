"""S2-4：进程内事件总线（docs/design/s2_4_sse_design.md §8）。

职责：把 runner 线程的事件（speech_*/error/done）分发给同一会话的 SSE
订阅者，并提供 per-session RLock 支撑 §8 竞态消解 + SessionController
支撑 §4 控制通道（S2-6 pause/quick/restart 端点置位）。

线程模型：runner 在 BackgroundTasks 线程池线程执行，SSE 端点在
StreamingResponse 的线程池线程执行——所有共享结构必须线程安全。
事件 payload 为 dict（可 JSON 序列化），帧序列化由 api/events.py 负责。

设计约束：
- 单 worker（dev 单进程）：多 worker 水平扩展需 Redis pub/sub（S5+ 待办）。
- 每订阅者无界 queue（MVP）：慢客户端背压记 S5+。
- 事件不落队列以外的存储：DB 落库在 runner 侧完成（sse §10 先落库后发
  事件），总线只做"发布给此刻在线的订阅者"。
"""
from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from queue import Empty, Full, Queue

# 订阅队列容量上限：队列满 = 慢客户端（订阅者消费跟不上发布）。
# 慢客户端处置（用户 m02174 追问 2 裁定 B，MVP 假设）：丢最旧事件再投——
# MVP 同会话连接数 ≤4（sse §2 同源建议值），队列积压 1000 属异常场景；
# S5+ 若提高并发/放开长消息，需改为发 error(code=slow_client, fatal=true)
# 关流让客户端走回放补齐（选项 A），否则丢 speech_start 会导致客户端
# delta 错位（无 snapshot 基准无法幂等吸收，sse §7.4）。
_QUEUE_MAXSIZE = 1000

# done sentinel：非 dict 的独特对象，与事件 dict 区分（订阅者据此关流）。
_DONE_SENTINEL = object()


@dataclass
class SessionController:
    """§4 控制通道：S2-6 端点置位，runner 在 chunk 边界自查。

    pause/quick/cancel 三个 flag + 一个 threading.Event（S2-4 设计 §4 原
    规划结构，S2-4 只落了 flag 与检查点，S2-6 补齐 Event 与封装方法）。

    flag 生命周期（S2-6 设计 §3.3）：
    - pause_requested：pause 端点置位 → runner 停手并挂起 → resume 端点清除；
    - quick_requested：quick 端点置位 → runner 停手退出；残留由下一轮
      run_generation 入口统一清除；
    - cancel_requested：restart 端点置位（仅可能唤醒挂起 runner 时）→
      runner 醒后消费并自清除；无挂起 runner 时的残留同样由下一轮入口清；
    - resume_event：pause 挂起 / resume 唤醒的载体（Event.set 唤醒）。

    线程模型：端点在 HTTP 线程置位/发信号，runner 在 BackgroundTasks
    线程消费——bool/Event 的置位-检查无需额外锁（GIL 原子性）。
    """

    pause_requested: bool = False
    quick_requested: bool = False
    cancel_requested: bool = False
    resume_event: threading.Event = field(default_factory=threading.Event)

    def signal_resume(self) -> None:
        """resume/restart 端点调用：唤醒挂起的 runner（幂等，无等待者也无害）。"""
        self.resume_event.set()

    def clear_resume(self) -> None:
        """runner 挂起前调用：清掉上一轮的旧唤醒信号（防 resume 端点先到）。"""
        self.resume_event.clear()

    def wait_resume(self, timeout: float) -> bool:
        """runner 挂起等待 resume；超时/被唤醒返回 True（runner 唤醒后自行复查 flag）。"""
        return self.resume_event.wait(timeout)

    def clear_control_flags(self) -> None:
        """新一轮 run_generation 入口调用：旧控制信号全部作废（S2-6 裁定 5）。"""
        self.pause_requested = False
        self.quick_requested = False
        self.cancel_requested = False
        self.resume_event.clear()


@dataclass
class _SessionChannel:
    """单会话的订阅者集合 + 单调位置计数器 + 会话锁。"""

    lock: threading.RLock = field(default_factory=threading.RLock)
    subscribers: set[Queue] = field(default_factory=set)
    position: int = 0
    controller: SessionController = field(default_factory=SessionController)


class EventBus:
    """进程内 pub/sub：publish 广播给该会话的全部订阅者。

    锁层次（§8 锁序无死锁）：会话锁 → 总线内部锁。本类 publish/subscribe
    持总线内部锁（self._buses_lock，仅保护 _buses dict 本身）；会话锁由
    runner 与 SSE 端点按 §8 临界区约定使用，总线不感知。
    """

    def __init__(self) -> None:
        self._buses_lock = threading.Lock()
        self._buses: dict[int, _SessionChannel] = defaultdict(_SessionChannel)

    # ---- 订阅侧（SSE 端点） ----

    def subscribe(self, session_id: int) -> Queue:
        """订阅会话；返回 per-subscriber 队列（调用方负责 get/关流）。

        必须在 per-session RLock 临界区内调用（§8 补充 1：订阅与回放
        读 DB、在途检查同锁），否则存在"事件已提交但既不在回放里也没
        进订阅队列"的丢失窗口。
        """
        queue: Queue = Queue(maxsize=_QUEUE_MAXSIZE)
        with self._buses_lock:
            channel = self._buses[session_id]
        with channel.lock:
            channel.subscribers.add(queue)
        return queue

    def unsubscribe(self, session_id: int, queue: Queue) -> None:
        """退订并清理；幂等。"""
        with self._buses_lock:
            channel = self._buses.get(session_id)
        if channel is None:
            return
        with channel.lock:
            channel.subscribers.discard(queue)
            self._gc_channel(session_id, channel)

    def _gc_channel(self, session_id: int, channel: _SessionChannel) -> None:
        """channel 生命周期（用户 m02174 追问 1 裁定）：

        - done（publish_done）后**不立即摘除**：迟到重连（done 帧丢失/
          传输层断线后 EventSource 重开）仍需经 §8 临界区重新 subscribe，
          _buses 里留着 channel 才能进 session_lock 临界区、由回放发现
          会话终态 → done → 关流。立即摘除会让迟到重连在 subscribe 时
          重建 channel 走同一路径，语义不破，但会丢掉 SessionController
          上未消费的 flag（S2-6 pause/quick 边缘场景），故摘除条件只认
          "零订阅者"。
        - 零订阅者（unsubscribe 最后一个 / publish_done 时全员退出）才
          从 _buses 摘除——内存占用 per session 仅一个空 dataclass，S2
          单机 session 量级下无泄漏面；S5+ 多 worker/Redis 化时此结构
          整体替换，无需额外超时/引用计数机制。
        - 调用方须持 channel.lock（与 subscribers 变更同锁防竞态）。
        """
        if not channel.subscribers:
            with self._buses_lock:
                if self._buses.get(session_id) is channel:
                    self._buses.pop(session_id, None)

    def drain(self, queue: Queue, *, timeout: float) -> tuple[object, bool]:
        """从订阅队列取一个事件（或 done sentinel）；timeout 秒无事件返回 (None, False)。

        返回 (event, True) 或 (_DONE_SENTINEL, True) 或 (None, False)。
        """
        try:
            return queue.get(timeout=timeout), True
        except Empty:
            return None, False

    # ---- 发布侧（runner） ----

    def publish(self, session_id: int, event: dict) -> None:
        """广播事件给该会话全部订阅者（含在途的 SSE 连接）。

        必须在 per-session RLock 临界区内、且 DB commit 之后调用
        （sse §10：先落库后发事件；§8：commit→publish 原子化防竞态）。

        慢客户端（队列满，见 _QUEUE_MAXSIZE 注释）：丢最旧再投；丢完仍满
        才发 done sentinel 关流（客户端经回放补齐）。
        """
        with self._buses_lock:
            channel = self._buses.get(session_id)
        if channel is None:
            return
        with channel.lock:
            channel.position += 1
            for queue in channel.subscribers:
                try:
                    queue.put_nowait(event)
                except Full:
                    # 慢客户端：丢最旧事件再投，给事件让位（丢一帧胜过错位）；
                    # 丢完仍满则说明已无可救空间，发 done sentinel 关流。
                    try:
                        queue.get_nowait()
                        queue.put_nowait(event)
                    except (Empty, Full):
                        try:
                            queue.put_nowait(_DONE_SENTINEL)
                        except Full:
                            pass

    def publish_done(self, session_id: int) -> None:
        """广播 done sentinel：订阅者据此发 done 帧并关流（§7 步骤 7）。

        与 publish 同样在 commit 之后、会话锁内调用。sentinel 不入
        position（不是事件，仅供关流信号）。发完 sentinel 的通道若已无
        订阅者即从 _buses 摘除（channel 生命周期见 _gc_channel 注释）。
        """
        with self._buses_lock:
            channel = self._buses.get(session_id)
        if channel is None:
            return
        with channel.lock:
            for queue in channel.subscribers:
                try:
                    queue.put_nowait(_DONE_SENTINEL)
                except Full:
                    pass
            self._gc_channel(session_id, channel)

    # ---- 会话锁与控制通道（runner / SSE 端点共用） ----

    def session_lock(self, session_id: int) -> threading.RLock:
        """per-session RLock（§8 竞态消解载体；锁序：会话锁→总线锁）。"""
        with self._buses_lock:
            channel = self._buses[session_id]
        return channel.lock

    def controller(self, session_id: int) -> SessionController:
        """§4 控制通道：S2-6 端点置位、runner chunk 边界检查。"""
        with self._buses_lock:
            channel = self._buses[session_id]
        return channel.controller

    def reset(self) -> None:
        """测试专用：清空全部会话通道。"""
        with self._buses_lock:
            self._buses.clear()


# 进程级单例（uvicorn 单 worker 下全局唯一；测试在 conftest 中 reset）
event_bus = EventBus()
