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

## E-8 sessions.task_id ON DELETE CASCADE 的产品后果（S3 显式处理）

- **事实**：`sessions.task_id → tasks.id ON DELETE CASCADE`（v2 定稿）。
  删任务会**连带清除**学生在该任务下的所有练习会话及其
  消息（messages）、观点版本（revisions）、复盘报告（reports）、
  提交记录（task_submissions）——级联链：tasks → sessions → messages/reports/revisions/task_submissions。
- **决策（用户，2026-10-12，S1-5 migration 审阅）**：DB 级联保持 CASCADE
  （技术上防孤儿），但 **S3 若开放删任务 API，必须在 UI 层明确警告**
  该后果；**推荐改用 `tasks.is_archived` 归档而非删除**。
- **理由**：schema_v2 定稿时接受 CASCADE 是"防孤儿"的技术判断，
  但产品后果（删任务 = 删学生练习记录）要在 S3 显式处理，
  不能等实现时才发现。
- **连带**：S3 任务管理 API 的验收应包含"删除路径的警告文案或归档替代"。

## E-9 计划书 S2-4 验收句"每事件 id: 递增整数" → "每消息 id: 递增整数"（取代）

- **原文问题**：S2-4 验收句"每事件 SSE `id:` 为递增整数"与 SSE 事件契约
  （docs/contracts/sse_events.md §3）冲突：契约下同一消息的所有 delta 共享
  同一 seq，delta 级 id 不存在。
- **取代为**：计划书 S2-4 验收句"每事件 id: 递增整数"应读作
  "**每消息** id: 递增整数"。理由：E-1 方案 A 的 DB 回放粒度是整条消息
  （`WHERE session_id=? AND seq>?`），同一消息的所有 delta 共享同一 seq。
  以 sse_events.md §3 为准。
- **日期/拍板人**：用户，2026-10-12（S1-6 草案审阅）。

## E-10 计划书 S2-1 验收句的凭据载体：Authorization 头 → Cookie（取代）

- **原文问题**：S2-1 验收句 `curl -H "Authorization: Bearer $T" $API/me → 200`
  假定 JWT 经 Authorization 头携带，与 S1-8 定稿的鉴权方案 A
  （JWT 存 httpOnly Cookie，docs/contracts/permissions.md §6.2）冲突。
- **取代为**：S2-1 验收三连（注册 → 登录 → me）改用 cookie jar 携带：
  登录响应 `set_cookie`（`curl -c cookie.txt` 存），后续请求 `curl -b cookie.txt`
  自动携带；错密码 → 401 语义不变。验收命令的三连语义与期望结果不变。
- **连带**：S1-7 API 契约不引用 Authorization 头；sse_events.md §9 已回填
  方案 A；S2-F1 axios 同源零配置（跨源兜底 withCredentials）。
- **日期/拍板人**：用户，2026-10-12（S1-8 审阅）。

## E-11 stage_outputs schema 修订（analyze/coach）：edge.type→relation 取代 + 字段增补

- **原文问题**：S0-5 `backend/app/schemas/stage_outputs.py` 的 `ArgumentMap`
  （edge.type∈support/attack，无 source_ref）与 S2-8 验收
  （edge.relation∈{支持,反驳,补充,依赖,限制,需要证据} + 节点 source_ref；S2-F5 引用跳转依赖 source_ref）冲突；
  `CoachTurn`（question/focus/hints）缺 S2-9 验收要求的"针对学生原文的引用"字段。
- **取代为**：**edge.type 字段被 edge.relation 取代**——字段名 + 枚举值全变，两字段**不并存**
  （勿理解为并存的扩展）；新 edge 字段 `relation` 取中文六枚举
  {支持,反驳,补充,依赖,限制,需要证据}（**与 S4 图谱契约共用同一枚举**，S4-2/S4-4 同源）；
  node 侧为纯增字段 `source_ref:{message_seq, quote}`。
  `CoachTurn` 增 `quote_refs:[{seq, quote}]`。`DecomposeOut` 保持不变（spike/mini-bench 用途）；
  explore 端点使用独立 schema `ExploreOut`（concepts/scope/subquestions/stakeholders，S1-7 用户裁定）。
- **范围**：仅 Pydantic schema 与 API 出参；不动 S0-3b mini-bench 已验证的 prompts 字段契约。
- **日期/拍板人**：用户，2026-10-12（S1-7 审阅）。

## E-12 加入码错误码对称化：课程 join 错码 404 → 403

- **原文问题**：permissions.md §3 原文"403 唯一例外：任务加入码错误"，导致课程 join
  （`POST /api/courses/join`）错码按兜底走 404，与任务 join（403，S3-3 验收指定）不对称，
  前端提示语义分裂。
- **取代为**：两个 join 端点（`POST /api/courses/join`、`POST /api/tasks/{id}/join`）错码一律 **403**；
  permissions §3 例外条款改为"加入码错误（课程/任务 join）"。无效码不暴露存在性细节
  （错误体 detail 只说"加入码无效"，不区分"码不存在/已失效"）。
- **日期/拍板人**：用户，2026-10-12（S1-7 审阅）。

## E-13 audit_events 的模型版本/错误/耗时/重试记录：进 detail JSON（非新增列）

- **背景**：方案 §10 audit_events 描述"记录模型版本、错误、耗时和重试"，schema_v3
  表 5 无对应专用列。
- **取代为**：四项均进 `detail` JSON（S3-1 实现时按需写入），不加专用列。方案 §10
  要求的是"记录"未规定列结构；JSON 免锁死字段增删（同 reports.scores 哲学）。敏感
  数据（密码/密钥）永不入此列。
- **日期/拍板人**：用户，2026-10-13（S1 收口一致性检查）。

