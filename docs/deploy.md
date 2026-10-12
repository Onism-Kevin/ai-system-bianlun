# 思辨工坊 · 部署文档初稿（S0-11）

> 版本：v0.1（S0 阶段初稿，随 S1～S2 逐步补齐）
> 最后更新：2026-10-12

## 1. 环境要求

| 组件 | 版本/形态 | 说明 |
|---|---|---|
| OS | Windows 10/11 | 当前开发与部署均为 Windows |
| Python | 3.14（`C:\Users\Kevin\AppData\Local\Programs\Python\Python314\python.exe`） | **不要**用 mingw/MSYS2 自带 Python |
| venv | `backend\venv` | 用上述原生 Python 建；已验证 `import fastapi/sqlalchemy` 正常 |
| MySQL | 8.4.9（服务名 `MySQL84`） | datadir 在 `D:\MySQL\Data`，配置 `D:\MySQL\my.ini` |
| Node/pnpm | pnpm + create-vite | 仅 frontend 构建需要 |
| 模型网关 | OpenAI 兼容，`http://127.0.0.1:8326/v1` | 生产键名/密钥见 `backend/.env` |

## 2. 目录与配置

1. 代码根目录：`D:\LLM\AISystemBianlunn`
2. 复制 `backend\.env.example` → `backend\.env`，填五键：
   - `MODEL_BASE_URL`（网关 /v1 地址）
   - `MODEL_API_KEY`（真实 key 只放 `.env`，已 gitignore）
   - `MODEL_DEFAULT`（当前 `cline/deepseek/deepseek-v4-pro`）
   - `DATABASE_URL`（密码含特殊字符必须 percent-encode，如 `@`→`%40`）
   - `JWT_SECRET`
3. **`.ps1` 脚本必须以 UTF-8 带 BOM 保存**：PowerShell 5.1 对无 BOM 脚本按 GBK 解码，会乱码并可能抛致命解析错误（详见 `docs/backup_drill.md`）。

## 3. 数据库初始化

```powershell
# 建三 schema（幂等，已实测连跑两遍均 OK）：sfb_dev / sfb_test / sfb_demo，utf8mb4_unicode_ci
powershell -ExecutionPolicy Bypass -File backend\scripts\mysql-root.ps1 -e "source backend\scripts\create_schemas.sql"
# 预期输出：sfb_demo / sfb_dev / sfb_test 三行，均为 utf8mb4 / utf8mb4_unicode_ci
```

> 注意：不要用 `Get-Content ... | mysql-root.ps1` 管道喂 SQL —— 包装脚本走的是 `@args` 透传，管道 stdin 不会到达 mysql。SQL 文件一律用上面的 `source` 方式。

带凭据的通用查询入口（从 `.env` 取密码，无需手输）：

```powershell
.\backend\scripts\mysql-root.ps1 sfb_dev -e "SELECT 1;"
```

> 注意：`mysql.exe` 直接调用时若不带 `-u`，会退回内置 `ODBC` 用户报 `ERROR 1045`；`my.ini` 的 `[client]` 段没有 user/password。请统一走 `mysql-root.ps1`。

## 4. 启动

```powershell
# backend（S0 阶段仅 /api/health 骨架，业务路由随 S2 挂载）
backend\venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8000
# 健康检查：GET http://127.0.0.1:8000/api/health → {"status":"ok"}

# frontend
cd frontend; pnpm install; pnpm dev
```

## 5. 演示预案（演示前快照 + 一条恢复命令）

演示数据库固定用 `sfb_demo`，绝不用 `sfb_dev`。

**演示前（T-30min）打快照：**

```powershell
powershell -ExecutionPolicy Bypass -File backend\scripts\backup.ps1 -Database sfb_demo
# 产出 backend\scripts\backups\sfb_demo_<时间戳>.dump，记下该路径
```

**演示中若数据被搞乱 → 一条命令回滚：**

```powershell
powershell -ExecutionPolicy Bypass -File backend\scripts\restore.ps1 -DumpFile "<演示前的 dump 路径>" -TargetDatabase sfb_demo
# 内部三步：DROP+重建 utf8mb4 → 选定库导入 → 核对表行数
```

**回滚后核对：**

```powershell
.\backend\scripts\mysql-root.ps1 sfb_demo -e "SELECT COUNT(*) FROM <主表>;"
```

以上链路已于 2026-10-12 在 `sfb_test` 完成一次真实演练：备份前 5 行 → 删除 → 恢复 → 恢复后 5 行，判据一致（见 `docs/backup_drill.md`）。

## 6. 已知限制与待补（S1+）

- backend 目前只有 `/api/health`，ORM/路由/鉴权随 S1/S2 落地后本节要补建表与迁移说明。
- `restore.ps1` 步骤 3 用 `information_schema.TABLE_ROWS` 是 InnoDB 估算值，仅作参考；**验收判据一律用真实 `COUNT(*)`**。
- push 到 GitHub 在当前沙箱环境报 `couldn't create signal pipe`，由用户在本机终端执行。
- 备份产物 `backend/scripts/backups/` 不入库（gitignore 已排除）。
