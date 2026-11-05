"""S3-2：加入码生成（api.md:54/:60，schema_v1 §3.2 / schema_v2 表 1）。

规则（契约原文）：6~8 位 A-Z0-9，剔除易混淆字符 I/O/0/1。

- **用 `secrets` 而非 `random`**：加入码是能力凭据（持码即可入组），
  必须密码学安全；`random.choice` 可被预测，`secrets` 是 stdlib、零新增依赖。
- 字母表：A-Z 剔除 I/O（24）+ 数字 2-9（剔除 0/1，8）= 32 个字符；
  长度固定 8（满足"6~8 位"，且 `courses.invite_code`/`tasks.join_code`
  均为 VARCHAR(8)）。
- **碰撞处理：以 DB 唯一键为准，不做先查后插**（避免 TOCTOU）。
  插入撞 `UNIQUE` → 由调用方捕获 `IntegrityError` 并重试
  （`is_duplicate_key` 精确识别 1062 + 目标列，不误吞 FK/其他约束）。
"""
from __future__ import annotations

import secrets

# A-Z 剔除 I/O + 数字 2-9 剔除 0/1
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8
CODE_MAX_ATTEMPTS = 5


def generate_code(length: int = CODE_LENGTH) -> str:
    """生成长度为 length 的加入码（secrets.choice，密码学安全）。"""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def is_duplicate_key(exc: Exception, column: str) -> bool:
    """判断 IntegrityError 是否为指定列的 UNIQUE(1062) 冲突。

    MySQL 报错形如
    `(1062, "Duplicate entry 'ABCD1234' for key 'courses.invite_code'")`。
    只认 1062 + 列名，FK(1451/1452) 等其他约束不在此列。
    """
    msg = str(getattr(exc, "orig", exc)).lower()
    return "1062" in msg and column in msg
