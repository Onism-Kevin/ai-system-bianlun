"""S2-8：论证结构分析 stage API（api.md:44）。

POST /api/sessions/{id}/analyze — 无 body（读会话 user 消息）。

流程：get_current_user（401）→ can_read_session（404）→ 读 role='user'
非 streaming 消息 → 零行 422 → structured 生成 ArgumentMap → 后置过滤
source_ref → 返回。

错误码：
- 401：未登录 / Cookie 无效（get_current_user 依赖）
- 404：会话不存在或 private 越权（can_read_session，存在性隐藏）
- 422：空会话（无 user 消息）；StructuredValidationError（E-22）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
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
from app.prompts.analyze import build_messages
from app.schemas.stage_outputs import ArgumentMap
from app.services.debate_runner import build_provider

router = APIRouter(prefix="/api/sessions", tags=["analyze"])

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="会话不存在或无权访问",
)
_UNPROCESSABLE = status.HTTP_422_UNPROCESSABLE_CONTENT


def _generate_text(provider: ModelProvider, model: str, messages: list[dict]) -> str:
    """把 provider 流式输出收集为单个字符串（供 generate_structured 使用）。"""
    chunks: list[str] = []
    for chunk in provider.generate_stream(model=model, messages=messages):
        chunks.append(chunk)
    return "".join(chunks)


@router.post("/{session_id}/analyze")
def analyze_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ArgumentMap:
    """论证结构分析（api.md:44）。无 body，读会话 user 消息。

    流程：
    1. get_current_user → 401（依赖层）
    2. can_read_session → 404（资源级判定，存在性隐藏）
    3. 读 role='user' AND status != 'streaming' 的消息（按 seq 升序）
    4. 零行 → 422 "会话无消息可分析，请先完成至少一轮对话"
    5. structured.generate_structured(messages, ArgumentMap, generate)
    6. 后置过滤 source_ref：message_seq 不在 valid_seq_set → 置 None
    7. StructuredValidationError → 422（E-22）
    """
    session = db.get(TrainingSession, session_id)
    if session is None or not can_read_session(db, user, session):
        raise _NOT_FOUND

    # 读 role='user' AND status != 'streaming' 的消息（只分析学生论证）
    # paused_truncated 纳入：学生已写的内容就是他的论证，不完整也是真实状态。
    # MVP 假设会话短（max_turns=1，通常 ≤10 条 user 消息）。
    # S5 若出现长会话需加窗口管理（如只读最近 N 条或摘要）。
    rows = db.scalars(
        select(Message)
        .where(
            Message.session_id == session_id,
            Message.role == "user",
            Message.status != "streaming",
        )
        .order_by(Message.seq.asc())
    ).all()

    if not rows:
        raise HTTPException(
            status_code=_UNPROCESSABLE,
            detail="会话无消息可分析，请先完成至少一轮对话",
        )

    # 构造 prompt 消息（带 seq 渲染，供 source_ref 引用）
    messages = [
        {
            "seq": row.seq,
            "role": row.role,
            "agent_role": row.agent_role,
            "content": row.content,
        }
        for row in rows
    ]
    valid_seq_set = {row.seq for row in rows}

    provider = build_provider()

    from app.core.config import get_settings  # 延迟导入：测试环境可无网关配置

    settings = get_settings()
    try:
        result, _ = generate_structured(
            messages,
            ArgumentMap,
            lambda msgs: _generate_text(provider, settings.model_default, msgs),
        )
    except StructuredValidationError as exc:
        raise HTTPException(
            status_code=_UNPROCESSABLE,
            detail=str(exc),
        ) from exc

    # 后置过滤 source_ref：message_seq 不在 valid_seq_set → 置 None
    # source_ref=None 有两种来源：
    # 1. 模型判断该节点无直接来源（综合结论/模型推断）
    # 2. 模型输出了 message_seq 但不在 valid_seq_set 里（幻觉 seq 被过滤）
    # MVP 不区分，S5+ 可加 filtered_refs 字段记录被过滤的原始 seq。
    for node in result.nodes:
        if (
            node.source_ref is not None
            and node.source_ref.message_seq not in valid_seq_set
        ):
            node.source_ref = None

    return result
