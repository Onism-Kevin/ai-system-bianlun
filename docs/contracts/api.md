# API 契约（思辨工坊 Web 版）

状态：**定稿 v1.2（2026-10-13，S1-10，用户审阅通过：G1 补登 POST /api/sessions/{id}/messages 漏收端点 + G2 补登反思端点；sessions 表 reflection 列为 2026-10-13 增量）**
基线：permissions.md v1.0（§3 错误码 / §4 矩阵 / §5 教师可见 / §6 鉴权方案 A）、sse_events.md v1.0（冲突处以 sse_events.md 为准，用户指令）、errata E-1/E-2/E-3/E-5/E-8/E-9/E-10/E-11/E-12、schema_v1 FINAL / schema_v2 FINAL-2026-10-13（reflection 增量）/ schema_v3 FINAL、计划书任务卡 S2-1~S2-13、S3-2~S3-5、S4-2/S4-4。
验收命令：`grep -c '^| \`' docs/contracts/api.md` ≥ 25（每端点一行）。

---

## 0. 全局约定

- **Base URL**：`http://localhost:8000/api`（dev；前端走 vite 代理同源转发）。
- **凭据**：**仅 httpOnly Cookie**（登录响应 `set_cookie`）。**全契约不引用 Authorization 头**（errata E-10：计划书 S2-1 验收句的 `Bearer` 已被取代，验收三连改 `curl -c/-b cookie.txt`）。跨 REST 与 SSE 同一凭据。
- **统一错误体**：`{"detail": "<人类可读一句话>"}`（FastAPI 默认；前端文案经 error_map.py 映射，S2-13）。
- **状态码语义**（permissions §3）：401 未登录/Cookie 无效；403 存在性已知但不符（例外：加入码错误，E-12）；**404 越权存在性隐藏**（private 会话、他人记录、未提交记录一律 404）；409 资源状态冲突（重名、暂停态错位）；422 入参校验失败；410 任务已过期；502/504 模型层故障（同步端点，permissions §3 已补行）。
- **教师可见范围**（permissions §5，禁改清单第 1 条）：private → 教师/管理员 404；task → 课程教师可见集合（进行中+完成，无提交门槛）。
- **静态资源**：`/static/` 前缀由 FastAPI StaticFiles 挂载（S2 配置 `app.mount("/static", ...)`）；词云 PNG 走此路径（见 wordcloud 端点），静态资源**不走 Cookie 鉴权**（无敏感内容；如词云改敏感则转鉴权资源另议）。
- **时间格式**：ISO 8601（DATETIME 列直出，`created_at`/`updated_at`）。
- **列表端点**：MVP 不分页（班级规模数据量）；S5 压测后再定分页契约。messages 端点的 `limit?` 是**单次最大返回条数**（防一次性拉全部历史），不是分页参数；列表端点仍不分页。
- **矩阵兜底**：未列出的 角色×资源×动作 组合一律 404（permissions §4）。

## 1. 端点总表

