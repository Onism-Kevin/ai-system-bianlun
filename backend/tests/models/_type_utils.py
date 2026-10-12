"""MySQL 方言反射 ↔ ORM 类型归一化工具（S1-5 抽出，consistency 测试及后续加表测试复用）。

背景：SQLAlchemy ORM 类型对象与 MySQL 反射类型对象存在多组"同义不同名/同义不同形"，
直接比对会报假差异（归档见 docs/deploy.md §6 开发注意）：

- **NUMERIC ≡ DECIMAL**：ORM `Numeric(5,2)` 用 MySQL 方言编译成 DDL 文本是
  `NUMERIC(5,2)`，但 migration 建出的列反射回来是 `DECIMAL(5,2)`——同一列两个类型名；
- **BOOL ≡ BOOLEAN ≡ TINYINT(1)**（display_width=1）；
- **INT ≡ INTEGER**，且整型带显示宽度 `INT(11)`（宽度无语义，剥掉）；
- VARCHAR/TEXT 反射带**列级 COLLATE 子句**（ORM 侧靠表级 mysql_collate，列上没有）→ 剥掉再比；
- DEFAULT：反射带引号（`'0'` ↔ ORM `text('0')`）；`CURRENT_TIMESTAMP` 可能带精度括号 `(6)` → 都归一；
- ENUM 类型名 MySQL 不存储，只比值；值顺序敏感，调用方按元组逐位比对（不排序不转集合）。

用法：双方类型对象各自过 `canon_type()` 折算成规范串再比；默认值过
`canon_default()`/`orm_default()`；约束/索引名过 `strip_op_f()`。
"""
from __future__ import annotations

import re

from sqlalchemy.dialects import mysql
from sqlalchemy.sql import TextClause

MYSQL_DIALECT = mysql.dialect()


def strip_op_f(name: str | None) -> str | None:
    """坑 4：剥 op.f('...') / quoted 名外壳，还原纯约束/索引名。"""
    if name is None:
        return None
    m = re.fullmatch(r'op\.f\(\s*[\'"](.+?)[\'"]\s*\)', name)
    if m:
        return m.group(1)
    return name.strip('"`')


def compile_type(type_) -> str:
    """类型 → MySQL 方言 DDL 文本（泛型 String/Boolean 也会被方言正确渲染）。"""
    return str(type_.compile(dialect=MYSQL_DIALECT))


def canon_type(type_) -> str:
    """坑 1/坑 2 的类型归一化。

    - 剥列级 COLLATE 子句（反射带 collation，ORM 侧靠表级 mysql_collate，列上没有）；
    - BOOL / BOOLEAN / TINYINT / TINYINT(1) → BOOLEAN（本 schema 布尔列即 TINYINT(1)）；
    - 整型剥显示宽度：INT(11) → INT；BIGINT → BIGINT（宽度不参与语义）；
    - DATETIME(n) → DATETIME；VARCHAR(n) 保留 n（长度是契约的一部分）；
    - NUMERIC ≡ DECIMAL（MySQL 同义：ORM Numeric 编译成 NUMERIC，反射成 DECIMAL）；
    - ENUM 只折算成 ENUM（值由调用方按元组逐位比对）。
    """
    s = compile_type(type_).upper().strip()
    s = re.sub(r"\s+COLLATE\s+\S+", "", s)
    s = re.sub(r"\s+", "", s)
    if "ENUM" in s:
        return "ENUM"
    if s.startswith(("BOOL", "TINYINT")):
        return "BOOLEAN"
    m = re.match(r"^(BIGINT|MEDIUMINT|SMALLINT|INT|INTEGER)(\(.*\))?(UNSIGNED)?$", s)
    if m:
        base = m.group(1)
        return "INT" if base in ("INT", "INTEGER") else base
    s = re.sub(r"^(DECIMAL|NUMERIC)\((\d+)\s*,\s*(\d+)\)$", r"DECIMAL(\2,\3)", s)
    s = re.sub(r"^(DATETIME|TIMESTAMP|TIME)\(\d+\)$", r"\1", s)
    return s


def canon_default(value) -> str | None:
    """坑 3 + 默认值引号归一化：CURRENT_TIMESTAMP(6)→CURRENT_TIMESTAMP、'1'→1、'draft'→DRAFT。"""
    if value is None:
        return None
    s = str(value).strip()
    if isinstance(value, TextClause):
        s = value.text.strip()
    s = re.sub(r"^CURRENT_TIMESTAMP\(\d*\)$", "CURRENT_TIMESTAMP", s, flags=re.I)
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        s = s[1:-1]
    return s.upper()


def orm_default(col) -> str | None:
    """ORM 列的 server_default 归一化（无默认返回 None）。"""
    sd = col.server_default
    if sd is None:
        return None
    return canon_default(sd.arg)
