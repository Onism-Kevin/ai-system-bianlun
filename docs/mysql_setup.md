# MySQL 部署形态探测与建议（S0-0 产出）

- 探测时间：2026-10-10
- 探测方式：只读探测（`where`/`Get-Service`/`netstat`/`Get-Command`/路径与环境变量检查），**未安装任何东西，未改动系统状态**
- 用途：决定思辨工坊 dev/test/demo 三环境的 MySQL 落地方式（对应计划书 S0-8 及其后所有 DB 任务）

## 一、当前状态

| 探测项 | 命令 | 结果 |
|---|---|---|
| mysql 客户端 | `where.exe mysql` | 未找到（NOT FOUND） |
| MySQL 服务 | `Get-Service *mysql*` | 无（NO SERVICE） |
| 3306 端口监听 | `netstat -ano \| findstr :3306` | 无监听（NOTHING LISTENING） |
| Docker | `Get-Command docker` | 未安装（DOCKER NOT INSTALLED） |
| winget | `Get-Command winget` | 可用（`...\WindowsApps\winget.exe`） |
| 常见安装目录 | `C:\Program Files\MySQL`、`C:\mysql`、`C:\xampp\mysql` 等 | 均不存在 |
| `MYSQL_HOME` / PATH | 环境变量检查 | 未设置；机器 PATH 无 mysql 条目 |

**结论：本机当前完全没有 MySQL（客户端、服务、端口监听、Docker 容器、常见残留目录全无）。**

## 二、推荐方案

**推荐：Windows 原生安装 MySQL 8.0 社区版**（通过 winget）。

- 命令：`winget install --id Oracle.MySQL -e`
- 理由：
  1. 本机没有 Docker，为一个库引入 Docker Desktop 不划算，也违背"最小可运行依赖"。
  2. 字符集/InnoDB 由计划书 S0-9 的建库脚本（`create_schemas.sql`）显式强制 `utf8mb4`/`InnoDB`，不依赖安装默认值，因此用哪种方式安装对后续 schema 无影响——选最省事的原生安装。
  3. winget 已可用，一条命令即可，且便于后续脚本化（backup.ps1 / restore.ps1 直接调 `mysql`/`mysqldump`）。
- 备选（不推荐）：MSI 安装包手动装；或先装 Docker Desktop 再用容器（多一步、收益低）。
- 安装后需要做的（由 S0-9/S0-10 负责，不属本任务）：建 `sfb_dev`/`sfb_test`/`sfb_demo` 三 schema、utf8mb4、备份恢复演练。

## 三、需用户操作

**待你操作（在 S0-8 之前完成，否则 S0-8 及其后 DB 任务标 `[blocked]`）：**

1. **授权/执行安装**：本项目已获授权在 S0-8 起执行 `winget install --id Oracle.MySQL -e`；若你希望我代装，请在进入 S0-8 时确认；若你自装，装完告诉我。
2. **设置 root 密码**：安装完成后 root 密码由你设置。
3. **告知连接方式**：安装完成后按提示回复"MySQL 已装，请设置 root 密码并告知连接方式"，并提供连接串要素（host/port/user/password），用于拼 `DATABASE_URL`（形如 `mysql+pymysql://user:pass@127.0.0.1:3306/sfb_dev?charset=utf8mb4`）。
4. **确认可用版本**：计划书按 MySQL 8.0 排；若你装的是 5.7，请提前告知（影响 `utf8mb4` 默认排序规则与 CHECK 约束语法的处理）。

> 红线提醒：本任务（S0-0）只探测与写文档。安装动作统一放到 S0-8 及之后，且需你在此处确认的连接方式可用。
