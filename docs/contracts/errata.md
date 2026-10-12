# 契约勘误记录（errata）

> 本文件集中记录对《思辨工坊执行计划书 v1.1》契约的**勘误与取代声明**。
> v1.1 原文是已确认的历史文档，**不改写**；冲突处以本文件 + 对应 schema 草案为准。
> 每条注明日期与拍板人（用户，2026-10-12，两份草案审阅回复）。

## E-1 契约 5.1：messages.seq 语义 → 方案 A（取代）

- **原文问题**：契约 5.1 一边写"seq BIGINT AUTO_INCREMENT PRIMARY KEY"，
  一边注"主键为独立 id"，两句矛盾；且 MySQL 每表只允许一个 AUTO_INCREMENT 列，
  "id 自增 PK + seq 全局自增"不可能同时成立。
- **取代为（方案 A）**：`seq` BIGINT AUTO_INCREMENT **即主键**，无独立 id 列；
  API 对外 message id = seq；`UNIQUE(session_id, seq)` 复合索引保留
  （方案 A 下唯一性已蕴含，索引用途是回放查询覆盖索引）。
- **单调性正确表述**：seq 全局分配、各会话交错（A 得 1,3,5；B 得 2,4），
  会话内单调由"全局单调序列的子序列仍单调"保证，
  回放 `WHERE session_id=? AND seq>? ORDER BY seq` 严格正确；
  **不是**"每会话从 1 开始"、**不是**"会话 A 占 1-10 连续段"。
- 落地细节见 `schema_v2_tasks.md` 焦点二、`schema_v3_messages.md` 表 1。

## E-2 契约 5.3：visibility 约束 → 应用层强制（取代）

- **原文**：契约 5.3 写 `CHECK 约束：visibility='task' AND task_id IS NULL 或 …`。
- **取代为**：DB 层**不加 CHECK**；由应用层校验函数强制
  （`visibility='task' ⇔ task_id 非空`）。理由：DB CHECK 报错信息对用户不友好；
  将来加第三态（如 public）要 ALTER 改表；"task_id 指向的任务存在且未归档"
  本来就必须应用层查，两层写一半反而误导。
- **事实澄清**：MySQL 8.4.9（本项目实测版）CHECK 语法可用（8.0.16+），
  "不支持"不是否决理由，纯权衡 1/2 条。
- **连带勘误**：计划书 v1.0 S1-3 验收句"`visibility='task' AND task_id IS NULL`
  插入被拒"改为"应用层 `validate_session_visibility()` 拒绝该组合"（见 E-4）。

## E-3 契约 5.4：messages.status 枚举统一（取代）

- **原文问题**：契约 5.2 定义 `paused_truncated`，5.4 重连示例写 `status='generating'`，不统一。
- **取代为**：三值枚举 `streaming`（生成中）/ `complete`（正常完成）/
  `paused_truncated`（暂停截断）；5.4 示例中的 `generating` 一律读作 `streaming`。
- **适用范围（2026-10-12 补）**：本勘误**仅适用于 `messages.status`**；
  `sessions.status` 保留五态（waiting/generating/paused/finished/failed，见 S2-2），
  其中的 generating 是会话层"模型生成中"状态，与本勘误无关，不改。

## E-4 计划书 v1.0 验收句勘误（已就地更新计划书）

- S1-3 验收："`visibility='task' AND task_id IS NULL` 插入被拒"
  → "应用层校验函数拒绝该组合（DB 无 CHECK，见 E-2）"。
- S1-3 任务行："visibility CHECK 生效" → "visibility 应用层校验函数生效"。
- S1-5 表数勘误：14 → **15** 张（v1.1 追加 task_submissions 漏改计数；用户此前已确认）。

## E-5 对 v1.1 的增量补充（非取代，用户 2026-10-12 拍板）

| 变更 | 内容 | 理由 |
|---|---|---|
| messages 新增列 | `agent_role` VARCHAR(16) NULL，值 `pro`/`con`/`judge`/`coach`/NULL；user/system 消息为 NULL | assistant 至少三类角色；前端按角色渲染、S4 图谱按来源区分、S2-9 区分"教练 vs 辩论对手"都需要；高频查询字段不进 detail JSON |
| tasks 新增列 | `deadline` DATETIME NULL、`is_archived` TINYINT(1) DEFAULT 0 | 教学常用；MVP 无删任务 API，归档防将来返工 |
| task_submissions 新增唯一键 | `UNIQUE(task_id, student_id)` | 防换会话反复提交；**连带 S3-4 任务备注**：提交 API 必须 upsert（`INSERT … ON DUPLICATE KEY UPDATE session_id=?, submitted_at=?` 或先删后插），见计划书 S3-4 段 |
| task_submissions 否决列 | ~~score / teacher_comment~~ | 未被要求的人工评分不发明 |
| sessions 否决列 | ~~冗余分数列~~ | 列表契约只要求状态/时间 |
| revisions 新增列 | `status` ENUM('draft','final') DEFAULT 'draft' | S4 要复用定稿观点作对比 |
| reports 否决约束 | ~~UNIQUE(session_id)~~ | 允许重跑复盘取最新一份 |
| audit_events 新增列 | `ip` VARCHAR(45) NULL | 登录留痕常见最低要求 |

## E-6 实现层教训：MySQL ENUM 违规抛 DataError(1265) 不是 IntegrityError

- **事实（S1-4 实测，commit 442d465）**：pymysql 下向 ENUM 列写入非法值
  （如 `messages.role='coach'`、`messages.status='generating'`）抛
  `pymysql.err.DataError (1265, "Data truncated for column '…' at row 1")`，
  映射为 `sqlalchemy.exc.DataError`；**不是** `IntegrityError`（1062 Duplicate entry 才是）。
- **连带影响**：S2-2/S2-3/S2-13 的错误处理若只 `except IntegrityError` 会漏掉枚举违规。
  错误分类映射（S2-13 `backend/app/services/error_map.py`）必须同时捕获
  `DataError`（→用户输入非法值/服务端枚举不一致，4xx 或服务端 bug 5xx）与
  `IntegrityError`（唯一键/外键约束，区分 1062 重复提交与 1451/1452 引用错误）。
- **依据来源**：pytest 全量回归中 4 个失败用例定位（test_message.py 两处枚举拒绝用例）。

## E-7 updated_at 由应用层 onupdate 维护，DB 层无 ON UPDATE CURRENT_TIMESTAMP

- **决策（用户，2026-10-12，S1-5 migration 审阅）**：所有表的 `updated_at`
  只由应用层 SQLAlchemy `onupdate` 维护，DB 层**不加**
  `ON UPDATE CURRENT_TIMESTAMP`。
- **理由**：全系统走 ORM，单一来源；Alembic 对比干净（无方言子句噪声）；
  避免 DB 层在绕过 ORM 的写入时静默改值。
- **约束（未来开发必须遵守）**：绕过 ORM 的 UPDATE（原生 SQL、运维脚本、
  导入工具）**不会刷新** `updated_at`。未来若出现此类写路径，
  需要补 `server_onupdate` + 手改 migration。
