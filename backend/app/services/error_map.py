"""S2-13：数据库异常分类 → HTTP 状态码映射（errata E-6）。

E-6 教训：MySQL ENUM 违规抛 DataError(1265) 不是 IntegrityError。
错误分类映射必须同时捕获 DataError 与 IntegrityError：
- DataError(1265) → 422（用户输入非法值/服务端枚举不一致）
- IntegrityError(1062) → 409（唯一键冲突，如重复提交）
- IntegrityError(1451/1452) → 409（外键约束）
- 其他 → 500（未分类故障，附日志）
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.exc import DataError, IntegrityError


def classify_db_error(exc: Exception) -> tuple[int, str]:
    """数据库异常 → (HTTP 状态码, 用户文案)。

    供 main.py 的 @app.exception_handler 使用。
    """
    if isinstance(exc, DataError):
        return status.HTTP_422_UNPROCESSABLE_CONTENT, "输入数据非法（ENUM 字段值不在允许范围）"
    if isinstance(exc, IntegrityError):
        original = exc.orig
        if original is not None and original.args:
            code = original.args[0]
            if code == 1062:
                return status.HTTP_409_CONFLICT, "重复提交（唯一键冲突）"
            if code in (1451, 1452):
                return status.HTTP_409_CONFLICT, "引用约束冲突（外键）"
        return status.HTTP_409_CONFLICT, "数据冲突"
    return status.HTTP_500_INTERNAL_SERVER_ERROR, "服务器内部错误"
