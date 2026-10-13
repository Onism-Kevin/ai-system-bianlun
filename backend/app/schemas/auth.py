"""S2-1：auth 三端点的 Pydantic 出入参。

出参形状逐字对齐 docs/contracts/api.md v1.2 auth 三行：
- register：201 {id, username, roles[]}
- login：200 {user}（Set-Cookie 走响应头，不进响应体）
- me：200 {user, roles[]}

username 规则由本文件定义——schema_v1.md §1 注：users.username 的
字符集/长度/允许字符规则由 S2-1（register API）定义，表 VARCHAR(50)
只提供存储上限。定案：3~50 位，字母/数字/下划线/连字符（登录标识，
不允许空格与控制字符）。
密码：8~72 **字符**且不超过 72 **字节**（72 是 bcrypt 库函数的字节上限，
多字节密码如中文必须按字节校验，否则哈希阶段抛 ValueError → 500）。
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

USERNAME_PATTERN = r"^[A-Za-z0-9_-]{3,50}$"


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=USERNAME_PATTERN)
    password: str = Field(min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def _password_byte_limit(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("密码超过 72 字节上限（bcrypt 限制）")
        return v


class LoginRequest(BaseModel):
    """登录入参宽松：任何字符串都不拦截，不匹配即 401（认证失败不是入参问题）。"""

    username: str
    password: str


class AuthUser(BaseModel):
    """登录态用户公开信息（password_hash 永不入响应）。"""

    id: int
    username: str
    display_name: str | None


class RegisterResponse(BaseModel):
    id: int
    username: str
    roles: list[str]


class LoginResponse(BaseModel):
    user: AuthUser


class MeResponse(BaseModel):
    user: AuthUser
    roles: list[str]
