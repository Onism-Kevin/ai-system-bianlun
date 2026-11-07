"""S3-3：tasks 端点出入参（api.md:60-64，逐字对齐）。

join_code 可见性（api.md:62：仅课程教师响应保留）：
- `TaskOut`（基类）：**不含** join_code 字段 → 学生响应该键完全缺席；
- `TaskWithCodeOut`：继承基类并追加 `join_code: str | None` → 课程教师响应带码。
实现上 `GET /api/tasks/{id}` 不声明 response_model、按角色返回对应模型
（FastAPI 对无 response_model 的返回值直接 jsonable_encoder，不补字段）。

列表端点 `GET /api/courses/{course_id}/tasks` 一律返回 `TaskOut`（不含码），
与 courses 列表的"一律不带码"决策一致（用户 2026-11-07 拍板 A）。
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TaskOut(BaseModel):
    """任务公开信息（学生可见，**不含 join_code**）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    title: str
    material: str | None = None
    deadline: datetime | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class TaskWithCodeOut(TaskOut):
    """课程教师视角（含 join_code，可为 None=无需加入码）。"""

    join_code: str | None = None


class TaskCreate(BaseModel):
    """POST /api/courses/{course_id}/tasks 入参：{title, material?, deadline?, need_join_code?}。"""

    title: str = Field(min_length=1, max_length=120)
    material: str | None = None
    deadline: datetime | None = None
    need_join_code: bool = False


class TaskUpdate(BaseModel):
    """PATCH /api/tasks/{id} 入参（全部可选；用 exclude_unset 区分未传/显式 null）。"""

    title: str | None = Field(default=None, min_length=1, max_length=120)
    material: str | None = None
    deadline: datetime | None = None
    is_archived: bool | None = None


class TaskJoinRequest(BaseModel):
    """POST /api/tasks/{id}/join 入参：{join_code}。"""

    join_code: str = Field(min_length=1, max_length=8)


class TaskJoinResponse(BaseModel):
    """POST /api/tasks/{id}/join 出参：200 {course_id, task_id}（幂等）。"""

    course_id: int
    task_id: int
