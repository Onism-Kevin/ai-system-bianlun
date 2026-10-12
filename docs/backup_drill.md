# S0-10 备份/恢复演练报告

- **日期**：2026-10-12
- **范围**：仅 `sfb_test`（演练全程未触碰 `sfb_dev`，符合"不能拿真实 dev 库做演练"约束）
- **结论**：**通过** —— 备份前 `COUNT(*)` = 恢复后 `COUNT(*)` = 5

## 演练步骤与实际输出

| 步骤 | 操作 | 结果 |
|---|---|---|
| ① | `CREATE TABLE drill_marker` + 插入 5 行（row-1..row-5） | OK |
| ② | 备份前计数 `SELECT COUNT(*) AS before_count` | **5** |
| ③ | `backend/scripts/backup.ps1 -Database sfb_test` | 产出 `backend/scripts/backups/sfb_test_20261012_124147.dump`（2135 bytes，50 行） |
| ④ | `DELETE FROM drill_marker` 后计数 | **0** |
| ⑤ | `backend/scripts/restore.ps1 -DumpFile <dump> -TargetDatabase sfb_test` | 步骤 1/2/3 全 OK：DROP → CREATE utf8mb4 → 导入 → 核对 `drill_marker` 5 行 |
| ⑥ | 恢复后计数 `SELECT COUNT(*) AS after_restore` | **5** |

判据（② == ⑥）成立：5 == 5。

## 演练中发现并修复的两个问题

### 1. PowerShell 脚本缺 UTF-8 BOM（用户发现，已修复）

**现象**：`restore.ps1` 在你的终端报
`字符串缺少终止符: "`（`ParserError: TerminatorExpectedAtEndOfString`，restore.ps1:57），且 backup/restore 的中文输出全部乱码（`澶囦唤鐩爣` = "备份目标"）。

**根因**：三个 `.ps1` 保存为 **UTF-8 无 BOM**。Windows PowerShell 5.1 对无 BOM 脚本按系统 ANSI（GBK）解码：
- 中文字符串被 GBK 错误解码 → 输出乱码；
- `restore.ps1:57` 的某个中文多字节字符在 GBK 下吞掉了行尾的闭合引号 → 解析器认为字符串未终止 → **脚本根本没运行**，所以 `after_restore=0`（④ 删除后的残留，不是恢复失败）。

**修复**：`backup.ps1`、`restore.ps1`、`mysql-root.ps1` 全部转为 **UTF-8 带 BOM**（`[System.IO.File]::WriteAllText` + `UTF8Encoding($true)`），并用 `[System.Management.Automation.Language.Parser]::ParseFile` 逐个校验零解析错误。

> 教训：本仓库所有 `.ps1` 必须以 UTF-8 **带 BOM** 保存，否则 PowerShell 5.1 会用 GBK 解码并可能产生致命解析错误。纯 ASCII 的脚本不受影响。

### 2. `mysql.exe` 无 `-u` 时报 ERROR 1045 ODBC（已封装规避）

**现象**：直接用 `mysql.exe --defaults-file="D:\MySQL\my.ini"` 连接报
`ERROR 1045 (28000): Access denied for user 'ODBC'@'localhost' (using password: NO)`。

**根因**：`D:\MySQL\my.ini` 的 `[client]` 段只声明了 `port=3306`，**没有 user/password**。Windows 上 `mysql.exe` 未显式 `-u` 时会退回内置的 `ODBC` 默认用户去连，服务端自然拒绝。

**修复/规避**：新增 `backend/scripts/mysql-root.ps1` —— 从 `backend/.env` 的 `DATABASE_URL` 解析出密码（percent-decode），以 `-u root` 显式连接并透传所有参数给 `mysql.exe`，密码不回显、不落盘。实测 `SELECT CURRENT_USER()` = `root@localhost`。

## 脚本清单（均已入库）

- `backend/scripts/backup.ps1`：`mysqldump` 逻辑备份；`--single-transaction --routines --triggers --events --no-tablespaces`；**不带** `--databases`（dump 只含表结构+数据，不含 `CREATE DATABASE`/`USE`）；库名唯一来源 = 显式 `-Database` 参数（默认 `sfb_test`），绝不从 URL 覆盖；输出 `<OutDir>\<db>_<yyyyMMdd_HHmmss>.dump`。
- `backend/scripts/restore.ps1`：三步 = DROP 后重建目标库（utf8mb4，与 S0-9 建库规则一致）→ 选定库后 `source` 导入（避免无 `USE` 时报 "No database selected"）→ `information_schema.TABLES` 核对表行数。
- `backend/scripts/mysql-root.ps1`：带凭据的 `mysql.exe` 包装器（见上）。

备份产物目录 `backend/scripts/backups/` 已在 `.gitignore` 排除，不入库。

## 演练数据清理

`drill_marker` 表仅存在于 `sfb_test`，属演练残留，可随时 `DROP TABLE`；`sfb_dev` 未受影响。
