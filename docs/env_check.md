# MySQL 环境核对（S0-8 产出）

- 核对时间：2026-10-10（首检）；**2026-10-11 复核（见第五节）**
- 探测方式：只读查询（`SHOW DATABASES` / `SHOW VARIABLES`），未改动任何数据

## 五、2026-10-11 复核（S0-8 正式记录）— ✅ 已解除阻塞，认证与建库均通过

| 项 | 结果 | 证据 |
|---|---|---|
| `mysql --version` | ✅ **Ver 8.4.9** for Win64 on x86_64 (Community Server - GPL) | `mysql.exe --version` |
| root 可达性 | ✅ **通过**：`root@localhost`，`SELECT VERSION(), CURRENT_USER()` 返回 `8.4.9 / root@localhost` | 用户终端 + `AUTH_OK` 探测 |
| 服务端口 | ✅ **3306**（`--defaults-file=D:\MySQL\my.ini`，datadir `D:/MySQL/Data`） | `netstat` / `sc qc MySQL84` |
| 三库可达 | ✅ **sfb_dev / sfb_test / sfb_demo 全部创建成功** | `SHOW DATABASES` 返回三库 |
| 字符集 | ✅ 三库 `DEFAULT_CHARACTER_SET=utf8mb4`，`COLLATION=utf8mb4_unicode_ci` | `information_schema.SCHEMATA` |
| 认证插件 | root 走 `caching_sha2_password`（`mysql.user` 核对） | `SELECT user,host,plugin` |

> **关键澄清（修正历史误判）**：此前 5 轮 `ERROR 1045` 的根因是 **`backend/.env` 里存的是旧密码**，不是"无密码可连的另一台实例"。用户重置 root 密码并更新 `.env` 后，用同一个 `DATABASE_URL` 直连即返回 `AUTH_OK`。随后发现真正的阻塞其实是 **`1049 Unknown database 'sfb_dev'`**（全新实例只有系统四库）——现已由本次 S0-9 建库消除。
>
> **密码存放约定**：真实密码只在 `backend/.env`；本文档与所有汇报/commit 均不回显密码值（禁止行为第 14 条）。

**尝试记录（均未 echo 任何密码值）**：
1. `mysql -u root -h 127.0.0.1 -P 3306`（无密码）→ 1045 Access denied（using password: NO）
2. `--defaults-extra-file`（密码取自 `backend/.env` 的 `DATABASE_URL`）→ 1045（using password: YES）
3. `-u root -h 127.0.0.1 "-p<env_pwd>"` → 1045（using password: YES）
4. `-u root -h localhost "-p<env_pwd>"`（本地套接字）→ 1045
5. `-u root --protocol=SOCKET` → `ERROR 2047: Wrong or unknown protocol`（Windows 版不支持该套接字协议）

**实例定位（2026-10-11 补查）**：本机只有一个 mysqld（独占 3306/33060），即 `MySQL84` 服务，用**自定义配置**启动：
`"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqld.exe" --defaults-file="D:\MySQL\my.ini" MySQL84`
- datadir = `D:\MySQL\Data`（**不是**默认 `C:\ProgramData\MySQL\...`），`C:\ProgramData` 下无 my.ini / Data。
- 服务运行账号 `NT AUTHORITY\NetworkService`；`Get-CimInstance Win32_Service` 拒绝访问（沙箱/权限），改用 `sc qc MySQL84` + 注册表 `ImagePath` 定位成功。
- 该实例走 `caching_sha2_password`（非 `mysql_native_password`），客户端需支持该插件（PyMySQL ≥1.0 已支持）。

**最终结论（2026-10-11 晚）**：阻塞已全部解除，S0-8 与 S0-9 完成。
- 历史 5 轮 `ERROR 1045` 的真实根因 = **`backend/.env` 里存的是旧密码**；用户重置 root 密码并同步 `.env` 后，用同一 `DATABASE_URL` 直连即 `AUTH_OK`。
- 修好密码后暴露出真正的阻塞其实是 **`1049 Unknown database 'sfb_dev'`**（全新实例仅有系统四库）。
- 已建齐三库并核对字符集（见上表），S0-9 完成；S0-8 由 `[blocked]` → ✅。

## 一、当前状态（核对结果）

