"""ORM 模型包（S1-2 起）。import 本包即注册全部表到 Base.metadata。"""
from app.models.base import Base
from app.models.course import Course, CourseMember
from app.models.session import (
    SESSION_STATUS_ENUM,
    SESSION_VISIBILITY_ENUM,
    TrainingSession,
    validate_session_visibility,
)
from app.models.task import Task, TaskSubmission
from app.models.user import User, UserRole

__all__ = [
    "Base",
    "User",
    "UserRole",
    "Course",
    "CourseMember",
    "Task",
    "TaskSubmission",
    "TrainingSession",
    "SESSION_VISIBILITY_ENUM",
    "SESSION_STATUS_ENUM",
    "validate_session_visibility",
]
