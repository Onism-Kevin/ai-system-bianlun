"""S2-1：JWT 签发/校验 + bcrypt 密码哈希。

- bcrypt 只调用库函数（requirements bcrypt>=4.1），不自行实现哈希；
- JWT 为 HS256，载荷 sub=用户 id（字符串形式）+ iat/exp，过期时间取
  settings.jwt_expire_days（默认 7 天，S2-1 写进 config，可环境变量覆盖）；
- 校验失败统一抛 InvalidToken，由 api/deps.py 的 get_current_user 转 401；
- 密码哈希只在 register 落库 / login 校验时短暂出现在内存：
  不记日志、不回显、不进 audit/commit（schema_v3 audit 敏感数据约定 + 用户硬约束⑤）。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings

ALGORITHM = "HS256"

# bcrypt 库函数按**字节**计上限（不是字符数）；多字节密码（如中文）受此约束
BCRYPT_MAX_BYTES = 72


class InvalidToken(ValueError):
    """token 缺失/篡改/过期/载荷非法（调用方转 401，不外泄具体原因）。"""


def hash_password(password: str) -> str:
    """bcrypt 哈希（gensalt 默认 cost=12）。调用方保证已通过字节上限校验。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """bcrypt 校验。超 72 字节或哈希串非法一律视为不匹配（转 401），不抛 500——
    register 侧已限字节数，此防御分支只针对畸形登录请求/脏数据。"""
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


def create_access_token(user_id: int) -> str:
    """签发 JWT：sub=str(user_id)，iat=now，exp=now + jwt_expire_days 天。"""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_expire_days),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> int:
    """校验签名/过期并取出用户 id；任何失败抛 InvalidToken。"""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],
        )
    except jwt.PyJWTError as exc:  # 过期/签名错/结构错统一为无效凭据
        raise InvalidToken(str(exc)) from exc
    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub.isdigit():
        raise InvalidToken(f"token 载荷 sub 非法：{sub!r}")
    return int(sub)