| 方法 | 路径 | 入参 | 出参 | 错误码 | 依据/errata |
|---|---|---|---|---|---|
| `POST` | `/api/auth/register` | `{username, password}` | 201 `{id, username, roles[]}`³ | 409 重名；422 校验 | S2-1；permissions §4（bcrypt 存储） |
| `POST` | `/api/auth/login` | `{username, password}` | 200 `{user}` + `set_cookie(httpOnly, SameSite=Lax)` | 401 凭据错；422 | S2-1；permissions §6.3；E-10 |
| `GET` | `/api/auth/me` | —（Cookie） | 200 `{user, roles[]}` | 401 | S2-1/S3-1；E-10（取代计划书 Authorization 验收句） |
| `POST` | `/api/sessions` | `{topic, mode="debate", max_turns=1, visibility="private", task_id=null}`¹ | 201 `{id, status}`³ | 401；422 topic 空/超长或 visibility 违反 E-2 | S2-2/S2-3；E-2（validate_session_visibility） |
| `GET` | `/api/sessions/{id}` | — | 200 `{id, topic, visibility, task_id, status, created_at, updated_at}` | 401；404 越权（private→教师 404） | permissions §5 |
| `PATCH` | `/api/sessions/{id}` | `{topic?, visibility?, task_id?}`（**status 不可 patch**——状态机独占，S2-2） | 200 `{session}` | 401；403 非 owner；422 E-2 违反；404 | E-2 |
| `POST` | `/api/sessions/{id}/pause` | — | 200 `{status:"paused"}`；SSE 侧同步收到 `speech_end(paused_truncated)` | 401；403 非 owner；404；409 非 generating | S2-6；E-3 |
| `POST` | `/api/sessions/{id}/resume` | — | 200 `{status:"generating"}`；SSE 重发 `speech_start`（同 seq）续写 | 同上（非 paused → 409） | S2-6；sse_events §5.3 |
| `POST` | `/api/sessions/{id}/restart` | — | 200 `{id, status:"waiting"}`（重开：状态复位，经状态机合法转移，非 PATCH；消息处置由 S2-F6 实现定） | 401；403 非 owner；404；409 generating 中（先暂停） | S2-F6 重开按钮；S2-2 状态机 |
| `POST` | `/api/sessions/{id}/quick` | — | 200 `{id, status}`（加速：当前消息立即定稿推进，SSE 侧随即 `speech_end(complete)`，顺序保证不变；暂停态语义见脚注 4）⁴ | 401；403 非 owner；404；409 非 generating | S2-F6 加速按钮；sse_events §3 |
| `POST` | `/api/sessions/{id}/messages` | `{content}`（学生输入） | 201 `{seq, created_at}`（新消息 seq，前端本地渲染用） | 401；403 非 owner；404；409 非 waiting | 方案 §9（漏收补登，v1.2）；**行为**：同步写 messages 表（`role='user'`，seq 自增 E-1）→ 异步触发状态机 waiting→generating → 通过 SSE 推送下一轮 AI 生成；**用户消息由前端本地渲染，不走 SSE 回显**（用户 2026-10-13 裁定，多标签页一致性 MVP 可接受；SSE 事件表本就不含 user_message 事件，见 sse_events.md §4） |
| `POST` | `/api/sessions/{id}/reflection` | `{content}`（反思文本） | 200 `{updated_at}`（保存/更新：单会话单文本，UPDATE sessions.reflection 同一列） | 401；403 非 owner；404；422 空/超长 | G2 裁定（用户 2026-10-13，方案 a2）；schema_v2 sessions.reflection TEXT NULL（2026-10-13 增量 migration）；报告 prompt 读取输入（S2-10） |
| `GET` | `/api/sessions/{id}/reflection` | — | 200 `{content, updated_at}`（未填写时 content=null，**不 404**——404 在本契约=越权存在性隐藏，空反思非越权；报告 prompt 按无反思分支处理，同 notes §6 第 6 条模式） | 401；403 非 owner；404 | G2 裁定（同上）；报告生成前置输入（notes §6 第 7 条） |
| `GET` | `/api/sessions/{id}/messages` | query `after_seq=0`；`limit?` | 200 `{messages:[{seq, role, agent_role, content, status, created_at}], next_seq}` | 401；404 | E-1（seq 即 message id）；E-3（status 三态）；E-5（agent_role ∈ pro/con/judge/coach） |
| `GET` | `/api/messages/{seq}` | — | 200 `{message}`（单条，供图谱原文定位反查） | 401；404 | E-1；S4-4 |
| `GET` | `/api/history` | — | 200 `[{id, topic, status, created_at, updated_at}]`（owner 视角；列表归 history.py，sessions.py 不提供列表防双入口） | 401 | S2-12 |
| `GET` | `/api/history/{session_id}` | — | 200 `{session, messages:[按 seq 升序]}`（详情完整重建消息流） | 401；404 | S2-12 |
| `GET` | `/api/sessions/{id}/events` | query `after_seq=0` | `text/event-stream`（事件表/心跳/回放/重连**全部**见 sse_events.md，不在此重复定义） | 建流前按 §3：401 未登录/Cookie 无效；404 会话不存在或 private 越权；403 已存在但角色不符；流中 error 事件（sse §6） | S2-4/S2-5；sse_events.md（E-9 取代 S2-4"每事件 id"验收句） |
| `POST` | `/api/sessions/{id}/explore` | 无 body（读会话 topic） | 200 `{concepts[], scope, subquestions[], stakeholders[]}`（ExploreOut 独立 schema） | 401；404；422 空 topic / 超 5000 字 | S2-7 验收；§4-1 裁定（ExploreOut，非 DecomposeOut） |
| `POST` | `/api/sessions/{id}/analyze` | 无 body | 200 `{nodes:[{id, type∈claim/evidence/rebuttal, text, source_ref:{message_seq, quote}}], edges:[{source, target, relation∈{支持,反驳,补充,依赖,限制,需要证据}}]}` | 401；404；422 | S2-8 验收 + S2-F5 引用跳转；schema 扩展见 E-11 |
| `POST` | `/api/sessions/{id}/coach_turn` | `{mode:"coach"\|"rebuttal"}` | 200 `{question, focus, hints[], quote_refs:[{seq, quote}]}`（追问含学生原文引用） | 401；404；422 | S2-9 验收；schema 扩展见 E-11 |
| `GET` | `/api/sessions/{id}/wordcloud` | — | 200 `{url:"/static/wordclouds/session_{id}.png"}`；未生成 → 404 | 401；404 | sse_events §5.6（URL 形态由本契约定：`/static/wordclouds/`；SSE 事件之外的补查入口） |
| `POST` | `/api/sessions/{id}/reports` | 无 body | 201 `{report}`（同步生成；长耗时，前端经 SSE `report_progress/ready` 跟进，UI 硬约束 S2-F7） | 401；403 非 owner；404；502/504 模型故障 | S2-10；E-5（无 UNIQUE，重跑=新行） |
| `GET` | `/api/sessions/{id}/reports` | — | 200 `{report}`（created_at 最新一份） | 401；404 无报告 | S2-F7/S3-5 |
| `GET` | `/api/reports/{id}` | — | 200 `{id, session_id, rubric_version, scores{四维}, overall_score, summary_text, sections[], created_at}`（正文结构遵循 ReviewReport，stage_outputs.py §4） | 401；404 | S2-10（四维量表+依据+建议三段） |
| `POST` | `/api/revisions` | `{session_id, content, status="draft"}` | 201 `{id, version, status, diff:null}`（初稿 version=1；修改稿自动 version+1） | 401；403 非 owner；404 会话无权 | S2-11；E-5（status draft/final） |
| `PATCH` | `/api/revisions/{id}` | `{content?, status?}` | 200 `{revision, diff_vs_prev}`（草稿自动保存入口） | 401；403；404 | S2-11 |
| `GET` | `/api/revisions` | query `session_id` | 200 `[{id, version, status, content, created_at, diff_vs_prev}]`（diff=相对上一版 unified diff，首版 null） | 401；404 | S2-11 验收（2 版本 + diff 字段） |
| `GET` | `/api/revisions/{id}` | — | 200 `{revision, diff_vs_prev}` | 401；404 | S2-11 |
| `POST` | `/api/courses` | `{name, description?, term?}` | 201 `{id, name, invite_code, …}`（invite_code 服务端生成 6~8 位 A-Z0-9 剔 I/O/0/1） | 401；403 非 teacher 角色 | S3-2；course.py 注记 |
| `GET` | `/api/courses` | — | 200 `[{course}]`（teacher→本人教的；student→已加入的） | 401 | S3-2；permissions §4 |
| `GET` | `/api/courses/{id}` | — | 200 `{course}`（invite_code 仅课程教师响应保留，学生响应剔除） | 401；404 | permissions §4 |
| `PATCH` | `/api/courses/{id}` | `{name?, description?, term?, is_archived?}` | 200 `{course}`（MVP 无删除端点；删带任务课程被 FK RESTRICT 拒） | 401；403 非 teacher_id；404 | S3-2；E-8 |
| `GET` | `/api/courses/{id}/members` | — | 200 `[{user_id, username, joined_at}]`（**仅学生行**，course_members 无教师行） | 401；403/404 非课程教师 | permissions §2/§4 |
| `POST` | `/api/courses/join` | `{invite_code}` | 200 `{course_id}`（幂等：重复加入仍 200） | 401；**403 错码**² | S3-2；E-12（对称化） |
| `POST` | `/api/courses/{course_id}/tasks` | `{title, material?, deadline?, need_join_code?}` | 201 `{id, title, join_code, …}`（need_join_code 时服务端生成 String(8)） | 401；403 非课程教师；404 | S3-3；permissions §4 |
| `GET` | `/api/courses/{course_id}/tasks` | — | 200 `[{task}]`（教师→本人课程任务；学生→成员课程全部任务） | 401；404 | permissions §4 |
| `GET` | `/api/tasks/{id}` | — | 200 `{task}`（join_code 仅课程教师响应保留） | 401；404 非课程成员 | S3-3；§9 Q1 已决（课程成员为主路径） |
| `PATCH` | `/api/tasks/{id}` | `{title?, material?, deadline?, is_archived?}` | 200 `{task}`（删除走归档） | 401；403 非课程教师；404 | E-8（CASCADE 连带删除风险，归档替代） |
| `POST` | `/api/tasks/{id}/join` | `{join_code}` | 200 `{course_id, task_id}`（幂等） | 401；403 错码（S3-3 验收指定；E-12 对称化）；410 已过期 | S3-3 验收 |
| `POST` | `/api/tasks/{task_id}/submissions` | `{session_id}` | 200 `{id, session_id, submitted_at, replaced:boolean}`（**upsert**：UNIQUE(task_id,student_id)，重复/换会话重做=更新旧行；旧会话 visibility 处置见 S3-4 备注） | 401；404 会话非 owner / 非课程成员（存在性隐藏） | E-5 补充 2（必须 upsert）；S3-4 |
| `GET` | `/api/tasks/{task_id}/submissions` | — | 200 `[{student_id, session_id, submitted_at}]`（教师：**仅已提交行**，未提交无行） | 401；403 非课程教师；404 | permissions §4；S3-4 |
| `GET` | `/api/tasks/{task_id}/submissions/me` | — | 200 `{submission}`；未提交 → 404（不暴露存在性） | 401；404 | S5-1 越权/缺失用例 |
| `POST` | `/api/tasks/{task_id}/feedback` | `{scores, comment}` | 200 `{id}`（**upsert**：UNIQUE(task_id,student_id)，一生一任务一份；学生反馈） | 401；404 未提交该任务 / 非课程成员 | schema_v3 表 4；permissions §4（选项 A） |
| `GET` | `/api/tasks/{task_id}/feedback` | — | 200 `[{student_id, scores, comment, created_at}]`（教师读；S3-5 汇总对象） | 401；403 非课程教师；404 | permissions §4 |
| `GET` | `/api/courses/{course_id}/summary` | query `task_id?` | 200 `{submitted_count, total_students, top_pending_verification:[{text, count}]}`（提交数/常见待核实项 Top5） | 401；403 非课程教师；404 | S3-5；permissions §4 |
| `POST` | `/api/sessions/{session_id}/graph` | 无 body | 201 `{graph_id}`（抽取落库 argument_nodes/edges/evidence_sources） | 401；403 非 owner；404；502/504 模型故障 | S4-1/S4-2 |
| `GET` | `/api/sessions/{session_id}/graph` | — | 200 `{nodes:[{id, text, type, source_ref:{message_seq, quote}, verified}], edges:[{source, target, relation∈{支持,反驳,补充,依赖,限制,需要证据}, verified}]}`（verified=false 即"待核实"，S4-3） | 401；404 未抽取/越权 | S4-4（source_ref 反查消息走 `/api/messages/{seq}`） |
| `GET` | `/api/graphs/{graph_id}` | — | 200 `{同上}` | 401；404 | 计划书文件清单（graph.py 双入口） |
| `GET` | `/api/health` | — | 200 `{mysql:"ok"\|"down", model_gateway:"ok"\|"degraded"\|"down"}`（**降级也 200**，状态在 body；匿名可读，前端徽标 S2-F9；Ollama 已在 S1-3b 被 model_gateway 替换） | 无鉴权 | S2-13；permissions §4（匿名行已增补） |

