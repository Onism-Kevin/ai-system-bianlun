"""S2-4：会话运行参数内存 registry（docs/design/s2_4_sse_design.md §5）。

mode/max_turns 为运行参数，不落 sessions 表（api.md:28 脚注 1）；按
Q3 拍板以进程内 registry 持有（key=session_id），POST /api/sessions
创建时填充，runner 从 registry 读。

边界（已知限制，记 S5+）：进程重启即丢；重连后按 DB 状态续（restart
由 S2-F6 定）。registry 条目在会话创建后长期保留（会话量小，MVP 不
做 GC）。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class SessionParams:
    """会话运行参数（api.md:28 body 带入，脚注 1 不落表）。"""

    mode: str = "debate"
    max_turns: int = 1


class SessionRegistry:
    """session_id → SessionParams 的线程安全内存表。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._params: dict[int, SessionParams] = {}

    def set(self, session_id: int, params: SessionParams) -> None:
        with self._lock:
            self._params[session_id] = params

    def get(self, session_id: int) -> SessionParams:
        """读取；缺失（如进程重启后）返回默认参数（api.md:28 默认值）。"""
        with self._lock:
            return self._params.get(session_id, SessionParams())

    def remove(self, session_id: int) -> None:
        with self._lock:
            self._params.pop(session_id, None)

    def reset(self) -> None:
        """测试专用。"""
        with self._lock:
            self._params.clear()


session_registry = SessionRegistry()
