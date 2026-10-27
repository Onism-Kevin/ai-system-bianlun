"""S2-7：议题探索 stage API（api.md:43）。

POST /api/sessions/{id}/explore — 无 body（读会话 topic）。

流程：get_current_user（401）→ can_read_session（404）→ 读 session.topic →
structured 生成（ExploreOut）→ 返回。

错误码：
- 401：未登录 / Cookie 无效（get_current_user 依赖）
- 404：会话不存在或 private 越权（can_read_session，存在性隐藏）
- 422：空 topic（api.md:43 字面）；StructuredValidationError（同步端点映射）

E-21：len(topic) > 5000 防御性检查——当前 schema 下 session.topic 是
VARCHAR(200)，此分支不会触发。无测试覆盖。未来 schema 扩大到
VARCHAR(5000)+ 时此检查生效，届时补测试。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import can_read_session, get_current_user
from app.core.database import get_db
from app.core.exceptions import StructuredValidationError
from app.core.model_provider import ModelProvider
from app.core.structured import generate_structured
from app.models.session import TrainingSession
from app.models.user import User
from app.prompts.explore import build_messages
from app.schemas.stage_outputs import ExploreOut
from app.services.debate_runner import build_provider

router = APIRouter(prefix="/api/sessions", tags=["explore"])

# E-21：防御性检查——当前 schema 下 session.topic 是 VARCHAR(200)，
# 此分支不会触发。无测试覆盖（errata E-21）。未来 schema 扩大到
# VARCHAR(5000)+ 时此检查生效，届时补测试。
_TOPIC_MAX_DEFENSIVE = 5000

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


@router.post("/{session_id}/explore")
def explore_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExploreOut:
    """议题探索（api.md:43）。无 body，读会话 topic。

    流程：
    1. get_current_user → 401（依赖层）
    2. can_read_session → 404（资源级判定，存在性隐藏）
    3. 读 session.topic，空则 422
    4. 防御性 len(topic) > 5000 检查（E-21，当前不触发）
    5. 调 structured.generate_structured(messages, ExploreOut, generate)
    6. StructuredValidationError → 422
    """
    # 401: get_current_user（依赖）；404: can_read_session（资源级判定）
    session = db.get(TrainingSession, session_id)
    if session is None or not can_read_session(db, user, session):
        raise _NOT_FOUND

    topic = session.topic

    # 422: 空 topic（api.md:43 字面）
    if not topic.strip():
        raise HTTPException(
            status_code=_UNPROCESSABLE,
            detail="议题内容为空",
        )

    # 防御性检查（E-21）：当前 schema 下不会触发，无测试覆盖。
    # 未来 schema 扩大到 VARCHAR(5000)+ 时此检查生效，届时补测试。
    if len(topic) > _TOPIC_MAX_DEFENSIVE:
        raise HTTPException(
            status_code=_UNPROCESSABLE,
            detail="topic 超长",
        )

    messages = build_messages(topic)
    provider = build_provider()

    from app.core.config import get_settings  # 延迟导入：测试环境可无网关配置

    settings = get_settings()
    try:
        result, _ = generate_structured(
            messages,
            ExploreOut,
            lambda msgs: _generate_text(provider, settings.model_default, msgs),
        )
    except StructuredValidationError as exc:
        raise HTTPException(
            status_code=_UNPROCESSABLE,
            detail=str(exc),
        ) from exc

    return result
