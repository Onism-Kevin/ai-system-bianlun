"""S2-11：revisions 端点出入参（api.md:50-53 逐字对照）。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RevisionCreate(BaseModel):
    """POST /api/revisions 入参（api.md:50）。"""

    session_id: int
    content: str = Field(min_length=1, description="观点内容，不可为空")
    status: Literal["draft", "final"] = "draft"  # E-5：status draft/final


class RevisionUpdate(BaseModel):
    """PATCH /api/revisions/{id} 入参（api.md:51）。

    content/status 均可选（不传=不动）；显式 null 与"不传"以
    model_fields_set 区分。
    """

    content: str | None = Field(default=None, min_length=1)
    status: Literal["draft", "final"] | None = None


class RevisionOut(BaseModel):
    """revision 完整出参（id/version/status/content/created_at）。"""

    id: int
    version: int
    status: str
    content: str
    created_at: str


class RevisionPostResponse(BaseModel):
    """POST 出参（api.md:50）：{id, version, status, diff:null}。

    diff 在新版本总是 null（无上一版可 diff）。
    """

    id: int
    version: int
    status: str
    diff: str | None = None


class RevisionDetailOut(BaseModel):
    """PATCH/GET 单条出参（api.md:51/53）：{revision, diff_vs_prev}。"""

    revision: RevisionOut
    diff_vs_prev: str | None = None


class RevisionListItem(BaseModel):
    """GET 列表出参（api.md:52）：每项含 diff_vs_prev。"""

    id: int
    version: int
    status: str
    content: str
    created_at: str
    diff_vs_prev: str | None = None
