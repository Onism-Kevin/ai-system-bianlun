"""S2-9：教练式追问 + 反方对练 stage API（api.md:45）。

POST /api/sessions/{id}/coach_turn — body {mode: "coach"|"rebuttal"}。

流程：get_current_user（401）→ can_read_session（404）→ 读 user 消息
（最近 20 条）+ assistant 消息（最近 5 条）→ 零 user 消息 422 → dispatch
mode → structured 生成 CoachTurn → 后置过滤 quote_refs → 返回。

错误码：
- 401：未登录 / Cookie 无效（get_current_user 依赖）
- 404：会话不存在或 private 越权（can_read_session，存在性隐藏）
- 422：mode 非法（非 coach/rebuttal）；空会话（无 user 消息）；
  StructuredValidationError（E-22）
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import can_read_session, get_current_user
from app.core.database import get_db
from app.core.exceptions import StructuredValidationError
from app.core.model_provider import ModelProvider
from app.core.structured import generate_structured
from app.models.message import Message
from app.models.session import TrainingSession
from app.models.user import User
from app.schemas.stage_outputs import CoachTurn
from app.services.debate_runner import build_provider

router = APIRouter(prefix="/api/sessions", tags=["coach_turn"])

logger = logging.getLogger(__name__)

# MVP 窗口限制
_USER_WINDOW = 20  # user 消息软上限
_AI_WINDOW = 5  # assistant 消息上限

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="会话不存在或无权访问",
)
_UNPROCESSABLE = status.HTTP_422_UNPROCESSABLE_CONTENT


class CoachTurnRequest(BaseModel):
    """POST /api/sessions/{id}/coach_turn 入参（api.md:45）。"""

    mode: Literal["coach", "rebuttal"]


def _generate_text(provider: ModelProvider, model: str, messages: list[dict]) -> str:
    """把 provider 流式输出收集为单个字符串（供 generate_structured 使用）。"""
    chunks: list[str] = []
    for chunk in provider.generate_stream(model=model, messages=messages):
        chunks.append(chunk)
    return "".join(chunks)


@router.post("/{session_id}/coach_turn")
def coach_turn_session(
    session_id: int,
    body: CoachTurnRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CoachTurn:
    """教练式追问 / 反方对练（api.md:45）。

    流程：
    1. get_current_user → 401（依赖层）
    2. can_read_session → 404（资源级判定，存在性隐藏）
    3. 读 user 消息（最近 20 条）+ assistant 消息（最近 5 条）
    4. 零 user 消息 → 422 "会话无消息可分析"
    5. dispatch：mode="coach" → coach.build_messages；
       mode="rebuttal" → rebuttal.build_messages
    6. structured.generate_structured(messages, CoachTurn, generate)
    7. 后置过滤 quote_refs：message_seq 不在 user_seq_set 的条目被移除
    8. StructuredValidationError → 422（E-22）
    """
    session = db.get(TrainingSession, session_id)
    if session is None or not can_read_session(db, user, session):
        raise _NOT_FOUND

    # 读 user 消息（多查 1 条用于判断是否超限）
    user_rows = db.scalars(
        select(Message)
        .where(
            Message.session_id == session_id,
            Message.role == "user",
            Message.status != "streaming",
        )
        .order_by(Message.seq.desc())
        .limit(_USER_WINDOW + 1)
    ).all()
    if len(user_rows) > _USER_WINDOW:
        logger.warning(
            "会话 user 消息超过 %d 条，coach 只读最近 %d 条",
            _USER_WINDOW, _USER_WINDOW,
        )
        user_rows = user_rows[:_USER_WINDOW]
    user_rows.reverse()  # 反转为升序

    if not user_rows:
        raise HTTPException(
            status_code=_UNPROCESSABLE,
            detail="会话无消息可分析，请先完成至少一轮对话",
        )

    # 读 assistant 消息（最近 5 条，升序）
    ai_rows = db.scalars(
        select(Message)
        .where(
            Message.session_id == session_id,
            Message.role == "assistant",
            Message.status != "streaming",
        )
        .order_by(Message.seq.desc())
        .limit(_AI_WINDOW)
    ).all()
    ai_rows.reverse()  # 反转为升序

    # 合并：按 seq 升序交错（对话时序正确——学生说一句，AI 回一句）
    # 边界：若 assistant 消息的 seq 早于
    # user_rows[0].seq（对应 user 消息被 20 条窗口
    # 截断），该 assistant 消息孤立在 history 开头。
    # MVP 会话短不触发，S5 若出现长会话需过滤
    # seq < user_rows[0].seq 的 assistant 消息。
    history = sorted([*user_rows, *ai_rows], key=lambda r: r.seq)

    # 构造 prompt 消息（带 seq 渲染，供 quote_refs 引用）
    messages = [
        {
            "seq": row.seq,
            "role": row.role,
            "agent_role": row.agent_role,
            "content": row.content,
        }
        for row in history
    ]
    user_seq_set = {row.seq for row in user_rows}

    # dispatch：mode → prompt builder
    if body.mode == "coach":
        from app.prompts.coach import build_messages as _build
    else:
        from app.prompts.rebuttal import build_messages as _build
    prompt_messages = _build(messages)

    provider = build_provider()

    from app.core.config import get_settings  # 延迟导入：测试环境可无网关配置

    settings = get_settings()
    try:
        result, _ = generate_structured(
            prompt_messages,
            CoachTurn,
            lambda msgs: _generate_text(provider, settings.model_default, msgs),
        )
    except StructuredValidationError as exc:
        raise HTTPException(
            status_code=_UNPROCESSABLE,
            detail=str(exc),
        ) from exc

    # 后置过滤 quote_refs：message_seq 不在 user_seq_set 的条目被移除
    # quote_refs 过滤：message_seq 不在 user_seq_set 的条目被移除。
    # 两种来源导致空引用：
    # 1. 模型判断无需引用（理论上 prompt 要求至少 1 条，但模型可能忽略）
    # 2. 模型输出的 message_seq 不在 user_seq_set（幻觉 seq 被过滤）
    # MVP 不区分，S5+ 可加 filtered_refs 字段记录被过滤的原始 seq。
    result.quote_refs = [
        quote_ref
        for quote_ref in result.quote_refs
        if quote_ref.seq in user_seq_set
    ]

    return result