**脚注**
1. `mode`/`max_turns` 为**运行参数**（S2-2/S2-3 验收入参），不落 sessions 表（表无此列）；存储形态（编排器内存 or JSON 列）属 S2-2 实现决策，本契约只约束 API 面与默认值。
2. 课程/任务 join 错码均为 **403**（对称化，errata E-12；用户 2026-10-12 裁定）。
3. 计划书 S2-1/S2-3 验收句写 `200 {user}` / `200 {id}`，以本契约为准：register 与 sessions create 均为 **201**（与 courses/tasks/revisions 对齐，用户 2026-10-12 裁定）。
4. **quick 在暂停态（paused）下的语义留白**：S2-6 实现时定——可选 409（要求先 resume）或自动 resume + quick；两种选择都符合本契约的 409 行（以实现时裁定为准，届时回填本脚注）。

## 2. SSE 端点

`GET /api/sessions/{id}/events`（owner/教师可见集合内，建流前完成三层鉴权：401 未登录/Cookie 无效、404 会话不存在或 private 越权、403 已存在但角色不符——按 permissions §3，**不产生 error 事件**）。
传输层（text/event-stream、心跳、retry）、10 类事件、id: 行规则（E-9：仅 speech_* 写 seq）、回放（after_seq / Last-Event-ID + snapshot）、暂停不关流、重连退避、done 唯一终态——**全部以 docs/contracts/sse_events.md 为准**，本契约不重复定义。