| 项 | 值 | 证据命令 |
|---|---|---|
| MySQL 版本 | **8.4.9**（Community Server, Win64 x86_64） | `mysql --version` → `Ver 8.4.9 for Win64` |
| 服务名 | MySQL84 | `Get-Service MySQL84` → **Running** |
| 端口 | 3306 | `SELECT @@port` → 3306 |
| 服务端字符集 | **utf8mb4** | `@@character_set_server` → utf8mb4 |
| 排序规则 | utf8mb4_0900_ai_ci | `@@collation_server` |
| 安装路径 | `C:\Program Files\MySQL\MySQL Server 8.4` | — |
| root 可达性 | ✅ 可连（host=127.0.0.1, port=3306） | 成功返回查询结果 |
| 已有 schema | `sfb_dev` / `sfb_test` / `sfb_demo`（业务三库，S0-9 已建，utf8mb4）＋ 系统库 `information_schema` / `mysql` / `performance_schema` / `sys` | `SHOW DATABASES` |

### ⚠️ 已知环境问题（非阻塞，需注意）

1. **`mysql` 不在本会话进程 PATH**：用户级 PATH 已更新，但当前 PowerShell 进程是旧的，直接敲 `mysql` 报 CommandNotFound。本任务改用绝对路径 `C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe` 探测成功。**S0-9/S0-10 的 SQL/脚本会用绝对路径或在新终端执行**，不依赖继承 PATH。
2. **`character_set_client/connection/results = gbk`**：这是 Windows 控制台默认编码，**不影响服务端存储**（`character_set_server`/`character_set_database` 均为 utf8mb4）。中文写入业务库不受影响；但若通过命令行导入含中文的 .sql，建议加 `--default-character-set=utf8mb4` 避免客户端层转码。

## 二、推荐方案（供 S0-9/S0-10 沿用）

沿用 v1.1 已定稿的三 schema 方案，本节只补"连接串正确写法"：

**`DATABASE_URL`（关键：密码含 `@` 必须编码为 `%40`）**

用户提供的原始要素：`root` / `<ROOT_PASSWORD>`（含特殊字符 `@`）/ `127.0.0.1:3306` / db=`sfb_dev`。**真实密码只存在你手填的 `backend/.env`，任何提交物一律用占位符。**

⚠️ **关键坑：密码含 `@` 时不能直接拼进 URL**——URL 里第一个 `@` 会被当作"userinfo 与 host 的分隔符"，导致 pymysql 把 host 误解析而连接失败。密码中的 `@` 必须 percent-encode 成 `%40`：

```env
# 正确（dev）
DATABASE_URL=mysql+pymysql://root:<ROOT_PASSWORD_ENCODED>@127.0.0.1:3306/sfb_dev?charset=utf8mb4
# 正确（test / demo，S0-9 建库后替换 db 名）
DATABASE_URL=mysql+pymysql://root:<ROOT_PASSWORD_ENCODED>@127.0.0.1:3306/sfb_test?charset=utf8mb4
DATABASE_URL=mysql+pymysql://root:<ROOT_PASSWORD_ENCODED>@127.0.0.1:3306/sfb_demo?charset=utf8mb4
```

- pymysql 内部会解码 `%40` → `@`，认证不受影响。
- `<ROOT_PASSWORD_ENCODED>` = 你的真实 root 密码把其中每个 `@` 换成 `%40` 后的字符串；填进 `.env` 时按此规则改写。
- 若换一个不含 `@` 的 root 密码，可省去编码（更省心，但非必须）。
- 三个 schema 均显式 `utf8mb4` / `InnoDB`（S0-9 的 `create_schemas.sql` 强制），不依赖安装默认值。

## 三、需用户操作

- **本任务（S0-8）无需你操作**——连通性、版本、字符集、root 可达性均已核对通过。
- 后续若我把 `mysql` 绝对路径固化进 `backup.ps1`/`restore.ps1`（S0-10），仅作脚本内部默认值，不改你的环境；如你希望脚本改用 PATH 中的 `mysql`（需新开终端生效），告诉我即可。

## 四、连接串备忘（不含明文密码）

- 真实 `DATABASE_URL` 只写进 `backend/.env`（gitignore，不提交）。
- root 密码明文仅存在于：你的输入、`.env`、本机进程环境变量。**不写进任何提交物/日志/文档**（禁止行为第 14 条）。
