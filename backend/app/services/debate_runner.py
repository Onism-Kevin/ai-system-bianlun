"""S2-4：辩论编排器（docs/design/s2_4_sse_design.md §1/§4/§6/§7）。

一次 run_generation(session_id) = 一条 AI 发言（Q1 拍板单条）：

1. submit_message 转移（waiting→generating）+ sessions.status 落库；
2. INSERT assistant 消息（status='streaming', agent_role 由 mode 定），
   flush 拿 seq（E-1 方案 A：seq 即主键）→ commit → publish speech_start；
3. 逐 chunk：UPDATE content 拼接 → commit → publish speech_delta；
   （chunk 边界检查控制 flag：S2-6 pause/quick，本任务只暴露检查点）
4. 收尾：UPDATE message(status='complete') + speech_end_complete 转移
   （generating→waiting/finished，轮次参数化）同事务 commit → publish
   speech_end；轮尽 → publish done；
5. 异常：按 sse §5.7 分类 fatal/non-fatal；fatal → 在途消息定稿
   （complete，Q2 拍板）+ sessions.status='failed' 落库 → publish
   error → publish done(failed)。

线程模型：由 POST /messages 的 BackgroundTasks 在线程池执行，晚于
HTTP 响应。DB 用独立 session（不复用请求 session——请求 session 在
响应结束时已 close）。

「先落库后发事件」零容忍（sse §10）：每个 publish 都在对应 commit
之后，且 runner 临界区（commit→publish）整体持 per-session RLock，
与 SSE 端点临界区互斥（§8 竞态消解）。
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import exceptions
from app.core.model_provider import ModelProvider
from app.core.state_machine import transition
from app.models.message import Message
from app.models.session import TrainingSession
from app.prompts.debate import (
    agent_role_for_mode,
    build_generation_messages,
)
from app.services.event_bus import event_bus
from app.services.session_registry import SessionParams, session_registry

logger = logging.getLogger(__name__)

# SSE error code 映射（sse_events.md §5.7 表）：code, retryable, fatal
_ERROR_CODES: dict[type[Exception], tuple[str, bool, bool]] = {
    exceptions.ModelConnectionError: ("model_connection", True, True),
    exceptions.ModelTimeoutError: ("model_timeout", True, True),
    exceptions.StructuredValidationError: ("structured_validation", False, False),
}
# ModelServerError 按 http_status 分流（4xx non-fatal / 5xx fatal）；
# 其余未预期异常 → internal/fatal（§5.7 表末行）


def _classify_error(exc: Exception) -> tuple[str, bool, bool]:
    """异常 → (code, retryable, fatal)。"""
    if isinstance(exc, exceptions.ModelServerError):
        if exc.http_status is not None and exc.http_status < 500:
            return ("model_server", False, False)
        return ("model_server", True, True)
    for exc_type, mapping in _ERROR_CODES.items():
        if isinstance(exc, exc_type):
            return mapping
    return ("internal", False, True)


def _error_message(exc: Exception) -> str:
    """error 事件的 message 字段（用户可读，不带堆栈）。"""
    return (str(exc) or exc.__class__.__name__)[:500]


def _load_history(db: Session, session_id: int) -> list[dict]:
    """按 seq 升序取会话消息（对齐 messages 表出参，prompt 带 seq 渲染）。

    必须在 INSERT 本轮 assistant 消息之前调用——否则空内容的在途消息
    会被渲染进 prompt（渲染成 "N. [反方] " 的空行）。
    """
    rows = db.scalars(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.seq.asc())
    ).all()
    return [
        {
            "seq": row.seq,
            "role": row.role,
            "agent_role": row.agent_role,
            "content": row.content,
        }
        for row in rows
    ]


def _turns_done(db: Session, session_id: int) -> int:
    """已定稿（非 streaming）的 assistant 发言数：本轮 + 历史。"""
    return int(
        db.scalar(
            select(func.count(Message.seq)).where(
                Message.session_id == session_id,
                Message.role == "assistant",
                Message.status != "streaming",
            )
        )
        or 0
    )


def _insert_assistant_message(
    db: Session, session_id: int, *, agent_role: str
) -> int | None:
    """INSERT assistant 消息 + submit_message 转移（同一 commit）。

    返回 seq；失败（会话不存在 / IllegalTransition 竞争）返回 None
    且不 publish——调用方放弃本轮。
    """
    session = db.get(TrainingSession, session_id)
    if session is None:
        logger.error("runner 找不到会话: session_id=%s", session_id)
        return None
    try:
        session.status = transition(session.status, "submit_message")
    except Exception:
        logger.exception(
            "submit_message 非法转移: session_id=%s status=%s",
            session_id,
            session.status,
        )
        db.rollback()
        return None

    message = Message(
        session_id=session_id,
        role="assistant",  # schema_v3:22 ENUM('user','assistant','system')，AI='assistant'
        agent_role=agent_role,
        content="",
        status="streaming",
    )
    db.add(message)
    db.commit()  # seq 分配 + waiting→generating 同事务落库（§6 表）
    db.refresh(message)
    return message.seq


def run_generation(
    session_id: int,
    *,
    db: Session,
    provider: ModelProvider,
    model: str | None = None,
    params: SessionParams | None = None,
) -> None:
    """执行一次 AI 发言（同步；由 BackgroundTasks 线程池调用）。

    db：独立 Session（不复用请求 session）；provider：ModelProvider
    实现（测试传 FakeProvider）；model：默认取 settings.model_default；
    params：测试可直接注入（不读 registry）。
    """
    from app.core.config import get_settings  # 延迟导入：测试环境可无网关配置

    settings = get_settings()
    effective_model = model or settings.model_default
    effective_params = params or session_registry.get(session_id)
    try:
        agent_role = agent_role_for_mode(effective_params.mode)
    except ValueError:
        logger.exception(
            "未知 mode: session_id=%s mode=%r", session_id, effective_params.mode
        )
        return

    # runner 临界区（§8）：history 读 → INSERT/commit → publish 全程持锁，
    # 与 SSE 端点临界区互斥，保证无丢无重。
    with event_bus.session_lock(session_id):
        history = _load_history(db, session_id)  # 先读：不含本轮 assistant 消息
        seq = _insert_assistant_message(db, session_id, agent_role=agent_role)
        if seq is None:
            return
        _run_generation_locked(
            db,
            session_id,
            seq=seq,
            agent_role=agent_role,
            provider=provider,
            model=effective_model,
            mode=effective_params.mode,
            max_turns=effective_params.max_turns,
            prompt_messages=build_generation_messages(effective_params.mode, history),
        )


def _run_generation_locked(
    db: Session,
    session_id: int,
    *,
    seq: int,
    agent_role: str,
    provider: ModelProvider,
    model: str,
    mode: str,
    max_turns: int,
    prompt_messages: list[dict],
) -> None:
    """持会话锁的执行体：落库→publish 逐 chunk，收尾转移 + 错误分类。"""
    event_bus.publish(
        session_id,
        {
            "event": "speech_start",
            "session_id": session_id,
            "seq": seq,
            "agent_role": agent_role,
        },
    )

    message = db.get(Message, seq)
    if message is None:  # 防御：刚 commit 的行不存在=实现 bug
        logger.error("publish_start 后找不到消息: seq=%s", seq)
        return

    parts: list[str] = []
    controller = event_bus.controller(session_id)
    fatal_exc: Exception | None = None
    non_fatal: tuple[str, str] | None = None

    try:
        for chunk in provider.generate_stream(model=model, messages=prompt_messages):
            if not chunk:
                continue
            # chunk 边界自查（补充 2：BackgroundTasks 不可取消，S2-6 pause/quick
            # 端点置位后 runner 在边界停；本任务只预留检查点与 break 路径，
            # 暂停专属收尾（paused_truncated + session→paused）由 S2-6 落）
            if controller.pause_requested or controller.cancel_requested:
                break
            parts.append(chunk)
            message.content = "".join(parts)
            db.commit()  # 每 chunk 落库（§6：snapshot/回放读 DB 即当前全文）
            event_bus.publish(
                session_id,
                {
                    "event": "speech_delta",
                    "session_id": session_id,
                    "seq": seq,
                    "delta": chunk,
                },
            )
            if controller.quick_requested:
                break
    except Exception as exc:  # noqa: BLE001 —— 按 §5.7 四类+internal 分类统一处理
        code, retryable, fatal = _classify_error(exc)
        if fatal:
            fatal_exc = exc
        else:
            non_fatal = (code, _error_message(exc))
        logger.warning(
            "生成异常: session_id=%s seq=%s code=%s fatal=%s err=%r",
            session_id,
            seq,
            code,
            fatal,
            exc,
        )

    if fatal_exc is not None:
        _finalize_fatal(db, session_id, seq=seq, message=message, exc=fatal_exc)
        return

    if non_fatal is not None:
        # non-fatal（4xx/结构校验）：error(fatal=false)，流不关；在途消息留
        # streaming（§5.7 字面：最终命运由后续 speech_end 或新 error(fatal=true) 定；
        # 手动重试入口属 S2-F6）
        event_bus.publish(
            session_id,
            {
                "event": "error",
                "session_id": session_id,
                "code": non_fatal[0],
                "message": non_fatal[1],
                "retryable": False,
                "fatal": False,
            },
        )
        return

    _finalize_complete(
        db,
        session_id,
        seq=seq,
        message=message,
        mode=mode,
        max_turns=max_turns,
    )


def _finalize_complete(
    db: Session,
    session_id: int,
    *,
    seq: int,
    message: Message,
    mode: str,
    max_turns: int,
) -> None:
    """正常收尾：在途消息定稿 + speech_end_complete 转移 + speech_end/done。"""
    session = db.get(TrainingSession, session_id)
    if session is None:
        logger.error("finalize 找不到会话: session_id=%s", session_id)
        return

    # 轮次判定（§2）：max_turns 用完 → finished；还有剩余轮次 → waiting
    # （等学生下一条输入，api.md:35 只有 waiting 接受新 messages）。
    # 本轮消息刚置 complete（下一行 commit 前），直接计入：turns_done + 1。
    turns_done = _turns_done(db, session_id) + 1
    target = "finished" if turns_done >= max_turns else "waiting"

    message.status = "complete"
    try:
        session.status = transition(session.status, "speech_end_complete", target)
    except Exception:
        logger.exception(
            "speech_end_complete 非法转移: session_id=%s status=%s target=%s",
            session_id,
            session.status,
            target,
        )
        db.rollback()
        return
    db.commit()  # 终态 + session 转移同事务（§6 speech_end 行）

    event_bus.publish(
        session_id,
        {
            "event": "speech_end",
            "session_id": session_id,
            "seq": seq,
            "status": "complete",
        },
    )
    if target == "finished":
        event_bus.publish(
            session_id,
            {"event": "done", "session_id": session_id, "reason": "finished"},
        )
        event_bus.publish_done(session_id)  # 订阅者关流（§7 步骤 7）


def _finalize_fatal(
    db: Session,
    session_id: int,
    *,
    seq: int,
    message: Message,
    exc: Exception,
) -> None:
    """fatal 收尾（§7 表 fatal 行）：在途消息定稿 complete（Q2 拍板）
    + session=failed 落库 → publish error → publish done(failed) → 关流。"""
    code, retryable, _fatal = _classify_error(exc)
    session = db.get(TrainingSession, session_id)
    if session is None:
        logger.error("fatal finalize 找不到会话: session_id=%s", session_id)
        return

    message.status = "complete"  # Q2 拍板：fatal 不可 resume，不用 paused_truncated
    try:
        session.status = transition(session.status, "fatal_error")
    except Exception:
        logger.exception(
            "fatal_error 非法转移: session_id=%s status=%s",
            session_id,
            session.status,
        )
        db.rollback()
        return
    db.commit()

    event_bus.publish(
        session_id,
        {
            "event": "error",
            "session_id": session_id,
            "code": code,
            "message": _error_message(exc),
            "retryable": retryable,
            "fatal": True,
        },
    )
    event_bus.publish(
        session_id, {"event": "done", "session_id": session_id, "reason": "failed"}
    )
    event_bus.publish_done(session_id)


def build_provider() -> ModelProvider:
    """默认 provider 工厂（§5 DI）：dev/demo→OpenAICompatProvider；test→FakeProvider。

    测试一律显式传 FakeProvider（不走环境变量魔法）；本工厂供 POST
    /messages 的 BackgroundTasks 在无注入时使用。
    """
    from app.core.config import get_settings

    settings = get_settings()
    if settings.app_env == "test":
        from app.core.model_provider import FakeProvider

        return FakeProvider()
    from app.core.model_provider import OpenAICompatProvider

    return OpenAICompatProvider(
        base_url=settings.model_base_url,
        api_key=settings.model_api_key.get_secret_value(),
    )
