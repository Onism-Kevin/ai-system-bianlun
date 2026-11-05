"""S3-2：courses 端点出入参（api.md:54-59，逐字对齐）。

invite_code 可见性（api.md:56：仅课程教师响应保留，学生响应剔除）：
- `CourseOut`（基类）：**不含** invite_code 字段 → 学生响应该键完全缺席；
- `CourseWithCodeOut`：继承基类并追加 `invite_code: str` → 课程教师响应带码。
实现上 `GET /api/courses/{id}` 不声明 response_model、按角色返回对应模型
（FastAPI 对无 response_model 的返回值直接 jsonable_encoder，不补字段）。

列表端点 `GET /api/courses` 一律返回 `CourseOut`（不含码）——加入码由单课
详情端点提供，避免列表里按行区分可见性。
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CourseOut(BaseModel):
    """课程公开信息（学生可见，**不含 invite_code**）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    teacher_id: int
    name: str
    description: str | None = None
    term: str | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class CourseWithCodeOut(CourseOut):
    """课程教师视角（含 invite_code）。"""

    invite_code: str


class CourseCreate(BaseModel):
    """POST /api/courses 入参：{name, description?, term?}。"""

    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    term: str | None = Field(default=None, max_length=20)


class CourseUpdate(BaseModel):
    """PATCH /api/courses/{id} 入参（全部可选；用 exclude_unset 区分未传/显式 null）。"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    term: str | None = Field(default=None, max_length=20)
    is_archived: bool | None = None


class CourseMemberOut(BaseModel):
    """成员行：仅学生行（course_members 无教师行，schema_v1 §4.2）。"""

    user_id: int
    username: str
    joined_at: datetime


class CourseJoinRequest(BaseModel):
    """POST /api/courses/join 入参：{invite_code}。"""

    invite_code: str = Field(min_length=1, max_length=8)


class CourseJoinResponse(BaseModel):
    """POST /api/courses/join 出参：200 {course_id}（幂等）。"""

    course_id: int