## E-14 计划书 S2-3 验收句的 seq 语义修正（E-9 漏网的同类句）

- **原文问题**：S2-3 三处表述与 E-1 冲突——验收句（v1.0:243）期望"`SELECT seq FROM
  messages WHERE session_id=?` → 1..N 连续无空洞"，完成信号/任务行（v1.1:196、
  v1.0:68）写"messages 表 seq 连续"——均与全局交错机制冲突：单会话 seq 是全局单调
  序列的子序列，不从 1 开始且不连续（空库 + 唯一会话恰好成立，有历史数据即挂）。
  E-9 只取代了 S2-4 的同类验收句，漏了 S2-3。
- **取代为**：三处（任务表行 v1.0:68 与 v1.1:196、验收句 v1.0:243）均改为"seq 在会话内
  单调（全局交错，会话内为子序列）"，并已就地更新（同 E-4 就地更新模式）。
- **日期/拍板人**：用户，2026-10-13（S1 收口一致性检查）。

## E-15 permissions §5 显式加 owner 优先级（纯澄清，不改既有语义）

- **背景**：permissions.md §5 规则 1 写"`private` → 仅 owner 可见，教师与管理员一律
  404"；矩阵 §4 的 sessions/{id} 行（owner 检查）与教师行（private→404）在
  **"教师本人 owner 的 private 会话"**（教师个人训练页）上表面冲突，§5 未显式规定
  优先级。consistency_check 维度 5（:66）已定语义"教师个人训练页=教师 owner 私有
  会话，由 owner 规则覆盖"，但那是检查文档内部记录，不是契约本身。
- **澄清为**：`can_read_session` 判定优先级——**owner_id=本人时无论角色可见**
  （教师个人训练页走这条）；非 owner 才应用角色规则（private→教师/管理员 404；
  task→课程教师可见集合）。纯澄清，不改既有语义（与 §5 规则 1/2 字面一致，
  只是把隐含优先级写明）。同步在 permissions.md §5 增补 §5.6。
- **落地约束**：S2-2 及后续 sessions 端点实现按此优先级，注释引用
  consistency_check:66 + permissions:63/64。
- **日期/拍板人**：用户，2026-10-13（S2-1 收口审阅）。

## E-17 api.md:30 PATCH /api/sessions/{id} 出参 {session} → 平铺（取代）

- **原文问题**：api.md 契约自身不一致——GET /api/sessions/{id}（:29）返回平铺
  七字段 `{id, topic, visibility, task_id, status, created_at, updated_at}`，
  PATCH（:30）却写 `200 {session}` 包裹。同一个 session 对象不该有两种出参结构，
  前端需为两套结构各写一份序列化。
- **取代为**：PATCH 200 出参**平铺**，与 GET 同构——"api.md:30 的 {session} 应为
  平铺，与 GET /api/sessions/{id} 同构。PATCH 返回更新后的 session 对象，语义上
  应与 GET 一致。"
- **落地**：S2-3 `backend/app/schemas/session.py` 删 SessionPatchResponse 包裹层；
  `backend/app/api/sessions.py` update_session 直接返回 SessionOut；
  `backend/tests/api/test_sessions.py` 出参断言改平铺七字段。
- **日期/拍板人**：用户，2026-10-14（S2-3 审阅回复，追问 1）。

## E-18 S2-2/S2-3/S2-4 任务内容重分配记录（备案，非取代）

- **实际实现**：
  - S2-2 = 状态机基座 + can_read_session（state_machine.py 五态转移表 +
    全矩阵穷举测试；can_read_session owner 优先级）；
  - S2-3 = sessions 端点（POST 创建 / GET 详情 / PATCH 修改，api.md:28-30）；
  - S2-4 = SSE 端点 + 编排器 + messages 落库。
- **偏差理由**：状态机先于端点（依赖方向：端点消费状态机而非相反）；
  编排器依赖 SSE（并入 S2-4 减少往返）。**计划书 v1.1:196 的 S2-3 描述
  （"训练编排器 debate_runner.py 自由辩论 + messages 落库"）按本勘误理解：
  编排器部分归 S2-4。**
- **连带**：S2-3 另含 task 归属校验（跨用户引用 → 404，存在性隐藏，permissions §3；
  用户 2026-10-14 追问 2 裁定）——归属判定 = 课程教师本人或课程成员
  （course_members，S3-3 join API 填充）。
- **日期/拍板人**：用户，2026-10-14（S2-3 审阅回复，问题 1 + 追问 2）。

## E-19 api.md:42 events 端点 403 无触发路径（纯澄清，不改既有语义）

- **原文问题**：api.md:42 `GET /api/sessions/{id}/events` 错误码列写"401 未登录/
  Cookie 无效；404 会话不存在或 private 越权；403 已存在但角色不符；流中 error
  事件（sse §6）"，其中 403 与 S2-3 GET 分层口径（读路径全 404，存在性隐藏）
  不一致，events 读路径无触发 403 的场景。
- **澄清为**："api.md:42 的 403 在 events 端点无触发路径，与 S2-3 GET 分层口径
  一致。读操作 can_read_session 通过即订阅，不通过即 404。"（保留 api.md:42
  字面不改写，以本勘误为准；同 E-15 纯澄清模式。）
- **连带**：410（任务已过 deadline）不在 events 端点出现——读历史/事件流不受
  任务过期影响。若 S3 要控制"过期任务不能继续训练"，那是 POST messages 的
  检查，不是 events 的。
- **落地**：S2-4 events 端点实现：can_read_session 不过 → 404；无 403 分支。
- **日期/拍板人**：用户，2026-10-14（S2-4 设计纲要审阅，Q4 裁定）。
