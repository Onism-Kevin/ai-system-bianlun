"""S2-4：SSE 端点 GET /api/sessions/{id}/events（api.md:42 + sse_events.md 全文）。

契约逐条对照：
- 帧格式（sse §2）：`event:`/`data:` 两行 + 空行；data 单行 JSON
  （禁止内嵌换行——json.dumps 默认无换行，显式断言防御）；只有 speech_*
  写 `id:` 行=seq（§3）；非 speech（error/done）省略。
- 响应头（sse §2）：Cache-Control no-cache / Connection keep-alive /
  X-Accel-Buffering no；Content-Type text/event-stream（StreamingResponse
  media_type 设置）。
- 建流即发 `retry: 5000`（sse §2）；每 15s 无事件发注释行 `: hb`（§2）。
- 鉴权（sse §9 方案 A：Cookie 与 REST 同一凭据）：建流前三鉴权 401
  （get_current_user）/ 404（can_read_session 不过——E-19：读路径无
  403，api.md:42 的 403 无触发路径）；HTTP 层错误不进事件流（§5.7 末段）。
- 回放（sse §7.1/§7.2）：裸连≡after_seq=0；Last-Event-ID 头优先于
  query（EventSource 原生重连自动带，§7.1）；终态消息重编码
  start→delta(全量)→end；在途发 snapshot；会话终态回放完 done 关流。
- 竞态（§8 + 用户补充 1）：回放读 DB + 在途检查 + 订阅 queue 三步全在
  per-session RLock 内；位置 > P 的事件才实时发；speech_ 事件再按
  seq <= maxReplayedTerminalSeq 去重（二层保险）。
- 流内异常（回放 DB 读失败等）→ error(code=internal) → done(failed)
  → 关流（sse §5.7 末段）。

线程模型（设计 §1 D1）：同步 def + StreamingResponse(同步生成器)，
Starlette 线程池迭代；queue.Queue 桥 runner 线程；每连接占一线程
（契约 §2 同会话 ≤4 建议值，MVP 无瓶颈）。单 worker 约束（多 worker
需 Redis pub/sub，S5+ 待办）。
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import can_read_session, get_current_user
from app.core.database import get_db
from app.models.message import Message
from app.models.session import TrainingSession
from app.models.user import User
from app.services.event_bus import _DONE_SENTINEL, event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# sse §2：心跳 15s 与 queue.get 超时一致（超时即心跳）
_HEARTBEAT_INTERVAL = 15.0
# sse §2：建流后立即发的重试提示（浏览器原生重连基准）
_RETRY_LINE = "retry: 5000"
# sse §4 事件总表：走 id: 行的事件（只有 speech_*）
_SPEECH_EVENTS = frozenset(
    {"speech_start", "speech_delta", "speech_end", "speech_snapshot"}
)
# sse §4：终态消息 status（complete/paused_truncated）；streaming=在途
_TERMINAL_STATUSES = frozenset({"complete", "paused_truncated"})
# sessions.status 终态 → 回放完 done 关流（§7.1 步骤 5）
_SESSION_TERMINAL = frozenset({"finished", "failed"})

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="会话不存在或无权访问",
)


def _frame(event: str, data: dict, *, seq: int | None = None) -> str:
    """SSE 帧序列化（sse §2/§3）：event/data 两行 + 空行；speech_* 带 id: 行。

    data 单行 JSON 硬约束（§2：禁止内嵌换行）——json.dumps 默认单行，
    显式断言防御未来误改 separators/ensure_ascii 之外的格式。
    """
    payload = json.dumps(data, ensure_ascii=False)
    if "\n" in payload or "\r" in payload:  # pragma: no cover - 防御性
        raise ValueError("SSE data 必须单行 JSON（sse §2）")
    lines = [f"event: {event}"]
    if event in _SPEECH_EVENTS and seq is not None:
        lines.append(f"id: {seq}")
    lines.append(f"data: {payload}")
    return "\n".join(lines) + "\n\n"


def _replay_frames(
    db: Session, session_id: int, *, after_seq: int
) -> tuple[list[str], int | None, int | None]:
    """回放（sse §7.1 步骤 2-5）：返回 (帧列表, 在途 seq, 最大回放终态 seq)。

    - 终态消息重编码：start → delta(全量 content 一条) → end(status)；
    - 在途（status='streaming'）消息：不重编码，返回其 seq 由调用方发
      snapshot（§7.3 即时语义）；
    - max_replayed_terminal_seq：已回放的最大终态 seq（调用方做 §8
      二层保险去重）；
    - user/system 行跳过（§4 事件总表 + api.md:35 行为注：用户消息
      前端本地渲染、不由 SSE 回显；回放只承载 AI 发言）。
    """
    rows = db.scalars(
        select(Message)
        .where(Message.session_id == session_id, Message.seq > after_seq)
        .order_by(Message.seq.asc())
    ).all()
    frames: list[str] = []
    inflight_seq: int | None = None
    max_terminal_seq: int | None = None
    for row in rows:
        # sse §4 事件总表 + §3：只有 assistant（AI）消息走 speech_* 回放；
        # user/system 行供 REST 历史与审计（api.md:35 行为注：用户消息
        # 前端本地渲染、不由 SSE 回显），回放不产生任何事件。
        if row.role != "assistant":
            continue
        if row.status == "streaming":
            # 同会话同一时刻至多一条在途（§5.7 末段）；多条时取最后一条
            inflight_seq = row.seq
            continue
        max_terminal_seq = row.seq if max_terminal_seq is None else max(
            max_terminal_seq, row.seq
        )
        frames.append(
            _frame(
                "speech_start",
                {"session_id": session_id, "seq": row.seq, "agent_role": row.agent_role},
                seq=row.seq,
            )
        )
        frames.append(
            _frame(
                "speech_delta",
                {"session_id": session_id, "seq": row.seq, "delta": row.content},
                seq=row.seq,
            )
        )
        frames.append(
            _frame(
                "speech_end",
                {"session_id": session_id, "seq": row.seq, "status": row.status},
                seq=row.seq,
            )
        )
    return frames, inflight_seq, max_terminal_seq


def _snapshot_frame(db: Session, session_id: int, seq: int) -> str | None:
    """在途消息 snapshot（§5.4/§7.3）：累积全文 + status。

    仅 assistant 行可被传入（回放只收集 AI 在途消息，§4 事件总表）。
    """
    row = db.get(Message, seq)
    if row is None:
        return None
    return _frame(
        "speech_snapshot",
        {
            "session_id": session_id,
            "seq": row.seq,
            "agent_role": row.agent_role,
            "content": row.content,
            "status": row.status,
        },
        seq=row.seq,
    )


def _resolve_after_seq(request: Request) -> int:
    """回放起点（sse §7.2）：Last-Event-ID 头优先（EventSource 原生重连），
    否则 query after_seq；裸连 ≡ 0（回放全部）。"""
    last_event_id = request.headers.get("last-event-id")
    if last_event_id is not None:
        try:
            return int(last_event_id)
        except ValueError:
            return 0
    try:
        return int(request.query_params.get("after_seq", "0"))
    except ValueError:
        return 0


def _event_stream(
    db: Session, session_id: int, request: Request, after_seq: int
) -> Iterator[str]:
    """SSE 生成器（设计 §1 流程 1-7 逐条落地）。"""
    yield _RETRY_LINE  # sse §2：建流后立即发

    try:
        # §8 临界区（用户补充 1）：回放读 DB + 在途检查 + 订阅 queue
        # 三步全在同一 RLock 内——与 runner 的 commit→publish 临界区
        # 互斥，保证无丢无重。
        #
        # 锁内 DB 读（几十毫秒）会阻塞 runner 的 commit→publish：可接受
        # （用户 m02174 追问 3 确认）——回放只在建流时执行一次，建流后
        # runner 持续运行不再与该锁交互（锁内无 DB 读、无 publish 等待）。
        with event_bus.session_lock(session_id):
            frames, inflight_seq, max_terminal_seq = _replay_frames(
                db, session_id, after_seq=after_seq
            )
            session = db.get(TrainingSession, session_id)
            session_terminal = (
                session is not None and session.status in _SESSION_TERMINAL
            )
            queue = event_bus.subscribe(session_id)
    except Exception:
        logger.exception("events 回放失败: session_id=%s", session_id)
        # 流内异常 → error(internal) → done(failed) → 关流（§5.7 末段）
        yield _frame(
            "error",
            {
                "session_id": session_id,
                "code": "internal",
                "message": "事件流初始化失败",
                "retryable": False,
                "fatal": True,
            },
        )
        yield _frame("done", {"session_id": session_id, "reason": "failed"})
        return

    try:
        for frame in frames:
            yield frame
        if inflight_seq is not None:
            frame = _snapshot_frame(db, session_id, inflight_seq)
            if frame is not None:
                yield frame
        if session_terminal:
            # 会话终态：回放完 done 即关流（§7.1 步骤 5；reason 与
            # sessions.status 对应，§5.10）
            reason = session.status if session is not None else "finished"
            yield _frame("done", {"session_id": session_id, "reason": reason})
            return

        # 实时循环（设计 §1 步骤 7）：queue.get(timeout=15) → 发帧；
        # 超时 → 心跳注释行；done sentinel → done 帧 → 关流。
        while True:
            event, ok = event_bus.drain(queue, timeout=_HEARTBEAT_INTERVAL)
            if not ok:
                yield ": hb\n\n"  # sse §2：注释行心跳
                continue
            if event is _DONE_SENTINEL:
                yield _frame("done", {"session_id": session_id, "reason": "finished"})
                return
            # §8 二层保险：已回放终态 seq 的 speech_* 事件跳过（锁保证
            # 无丢无重后这是双保险；非 speech 事件 error/done 天然一次）。
            # snapshot 例外：在途消息无终态 seq（max_terminal_seq 只按终态
            # 行更新），回放阶段已发的 snapshot 由 §8 锁保证不重发。
            seq = event.get("seq")
            if (
                seq is not None
                and max_terminal_seq is not None
                and seq <= max_terminal_seq
                and event["event"] in _SPEECH_EVENTS
                and event["event"] != "speech_snapshot"
            ):
                continue
            frame = _frame(
                event["event"],
                {k: v for k, v in event.items() if k != "event"},
                seq=seq,
            )
            yield frame
    finally:
        event_bus.unsubscribe(session_id, queue)


@router.get("/{session_id}/events")
def session_events(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """SSE 事件流（api.md:42 + sse_events.md 全文；实现细节见模块 docstring）。

    建流前三鉴权（sse §5.7 末段：HTTP 层错误不进事件流）：
    401（get_current_user）/ 404（can_read_session 不过，E-19 读路径
    无 403）。
    """
    session = db.get(TrainingSession, session_id)
    if session is None or not can_read_session(db, user, session):
        raise _NOT_FOUND
    after_seq = _resolve_after_seq(request)
    return StreamingResponse(
        _event_stream(db, session_id, request, after_seq),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
