"""S3-5：feedback 端点出入参（api.md:68-69，逐字对齐）。

feedback_forms.scores 的三维度（用户 2026-11-07 S3-5 拍板，schema_v3 表 4 定稿）：

    {"difficulty": 1-5, "coach_helpful": 1-5, "time_reasonable": 1-5}

**语义区分（不可混用）**：
- 本表三维度 = **学生对任务的体验评分**（难度 / 教练帮助 / 时间安排）；
- rubric.json 四维度 = **学生论证质量评分**（S1-9/S2-10）。
两者评价对象与语义不同，前端不得复用同一套渲染/权重。

upstream：POST 出参 `{id}`（upsert，UNIQUE(task_id, student_id)）；
GET 出参 `[{student_id, scores, comment, created_at}]`（教师读）。
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FeedbackScores(BaseModel):
    """学生对任务的体验评分（三维度，各 1-5）。"""

    difficulty: int = Field(ge=1, le=5, description="任务难度")
    coach_helpful: int = Field(ge=1, le=5, description="教练/反馈帮助")
    time_reasonable: int = Field(ge=1, le=5, description="时间安排合理性")


class FeedbackCreate(BaseModel):
    """POST /api/tasks/{task_id}/feedback 入参：{scores, comment}。"""

    scores: FeedbackScores
    comment: str | None = None


class FeedbackPostResponse(BaseModel):
    """POST 出参：200 {id}（upsert 成功）。"""

    id: int


class FeedbackOut(BaseModel):
    """GET 出参项：{student_id, scores, comment, created_at}。

    `created_at` 映射 DB 列 `submitted_at`（契约 api.md:69 用 created_at）。
    """

    student_id: int
    scores: FeedbackScores
    comment: str | None
    created_at: datetime


class CourseSummaryOut(BaseModel):
    """GET /api/courses/{course_id}/summary 出参（api.md:70）。

    `top_pending_verification` 在 MVP 返回 `[]`（errata E-29：reports 表无
    结构化待核实项字段，summary_text 是 markdown 拼接无法可靠提取；
    S5 需要时 S2-10 报告生成时提取存入 reports 新列）。
    """

    submitted_count: int
    total_students: int
    top_pending_verification: list[dict] = Field(default_factory=list)