## 3. 错误码细则（permissions §3 的 API 面展开）

- 404 存在性隐藏的三类典型：private 会话对教师、他人记录（messages/revisions/reports 越权）、未提交记录（submissions/me）。
- 403 全契约合法出现的两类：①已知资源 + 角色/归属不符（如学生 PATCH 教师任务）；②**加入码错误（课程/任务 join 对称化，E-12）**。
- 422 校验失败：pydantic 入参校验 + E-2 应用层 visibility 校验 + explore 空 topic/超 5000 字。
- 409：注册重名、pause 非 generating、resume 非 paused、restart 于 generating 中、quick 非 generating、messages 提交于非 waiting（状态机错位，S2-2 转移表；messages 行 v1.2 补登）。
- 410：任务 join 已过 deadline（S3-3 验收）。
- **502/504**（permissions §3 已补行，方案 A）：模型层故障在同步端点的映射——**502 = 上游模型服务错误**（ModelServerError / StructuredValidationError 等 5xx 类）、**504 = 上游模型超时**（ModelTimeoutError / httpx.ReadTimeout）；ModelConnectionError（模型网关停机）映射 **502**。流式路径不走 HTTP 状态码，映射 error 事件（sse §6，fatal 列）。

## 4. 差异裁定记录（2026-10-12 用户拍板，六项全部落定）

