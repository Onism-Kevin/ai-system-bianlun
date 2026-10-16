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
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import can_read_session, get_current_user
from app.core.database import get_db
from app.core.state_machine import INITIAL_STATE
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
    SessionUpdate,
)
from app.services.debate_runner import build_provider, run_generation
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
