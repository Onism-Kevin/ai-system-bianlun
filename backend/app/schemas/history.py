"""S2-12：训练历史列表/详情出入参（api.md:40-41 逐字对照）。"""
from __future__ import annotations

from pydantic import BaseModel


class HistoryItem(BaseModel):
    """历史列表出参（api.md:40）：[{id, topic, status, created_at, updated_at}]。

    5 字段（无 visibility/task_id）——列表是 owner 视角，visibility 恒可读，
    task_id 是内部元数据不外露。
    """

    id: int
    topic: str
    status: str
    created_at: str
    updated_at: str


class HistoryDetailOut(BaseModel):
    """历史详情出参（api.md:41）：{session, messages:[按 seq 升序]}。

    session 是完整 SessionOut（7 字段），messages 是 list[MessageOut]。
    """

    session: dict  # 完整 SessionOut（7 字段）
    messages: list[dict]  # list[MessageOut]（含 streaming）
