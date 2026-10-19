"""S2-3：sessions 端点（POST 创建 / GET 详情 / PATCH 修改，api.md:28-30）。

契约逐条对照：
- POST（api.md:28）：201 {id, status}（脚注 3：一律 201）；初始状态取
  state_machine.INITIAL_STATE（waiting）——创建不自动触发 generating，
  等首条消息（api.md:35 messages 提交才 waiting→generating）；mode/
  max_turns 为运行参数不落表（脚注 1）；创建时调 validate_session_visibility
  （E-2），task_id 指向的任务必须存在且未归档（E-2 存在性检查只能应用层做）。
- GET（api.md:29）：200 会话全字段；不存在或越权一律 404（存在性隐藏，
  api.md §3:89）——private 对非 owner（含教师）也 404。
- PATCH（api.md:30 + errata E-17）：{topic?, visibility?, task_id?}；
  200 平铺（与 GET 同构）。错误码分层（用户 2026-10-14 裁定，对齐
  api.md:30 字面 + §3:90）：
  · can_read_session 不过 → 404（存在性隐藏；学生非 owner 全落此档）；
  · 可读但非 owner（仅课程教师对学生 task 会话：可读无 update 授权，
    permissions:64）→ 403「非 owner」；
  · 合并后 (visibility, task_id) 违反 E-2 → 422；task 不存在/已归档
    → 422（契约只列 401/422）；task 跨用户引用 → 404（存在性隐藏）。
- status 不在 PATCH 入参（状态机独占，api.md:30）；pause/resume/restart/
  quick（api.md:31-34）为 S2-6 端点，经 state_machine.transition 校验。

权限判定复用 S2-2 的 can_read_session（E-15/§5.6 owner 优先级）；
initial 状态复用 state_machine.INITIAL_STATE（用户 S2-3 硬约束⑤）。

S2-4 扩展（同文件，路由前缀共用）：
- POST /{session_id}/messages（api.md:35）：同步写 messages role='user'
  → BackgroundTasks 触发 debate_runner（异步 waiting→generating）；
  409 非 waiting（状态机错位，api.md:92 清单）。
- GET /{session_id}/messages（api.md:38）：历史分页（after_seq+limit）。
- GET /{session_id}/events（api.md:42）：SSE 流（见 api/events.py 挂载，
  E-19：读路径 403 无触发路径，统一 404）。

S2-6 扩展（同文件）：POST /{session_id}/{pause,resume,restart,quick}
（api.md:31-34）四控制端点：
- 统一动作序列（S2-6 设计 §2）：鉴权分层（404→403）→ 状态机前置校验
  → 持 per-session event_bus.session_lock 做「读在途消息 + 改消息
  status + 状态机转移 + commit + publish」原子段 → 返回。
- pause：在途消息置 paused_truncated + 置位 pause_requested + publish
  speech_end(paused_truncated)；runner 在 chunk 边界停手并**锁外挂起**
  等 resume（run_generation 整轮持锁会死锁本端点，故 S2-6 起 runner
  锁粒度=逐 chunk，见 debate_runner._consume_stream）。
- resume：截断消息回 streaming + 清 pause_requested + signal_resume
  唤醒 + publish speech_start（同 seq 重发，§5.1）续写。
- restart：仅状态复位（*→waiting，generating 中 409），**消息全保留**
  （api.md:33：消息处置由 S2-F6 实现定）；cancel_requested + signal_resume
  唤醒可能的挂起 runner。
- quick：在途消息置 complete + 置位 quick_requested + 轮次判定
  （plan_finalize_target，与 _finalize_complete 共用公式）→ waiting/
  finished + publish speech_end(complete)；轮尽补 done(finished) +
  publish_done() 关流（§7 步骤 7）。
- quick 在 paused 的语义：**409**（api.md:80 脚注 4 已裁定回填）——跨
  线程无法保证先落库后发事件，要求先 resume 再 quick。
- 404 会话不存在或 private 越权；403 非 owner（课程教师可读 task
  会话但不可代学生控制，permissions §4 字面）；409 状态机错位
  （api.md:92 清单：pause 非 generating、resume 非 paused、restart
  于 generating 中、quick 非 generating）。
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import can_read_session, get_current_user
from app.core.database import get_db
from app.core.state_machine import INITIAL_STATE, IllegalTransition, transition
from app.models.course import Course, CourseMember
from app.models.message import Message
from app.models.session import TrainingSession, validate_session_visibility
from app.models.task import Task
from app.models.user import User
from app.schemas.message import (
    MessageCreate,
    MessageCreated,
    MessageListOut,
    MessageOut,
)
from app.schemas.session import (
    SessionCreate,
    SessionCreated,
    SessionOut,
    SessionStatusOut,
    SessionUpdate,
)
from app.services.debate_runner import build_provider, plan_finalize_target, run_generation
from app.services.event_bus import event_bus as _event_bus
from app.services.session_registry import SessionParams, session_registry

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# 404 统一文案：不存在与越权不可区分（存在性隐藏，api.md §3:89）
_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="会话不存在或无权访问",
)
# 403（用户 2026-10-14 裁定分层）：can_read_session 通过但非 owner——
# api.md:30 字面「403 非 owner」+ §3:90 ①已知资源+归属不符
_FORBIDDEN_NON_OWNER = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="仅会话创建者可修改",
)
# starlette 1.x 重命名（旧名 HTTP_422_UNPROCESSABLE_ENTITY 已弃用告警）
_UNPROCESSABLE = status.HTTP_422_UNPROCESSABLE_CONTENT
# messages 提交于非 waiting（api.md:35/92 状态机错位）
_CONFLICT_NOT_WAITING = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="会话当前状态不接受新消息",
)
# messages 403（api.md:35 错误列字面「403 非 owner」；写操作，与 PATCH 同分层）
_FORBIDDEN_SUBMIT = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="仅会话所有者可提交消息",
)
# task 跨用户引用（用户 2026-10-14 裁定）：task 存在未归档但不属于当前
# 用户 → 404 存在性隐藏（permissions §3：不暴露"存在但不是你的"）
_TASK_NOT_AVAILABLE = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="任务不存在或无权访问",
)
# S2-6 四端点错误分层（api.md:31-34 行字面 + §3:90 模式同 PATCH）：
# pause/quick 要求 generating；resume 要求 paused；restart 禁 generating
# （"先生成中，请先暂停"）。状态机 IllegalTransition 一律映射 409。
_CONFLICT_NOT_GENERATING = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="仅生成中可暂停/加速",
)
_CONFLICT_NOT_PAUSED = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="会话当前未处于暂停态",
)
_CONFLICT_GENERATING = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="生成中，请先暂停",
)
# 防御：generating/paused 却无在途消息=实现 bug（不向客户端暴露细节）
_INTERNAL_NO_STREAMING = HTTPException(
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    detail="会话状态与消息不一致",
)


def _transition_or_409(
    session: TrainingSession, event: str, target: str | None = None
) -> str:
    """状态机转移 + IllegalTransition → 409（api.md:92 清单字面）。"""
    try:
        session.status = (
            transition(session.status, event)
            if target is None
            else transition(session.status, event, target)
        )
    except IllegalTransition as exc:
        raise _CONFLICT_NOT_GENERATING from exc
    return session.status


def _publish(session_id: int, frame: dict) -> None:
    """事件帧发布（sse §10 先落库后发事件；调用点已在 commit 之后）。

    经单例 _event_bus 发布；_event_bus 是模块级别名，测试 monkeypatch
    本模块的 `_event_bus` 即可拦截（实例属性优先于类方法）。
    """
    _event_bus.publish(session_id, frame)


def _latest_assistant_streaming(db: Session, session_id: int) -> Message | None:
    """最新在途 assistant 消息（status='streaming'）。"""
    return db.scalars(
        select(Message)
        .where(
            Message.session_id == session_id,
            Message.role == "assistant",
            Message.status == "streaming",
        )
        .order_by(Message.seq.desc())
        .limit(1)
    ).first()


def _latest_assistant_paused_truncated(db: Session, session_id: int) -> Message | None:
    """最新被暂停截断的 assistant 消息（status='paused_truncated'）。"""
    return db.scalars(
        select(Message)
        .where(
            Message.session_id == session_id,
            Message.role == "assistant",
            Message.status == "paused_truncated",
        )
        .order_by(Message.seq.desc())
        .limit(1)
    ).first()


def _task_assignable_to(db: Session, user: User, task: Task) -> bool:
    """task 归属判定：课程教师本人，或课程成员（course_members 行）。

    成员分支在 S2 阶段恒空（无 join API，S3-3 落地后学生自动获得资格），
    当前实际生效的是"教师引用自己课程的 task"。
    """
    course = db.get(Course, task.course_id)
    if course is None:
        return False
    if course.teacher_id == user.id:
        return True
    return (
        db.scalar(
            select(CourseMember).where(
                CourseMember.course_id == task.course_id,
                CourseMember.user_id == user.id,
            )
        )
        is not None
    )


def _validate_task_binding(
    db: Session, user: User, visibility: str, task_id: int | None
) -> None:
    """E-2 应用层校验：visibility ⇔ task_id，task 存在、未归档、且归属本人。

    - visibility ⇔ task_id 违反 → 422（api.md:28/30 错误列）；
    - task 不存在/已归档 → 422（用户 2026-10-14 裁定，契约只列 401/422）；
    - task 跨用户引用 → 404（用户 2026-10-14 裁定，permissions §3
      存在性隐藏，不暴露归属细节）。
    """
    try:
        validate_session_visibility(visibility, task_id)
    except ValueError as exc:
        raise HTTPException(status_code=_UNPROCESSABLE, detail=str(exc)) from exc
    if visibility != "task":
        return
    task = db.get(Task, task_id)
    if task is None or task.is_archived:
        raise HTTPException(
            status_code=_UNPROCESSABLE,
            detail="task_id 指向的任务不存在或已归档",
        )
    if not _task_assignable_to(db, user, task):
        raise _TASK_NOT_AVAILABLE


@router.post("", status_code=status.HTTP_201_CREATED)
def create_session(
    body: SessionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionCreated:
    """创建练习会话（api.md:28）。初始 waiting，不自动进入 generating。"""
    _validate_task_binding(db, user, body.visibility, body.task_id)
    session = TrainingSession(
        owner_id=user.id,
        topic=body.topic,
        visibility=body.visibility,
        task_id=body.task_id,
        status=INITIAL_STATE,  # waiting（状态机初始态，硬约束⑤）
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    # 运行参数入进程内 registry（§5：脚注 1 不落表；key=session_id）。
    # messages POST body 只有 {content}——mode/max_turns 在创建时一次性带入。
    session_registry.set(
        session.id, SessionParams(mode=body.mode, max_turns=body.max_turns)
    )
    return SessionCreated(id=session.id, status=session.status)


@router.get("/{session_id}")
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionOut:
    """会话详情（api.md:29）。不存在/越权统一 404（存在性隐藏）。"""
    session = db.get(TrainingSession, session_id)
    if session is None or not can_read_session(db, user, session):
        raise _NOT_FOUND
    return SessionOut.model_validate(session)


@router.patch("/{session_id}")
def update_session(
    session_id: int,
    body: SessionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionOut:
    """修改会话元信息（api.md:30，errata E-17：出参平铺同 GET）。

    错误码分层：404（不可见/不存在）→ 403（可读非 owner）→ 422（E-2）；
    task 跨用户引用 → 404（存在性隐藏）。显式 null 与"不传"以
    model_fields_set 区分（task→private 需 task_id:null）。
    """
    session = db.get(TrainingSession, session_id)
    if session is None or not can_read_session(db, user, session):
        raise _NOT_FOUND
    if session.owner_id != user.id:
        raise _FORBIDDEN_NON_OWNER
    # 合并后再校验（E-2 约束的是 visibility×task_id 组合，api.md:30 422）
    new_visibility = (
        body.visibility if "visibility" in body.model_fields_set else session.visibility
    )
    new_task_id = body.task_id if "task_id" in body.model_fields_set else session.task_id
    _validate_task_binding(db, user, new_visibility, new_task_id)
    if body.topic is not None:
        session.topic = body.topic
    session.visibility = new_visibility
    session.task_id = new_task_id
    db.commit()
    db.refresh(session)
    return SessionOut.model_validate(session)


@router.post("/{session_id}/messages", status_code=status.HTTP_201_CREATED)
def submit_message(
    session_id: int,
    body: MessageCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MessageCreated:
    """提交学生消息（api.md:35）：同步落库 role='user' → 异步触发 AI 生成。

    契约逐条：
    - 201 {seq, created_at}：用户消息同步写 messages（seq 自增，E-1）；
    - 状态机：仅 waiting 接受（409 非 waiting，api.md:92 清单）；转移
      waiting→generating 由 runner 在临界区内做（§6 表 submit_message）；
    - 异步：BackgroundTasks 在线程池跑 debate_runner（TestClient 门户
      模式下同步执行完，见 §9）；
    - 权限：403 非 owner（api.md:35 错误列字面——messages 是写操作，
      课程教师可读 task 会话但不可代学生发言）；不可见 404；
    - 用户消息前端本地渲染，不走 SSE 回显（api.md:35 行为注）。
    """
    session = db.get(TrainingSession, session_id)
    if session is None or not can_read_session(db, user, session):
        raise _NOT_FOUND
    if session.owner_id != user.id:
        raise _FORBIDDEN_SUBMIT
    if session.status != "waiting":
        raise _CONFLICT_NOT_WAITING

    message = Message(
        session_id=session_id,
        role="user",  # schema_v3:22 'user'=学生；api.md:35 行为注字面
        agent_role=None,  # agent_role 仅 assistant 细分（schema_v3:23）
        content=body.content,
        status="complete",  # 用户消息同步完整落库；streaming/paused_truncated
        # 仅属 AI 在途生成（sse_events §10 一致性表）；前端本地渲染不回显
        # （api.md:35 行为注），DB 行仍供刷新/回放/审计读取。
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    # 异步 AI 生成：独立 db session（请求 session 在响应结束时 close，
    # BackgroundTasks 晚于响应执行——设计 §1 D2）。测试夹具可 override
    # sessions_module.get_session_factory 复用测试 session（见
    # tests/api/test_events.py runner_session_factory）。
    from app.core.database import get_session_factory

    def _run() -> None:
        runner_db = get_session_factory()()
        try:
            run_generation(session_id, db=runner_db, provider=build_provider())
        finally:
            runner_db.close()

    background_tasks.add_task(_run)
    return MessageCreated(seq=message.seq, created_at=message.created_at)


@router.post("/{session_id}/pause")
def pause_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionStatusOut:
    """暂停生成（api.md:31）：generating → paused，SSE 侧 speech_end(paused_truncated)。

    动作序列（S2-6 设计 §2.1，全部持 per-session 锁）：
    ① 状态机校验（非 generating → 409）；② 在途消息置
    paused_truncated（content=当前已 commit 全文=截断点）；③ 置位
    controller.pause_requested（runner chunk 边界据此停手）；④ 消息 +
    session 同事务 commit；⑤ commit 后 publish speech_end。先落库后
    发事件（§10）；与 runner 的 commit→publish 互斥，故本端点读到的
    content 是唯一确定截断点，speech_end 之后不可能再跟同 seq delta。
    """
    session = db.get(TrainingSession, session_id)
    if session is None or not can_read_session(db, user, session):
        raise _NOT_FOUND
    if session.owner_id != user.id:
        raise _FORBIDDEN_NON_OWNER
    if session.status != "generating":
        raise _CONFLICT_NOT_GENERATING

    with _event_bus.session_lock(session_id):
        if session.status != "generating":
            raise _CONFLICT_NOT_GENERATING
        target = _transition_or_409(session, "pause")
        message = _latest_assistant_streaming(db, session_id)
        if message is None:  # 防御：generating 却无在途消息=实现 bug
            raise _INTERNAL_NO_STREAMING
        message.status = "paused_truncated"
        _event_bus.controller(session_id).pause_requested = True
        db.commit()
        _publish(
            session_id,
            {
                "event": "speech_end",
                "session_id": session_id,
                "seq": message.seq,
                "status": "paused_truncated",
            },
        )
    return SessionStatusOut(id=session.id, status=session.status)


@router.post("/{session_id}/resume")
def resume_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionStatusOut:
    """恢复生成（api.md:32）：paused → generating，SSE 重发 speech_start（同 seq）续写。

    动作序列（S2-6 设计 §2.2）：① 状态机校验（非 paused → 409）；
    ② paused_truncated 在途消息回 streaming（回放/snapshot 语义正确）；
    ③ 清 pause_requested；④ 同事务 commit；⑤ signal_resume() 唤醒
    挂起的 runner；⑥ publish speech_start（§5.1 重发，start 不清本地
    内容，delta 追加即续写）。找不到截断消息（paused 却无在途行）→ 500。
    """
    session = db.get(TrainingSession, session_id)
    if session is None or not can_read_session(db, user, session):
        raise _NOT_FOUND
    if session.owner_id != user.id:
        raise _FORBIDDEN_NON_OWNER
    if session.status != "paused":
        raise _CONFLICT_NOT_PAUSED

    with _event_bus.session_lock(session_id):
        if session.status != "paused":
            raise _CONFLICT_NOT_PAUSED
        target = _transition_or_409(session, "resume")
        message = _latest_assistant_paused_truncated(db, session_id)
        if message is None:  # 防御：paused 却无截断消息=实现 bug
            raise _INTERNAL_NO_STREAMING
        message.status = "streaming"
        controller = _event_bus.controller(session_id)
        controller.pause_requested = False
        db.commit()
        controller.signal_resume()  # 唤醒挂起的 runner（§5.3 同 seq 续写）
        _publish(
            session_id,
            {
                "event": "speech_start",
                "session_id": session_id,
                "seq": message.seq,
                "agent_role": message.agent_role,
            },
        )
    return SessionStatusOut(id=session.id, status=session.status)


@router.post("/{session_id}/restart")
def restart_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionStatusOut:
    """重开会话（api.md:33）：* → waiting（消息全保留，处置留白 S2-F6）。

    generating 中 → 409（先暂停）；其余态（waiting/paused/finished/
    failed）均合法。paused 态若 runner 仍挂起（正常路径：pause 端点只
    置位，runner 停手有毫秒级延迟但已关在锁内，实际不可同时发生），
    置 cancel + signal_resume 唤醒它退出本轮；无挂起 runner 时的残留
    由下一轮 run_generation 入口统一清除（S2-6 裁定 5）。
    """
    session = db.get(TrainingSession, session_id)
    if session is None or not can_read_session(db, user, session):
        raise _NOT_FOUND
    if session.owner_id != user.id:
        raise _FORBIDDEN_NON_OWNER
    if session.status == "generating":
        raise _CONFLICT_GENERATING

    with _event_bus.session_lock(session_id):
        if session.status == "generating":
            raise _CONFLICT_GENERATING
        _transition_or_409(session, "restart")
        # 防御：paused 态理论上必有截断消息，此处兜底防脏数据卡住 waiting
        message = _latest_assistant_paused_truncated(db, session_id)
        if message is not None:
            message.status = "complete"  # 消息全保留（api.md:33：处置 S2-F6 定）
        controller = _event_bus.controller(session_id)
        controller.cancel_requested = True
        db.commit()
        controller.signal_resume()  # 无挂起 runner 也无害（幂等）
    return SessionStatusOut(id=session_id, status=session.status)


@router.post("/{session_id}/quick")
def quick_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionStatusOut:
    """加速定稿（api.md:34 + 脚注 4）：generating → {waiting, finished}。

    动作序列（S2-6 设计 §2.4）：① 状态机校验（非 generating → 409，
    含 paused——脚注 4 已裁定，要求先 resume）；② 轮次判定（与
    _finalize_complete 共用 plan_finalize_target：turns_done+1 >=
    max_turns → finished，否则 waiting）；③ 在途消息置 complete
    （"立即定稿"=截断到当前全文）；④ 置位 quick_requested；⑤ 同事务
    commit；⑥ publish speech_end(complete)；轮尽时补 publish
    done(finished) + publish_done() 关流（§7 步骤 7）。暂停态 409 字面
    见脚注 4（跨线程无法保证先落库后发事件）。
    """
    session = db.get(TrainingSession, session_id)
    if session is None or not can_read_session(db, user, session):
        raise _NOT_FOUND
    if session.owner_id != user.id:
        raise _FORBIDDEN_NON_OWNER
    if session.status != "generating":
        raise _CONFLICT_NOT_GENERATING

    with _event_bus.session_lock(session_id):
        if session.status != "generating":
            raise _CONFLICT_NOT_GENERATING
        params = session_registry.get(session_id)
        max_turns = params.max_turns if params else 1
        target = _transition_or_409(
            session, "quick", plan_finalize_target(db, session_id, max_turns)
        )
        message = _latest_assistant_streaming(db, session_id)
        if message is None:  # 防御：generating 却无在途消息=实现 bug
            raise _INTERNAL_NO_STREAMING
        message.status = "complete"
        _event_bus.controller(session_id).quick_requested = True
        db.commit()
        _publish(
            session_id,
            {
                "event": "speech_end",
                "session_id": session_id,
                "seq": message.seq,
                "status": "complete",
            },
        )
        if target == "finished":
            _publish(
                session_id, {"event": "done", "session_id": session_id, "reason": "finished"}
            )
            _event_bus.publish_done(session_id)
    return SessionStatusOut(id=session.id, status=session.status)


@router.get("/{session_id}/messages")
def list_messages(
    session_id: int,
    after_seq: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MessageListOut:
    """会话历史分页（api.md:38）：after_seq 之后按 seq 升序，limit 截断。"""
    session = db.get(TrainingSession, session_id)
    if session is None or not can_read_session(db, user, session):
        raise _NOT_FOUND
    rows = db.scalars(
        select(Message)
        .where(Message.session_id == session_id, Message.seq > after_seq)
        .order_by(Message.seq.asc())
        .limit(limit)
    ).all()
    messages = [MessageOut.model_validate(row) for row in rows]
    next_seq = rows[-1].seq if rows else after_seq
    return MessageListOut(messages=messages, next_seq=next_seq)
