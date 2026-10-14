"""S2-3：sessions 端点出入参（api.md:28-30 逐字对照）。

- POST 入参形状（api.md:28）：{topic, mode="debate", max_turns=1,
  visibility="private", task_id=null}；mode/max_turns 为运行参数（脚注 1：
  不落表），本层接收默认值后仅透传给后续运行轨（S2-6 消费）。
- POST 出参（api.md:28）：{id, status}，一律 201（脚注 3 取代计划书 200）。
- GET/PATCH 出参（api.md:29/30）：{id, topic, visibility, task_id, status,
  created_at, updated_at}；PATCH 字面为 {session}——按 S2-1 同款约定
  （auth/login:27 {user} → LoginResponse{user}）实现为 {"session": {...}}
  外层包裹。
- PATCH 入参（api.md:30）：{topic?, visibility?, task_id?}；status 不在
  其中（状态机独占，pause/resume/restart/quick 走 S2-6）——收到 status
  字段显式报 422，避免静默忽略。
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# visibility 枚举与 schema_v2 sessions.visibility ENUM 一致（E-2 校验的前提）
Visibility = Literal["private", "task"]

# topic 上限与 models/session.py TrainingSession.topic String(200) 一致
TOPIC_MAX = 200


class SessionCreate(BaseModel):
    """POST /api/sessions 入参（api.md:28）。"""

    topic: str = Field(min_length=1, max_length=TOPIC_MAX)
    mode: str = "debate"  # 运行参数（脚注 1：不落表，S2-6 消费）
    max_turns: int = 1  # 运行参数（脚注 1：不落表，S2-6 消费）
    visibility: Visibility = "private"
    task_id: int | None = None


class SessionUpdate(BaseModel):
    """PATCH /api/sessions/{id} 入参（api.md:30）：{topic?, visibility?, task_id?}。

    - 全字段可选（不传=不动）；显式 null 与"不传"以 model_fields_set 区分
      （task→private 切换需 task_id:null）。
    - extra=forbid：未知字段 422（api.md:91 pydantic 校验族）。
    - status 字段显式拒 422：状态机独占（api.md:30），pause/resume/restart/
      quick 端点（S2-6）是唯一状态转移入口。
    """

    model_config = ConfigDict(extra="forbid")

    topic: str | None = Field(default=None, min_length=1, max_length=TOPIC_MAX)
    visibility: Visibility | None = None
    task_id: int | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_status(cls, data: object) -> object:
        if isinstance(data, dict) and "status" in data:
            raise ValueError("status 字段由状态机独占（api.md:30），不可 PATCH")
        return data


class SessionCreated(BaseModel):
    """POST /api/sessions 出参（api.md:28）：{id, status}（脚注 3：201）。"""

    id: int
    status: str


class SessionOut(BaseModel):
    """会话完整出参（api.md:29/30 字段清单）。

    from_attributes=True：GET/PATCH 直接序列化 ORM 行。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    topic: str
    visibility: str
    task_id: int | None
    status: str
    created_at: datetime
    updated_at: datetime


class SessionPatchResponse(BaseModel):
    """PATCH 出参（api.md:30 字面 {session}，同 S2-1 LoginResponse{user} 约定）。"""

    session: SessionOut
