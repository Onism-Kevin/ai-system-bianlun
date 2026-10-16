"""S2-4：messages 端点出入参（api.md:35 逐字对照）。

- POST /api/sessions/{id}/messages body {content}，201 {seq, created_at}
  （api.md:35：seq 自增 E-1 方案 A；用户消息同步落库，异步触发 AI
  生成——等 SSE 回放/推送，不走 SSE 回显）。
- GET /api/sessions/{id}/messages（api.md:38）200 {messages: [...],
  next_seq}；按 after_seq 过滤 + limit 分页，供前端历史补齐。
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# role/agent_role/status 枚举与 models/message.py 一致（字面核对）
MessageRole = Literal["user", "assistant", "system"]
AgentRole = Literal["pro", "con", "judge", "coach"]
MessageStatus = Literal["streaming", "complete", "paused_truncated"]


class MessageCreate(BaseModel):
    """POST /api/sessions/{id}/messages 入参（api.md:35）：{content}。"""

    content: str = Field(min_length=1)


class MessageCreated(BaseModel):
    """POST /api/sessions/{id}/messages 出参（api.md:35）：{seq, created_at}。"""

    seq: int
    created_at: datetime


class MessageOut(BaseModel):
    """单条消息出参（api.md:38 messages 数组元素字段清单）。"""

    model_config = ConfigDict(from_attributes=True)

    seq: int
    role: MessageRole
    agent_role: AgentRole | None
    content: str
    status: MessageStatus
    created_at: datetime


class MessageListOut(BaseModel):
    """GET /api/sessions/{id}/messages 出参（api.md:38）。

    next_seq：下一页起点（已取到的最大 seq；无消息时=请求的 after_seq）。
    """

    messages: list[MessageOut]
    next_seq: int