1. **explore 出参**：S2-7 使用**独立 schema ExploreOut**（concepts/scope/subquestions/stakeholders）；`DecomposeOut` 保持 spike/mini-bench 用途不动。两者用途不同，schema 归属 S2-7 实现。
2. **analyze 出参**：`ArgumentMap` **扩展**——edge 增 `relation∈{支持,反驳,补充,依赖,限制,需要证据}`（与 S4 图谱契约共用中文枚举）、node 增 `source_ref:{message_seq, quote}` → **errata E-11**。
3. **coach_turn 出参**：`CoachTurn` 扩展增 `quote_refs:[{seq, quote}]` → **errata E-11**（与 2 合并）。
4. **health 匿名**：permissions §4 已增补"匿名 | health | read | 无（探针）"。
5. **加入码错误码**：对称化到 **403**（课程 join 404→403）→ **errata E-12**；permissions §3 例外条款已同步改"加入码错误（课程/任务 join）"。
6. **S2-4 验收句**"每事件 id 递增整数"已被 E-9 取代（仅 speech_* 写 id: = 消息 seq）——本契约 §1 events 行按 sse_events.md 写（用户指令：冲突以 sse_events.md 为准），备案维持。

## 5. 验收锚点（S1-7 本档 + S1-10 v1.2 补登）

- [x] `grep -c '^| \`' docs/contracts/api.md` ≥ 25（修订后实测 50 行，2026-10-13；v1.2 补登 3 行）
- [x] 端点覆盖：auth 3 / sessions 7→10（v1.1 声称"sessions 8"是笔误，总表实际 7 行；v1.2 补登 messages + reflection×2 共 3 行；含 pause/resume/restart/quick/messages/reflection）/ messages 2 / history 2 / SSE 1 / stage 3 / wordcloud 1 / reports 3 / revisions 4 / courses 6 / tasks 5 / submissions 3 / feedback 2 / summary 1 / graph 3 / health 1（合计 50）
- [x] `Authorization` 仅出现在否定/备案语境（§0 否定声明、§1 auth/me 行的 E-10 取代说明、§4-6 备案），无任何"携带 Authorization 头"的正向要求
- [x] 每端点行含错误码 + 依据/errata 列，无空单元格
- [x] §4 六项裁定已全部落地（E-11/E-12 入 errata，permissions.md 两处同步修改）
- [x] v1.2 补登（2026-10-13，S1-10，用户审阅通过）：G1 `POST /api/sessions/{id}/messages`（方案 §9 漏收补登；用户消息前端本地渲染、不走 SSE）；G2 `POST/GET /api/sessions/{id}/reflection`（sessions.reflection 列，schema_v2 2026-10-13 增量 + 第二次 migration 一致性测试通过）
