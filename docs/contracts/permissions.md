# 权限矩阵与鉴权设计（思辨工坊 Web 版）

状态：**定稿 v1.0（2026-10-12，S1-8，用户审阅通过；Q1–Q3 已决）**
基线：schema_v1（角色模型）、计划书 §5.3 教师可见范围、errata E-2/E-5/E-8/E-10、sse_events.md §9（已回填方案 A）
下游：S1-7（API 契约引用本档：错误码语义、凭据方式）、S2-1（auth 落地：set_cookie）、S3-3（任务备注硬约束）

---

## 1. 目的与范围

定义**角色 × 资源 × 动作权限矩阵**（无空格）、**鉴权方式**（二选一已定，见 §6）、**授权中间件设计**，供 S1-7 API 契约与 S2/S3 全部端点实现引用。本档是"教师可见范围分层"架构决策（计划书 §5.3，禁改清单第 1 条）的可执行化。

## 2. 角色模型

- **全局角色**（`user_roles`，多角色可并存，UNIQUE(user_id, role)）：`student` / `teacher` / `admin`。
  - 无角色行的账号按 student 对待（注册默认授予 student，S2-1 落地）。
  - `admin` 为契约 5.3 预留枚举值（schema_v1 注记），MVP 无自助授予入口。
- **课程教师**：一律查 `courses.teacher_id`（course.py 注记：成员表只有学生行，course_members 无角色列）。
- **课程学生**：`course_members` 含该 user_id 的行（凭课程加入码入组）。
- **角色授予**：teacher/admin 角色由 admin 授予（S3-1 起按本行执行；MVP 可用种子数据）。

## 3. 动作词汇与 HTTP 错误码语义

动作：`create` / `read` / `list` / `update` / `join` / `upsert` / `subscribe`（SSE）/ `grant` / `archive`。

| 码 | 语义（全端点统一，S1-7 按此写错误码表） |
|---|---|
| 401 | 未登录 / Cookie 无效或过期 |
| 403 | 已登录、资源存在性已知，但动作不符——唯一例外：任务加入码错误（S3-3 验收指定 403） |
| 404 | **存在性隐藏**：越权一律 404，不暴露资源是否存在（private 会话、他人记录、未提交记录） |

依据：计划书 S3-4"未提交越权访问 → 404（不暴露存在性）"、§5.3"private → 教师/管理员一律 404"。

## 4. 权限矩阵（角色 × 资源 × 动作 × 条件）

矩阵只列**允许**项；未列出的 角色×资源×动作 组合一律 404（如学生查汇总统计、非 admin 查审计日志）。MVP 无 sessions 删除端点（E-8：S3 推荐归档替代删除）。

| 角色 | 资源 | 动作 | 条件 |
|---|---|---|---|
| 匿名 | auth/register | create | 用户名未被占用；密码 bcrypt 哈希存储 |
| 匿名 | auth/login | read | 凭据正确（错密码 401）；成功签发 JWT 写入 httpOnly Cookie |
| student | auth/me | read | 本人登录态（Cookie 有效） |
| teacher | auth/me | read | 本人登录态（Cookie 有效） |
| admin | auth/me | read | 本人登录态（Cookie 有效） |
| admin | user_roles | grant | 仅 admin 可授予 teacher/admin 角色（S3-1 起） |
| teacher | user_roles | read | 只读本人角色行；教师不得授予他人角色 |
| student | user_roles | read | 只读本人角色行；学生不得自助授予 |
| teacher | courses | create | 本人具有 teacher（教师）全局角色 |
| teacher | courses/{id} | update | courses.teacher_id = 本人；改名/归档，无删除（FK RESTRICT，E-8 同族：归档替代删除） |
| teacher | courses/{id} | read | courses.teacher_id = 本人 |
| student | courses/{id} | read | course_members 含本人（学生凭课程加入码入组） |
| teacher | courses/{id}/members | list | courses.teacher_id = 本人；成员表仅学生行 |
| student | course_members | join | 持有效课程加入码；重复加入幂等（UNIQUE(course_id,user_id)） |
| teacher | tasks | create | 本人为所属课程教师（courses.teacher_id = 本人） |
| teacher | tasks/{id} | update | 本人为所属课程教师；含 deadline/is_archived；删除走归档（E-8） |
| teacher | tasks/{id} | read | 本人为所属课程教师 |
| student | tasks/{id} | read | 任务课程的成员为主路径；join_code 仅作入组校验（§9 Q1 已决） |
| student | tasks/join | join | 持有效任务 join_code；错码 403（S3-3 验收） |
| student | sessions | create | 本人登录；visibility='task' 时 task_id 非空（E-2 应用层 validate_session_visibility） |
| student | sessions/{id} | read / update | sessions.owner_id = 本人；否则 404 |
| teacher | sessions/{id} | read | private → **一律 404**（教师也无权）；task → 任务属于本人课程即教师可见集合（进行中+完成，§5.3） |
| admin | sessions/{id} | read | 与教师同规则：private 对管理员同样 404（契约 5.3 原文"教师/管理员一律 404"） |
| student | sessions/{id}/events（SSE） | subscribe | 同本人 sessions/{id} read；建流前鉴权，失败 403（sse_events §9） |
| teacher | sessions/{id}/events（SSE） | subscribe | 同教师 sessions/{id} read（§5.3 教师可见集合）；建流前鉴权 |
| student | messages | list / read | 本人为所属会话 owner（owner_id = 本人）；否则 404 |
| teacher | messages | list / read | 随教师会话可见规则（§5.3 教师可见集合内全部消息） |
| student | revisions | create / update | 本人为所属会话 owner；默认 status='draft'（E-5） |
| teacher | revisions | read | 随教师会话可见规则（批阅练习过程） |
| student | reports | create | 本人为所属会话 owner |
| student | reports | read | 本人为所属会话 owner；多份取最新一份（无 UNIQUE） |
| teacher | reports | read | 随教师会话可见规则 |
| student | task_submissions | upsert | student_id = 本人；INSERT ON DUPLICATE KEY UPDATE（E-5：UNIQUE(task_id,student_id)） |
| student | task_submissions/{task} | read | 仅本人提交记录；他人记录 404 |
| teacher | task_submissions | list | 任务属于本人课程（教师）；**仅已提交行可见，未提交无行（S3-4 用例 404）** |
| student | feedback_forms | create / update | student_id = 本人且已加入该任务；UNIQUE(task_id, student_id) 一生一任务一份（schema_v3 表 4：学生反馈） |
| teacher | feedback_forms | read | 任务属于本人课程（教师）；反馈汇总对象为学生反馈（S3-5） |
| teacher | 汇总统计（S3-5） | read | 课程/任务属于本人课程教师 |
| teacher | graph（S4 图谱） | read | 随教师会话可见规则 |
| student | graph（S4 图谱） | read | 随本人会话可见规则（owner） |
| admin | audit_events | read | 仅 admin（预留端点；S1-3 表已建） |

## 5. 教师可见范围规则（计划书 §5.3 的可执行化）

1. `visibility='private'` → 仅 owner 可见，**教师与管理员一律 404**（本档矩阵原样执行，不做例外）。
2. `visibility='task'` → 教师可见集合 = 该任务所属课程教师的**全部 task 会话**（进行中 + 完成），无提交门槛——练习过程对教师可见（学生加入任务时 UI 明示，S3-F 页负责文案）。
3. **评分与过程解耦**：评分/汇总只基于 `task_submissions` 快照，教师评分动作不读会话实时状态。
4. 未提交的 task 会话对教师**可**见（规则 2），但**提交记录**在提交前不存在——教师提交列表无该行，按提交记录访问 → 404（S3-4 用例）。
5. 本规则列入禁改清单第 1 条，任何端点实现不得绕过；SSE 端点同规则（建流前判定）。

## 6. 鉴权方案（二选一，已评估）

### 6.1 方案对比

| 维度 | 方案 A：JWT 存 httpOnly Cookie | 方案 B：JWT 经 `?token=` 查询参数 |
|---|---|---|
| SSE 携带 | EventSource **原生**带 Cookie（同源），零处理 | 前端手动拼 URL，token 进浏览器历史/Referer/URL 日志 |
| REST 携带 | 浏览器自动；axios 同源零配置（`withCredentials` 跨源时需开） | `set_header` 返回 + 前端每次手动加 `Authorization` 或 query |
| XSS 防护 | **httpOnly，JS 读不到** | localStorage/内存持 token，XSS 即失窃 |
| CSRF 风险 | 有（缓解见 6.3） | 无 |
| 日志泄漏面 | Cookie 不进 URL 日志 | uvicorn/反代 access log、浏览器历史、错误上报全要脱敏 |
| 传输统一 | REST + SSE 同一凭据同一代码路径 | header（REST）+ query（SSE）双通道，两套校验 |
| 主动失效 | 不可（JWT 无状态，A/B 共有） | 不可（同左，非区分项） |

### 6.2 推荐：方案 A（Cookie），已定

推荐理由（含用户倾向的三条 + 本项目事实补充）：
1. **EventSource 天然带 Cookie**——SSE 是本项目一等公民（禁改清单：SSE 单向推送），方案 B 必须给 EventSource 单独开 query 通道。
2. **前端零改动**：dev 走 vite 代理（`/api` → `localhost:8000`）时浏览器视角同源，Cookie 自动携带，axios 无需任何凭据配置。
3. **httpOnly 防 XSS 读取**：JWT 存 httpOnly Cookie，页面内注入的脚本拿不到凭据；方案 B 的 token 对 JS 可见。
4. **传输统一**：一套读取逻辑（get_current_user 从 Cookie 解析）服务 REST + SSE，方案 B 是两套。
5. CSRF 是方案 A 的真实代价，但缓解到位（6.3）MVP 足够；方案 B 的 URL 日志泄漏面是**运维期持续成本**，且 token 一旦泄漏即等同凭据（无 SameSite 保护层）。

### 6.3 方案 A 技术细节（S2-1/S2-F1 按此实现）

- **登录响应**：`response.set_cookie(key="access_token", value=<JWT>, httponly=True, samesite="lax", secure=False(仅 dev，HTTPS 部署改 True), max_age=…, path="/")`——**set_cookie 而非 set_header**。
- **读取**：FastAPI 依赖从 `request.cookies["access_token"]` 解析（core/security.py 签发/验签不变，只是载体从 header 换 Cookie）。
- **dev CORS（直连跨源场景）**：`allow_origins=["http://localhost:5173"]`（**显式 origin，禁止 `*`**——浏览器拒绝在 wildcard 下携带凭据）+ `allow_credentials=True`；推荐 vite 代理走同源（代理场景不触发 CORS，此配置为直连兜底）。
- **CSRF 缓解（双防线）**：`SameSite=Lax`（现代浏览器默认）挡跨站 POST/PUT/DELETE 带 Cookie；再要求所有写操作 `Content-Type: application/json`（跨站 HTML 表单无法构造）——MVP 双防线足够，后续有需要再加 CSRF token。
- **前端**：axios 同源零配置；跨源场景 `withCredentials: true`（S2-F1 client.ts 注释注明）。

### 6.4 方案 B 技术细节（未采纳，留档供对比）

- S2-1：登录响应 `set_header` 返回 token（body 或 Authorization），前端存内存/localStorage。
- SSE：前端手动拼 `?token=`；**URL 日志脱敏要求**：uvicorn access log 对 `token=` 参数替换为 `token=***`（自定义 formatter 或对该路径关闭 access log）、反代（如有）同步处理、前端错误上报剥离 query。
- CORS：同样显式 origin + `allow_credentials`（若 REST 走 header 则 header 需列入 allow_headers）。

## 7. 连带影响与回填清单（S1-8 定稿时一并执行）

| 对象 | 动作 |
|---|---|
| sse_events.md §9 | ✅ 已回填"方案 A：Cookie 会话（S1-8 定稿）" |
| errata.md E-10 | ✅ 已写入：S2-1 验收句 `Authorization: Bearer` → cookie jar 携带 |
| S1-7 api.md | 所有端点凭据 = Cookie；**不引用 Authorization 头**；错误码表按本档 §3 |
| S2-1 | `set_cookie`（6.3）；core/security.py 签发逻辑不变 |
| S2-F1 client.ts | 同源零配置注明；跨源兜底 withCredentials 注释 |

## 8. 授权中间件设计（S2 落地蓝图）

依赖链三层，全部**在业务逻辑之前**执行：

1. `get_current_user`：读 Cookie → 验签（过期/伪造 401）→ 取 user + 角色集。
2. `require_role(...)`：端点声明最低角色（如 `require_role("teacher")`）——不符且资源存在性已知 403。
3. **资源级判定函数**（应用层，E-2 风格）：`can_read_session(user, session)` / `can_list_task_submissions(user, task)` 等——内部执行 §5 规则，失败抛 **404**（存在性隐藏）。SSE 端点在**建流前**完成 1–3（sse_events §9：鉴权失败不产生 error 事件）。

约束：判定函数是唯一入口，端点 handler 不得内联写 role 判断（防规则漂移）；每类资源的越权用例进 S2/S3 测试。

## 9. 决议与遗留硬约束（2026-10-12 用户审阅定稿）

| # | 问题 | 决议 |
|---|---|---|
| Q1 | 学生"已加入任务"的持久化判据（schema 无任务成员表） | **已决**：任务读取权限 = 课程成员（course_members）为主路径，join_code 仅作入组校验。**硬约束（已写入计划书 S3-3 任务备注）**：若 S3-3 实现时发现需要持久成员记录（如教师查看哪些学生已加入但未提交），停下提 schema 增量（新 migration + 新表 task_members），不在 S3 实现里顺手加表 |
| Q2 | E-10 是否随 S1-8 写入 errata | **已决**：写入 ✅ |
| Q3 | admin 预留行是否保留 | **已决**：保留（条件列注明预留语义） |

## 10. 验收锚点（S1-8 本档）

- [x] `grep -c "教师" docs/contracts/permissions.md` ≥ 10
- [x] 矩阵每行四列（角色/资源/动作/条件）无空单元格、无空行
- [x] 鉴权方式二选一已定（非含糊表述）：方案 A Cookie，§6.2
- [x] §7 回填清单五对象齐全（sse §9 / E-10 / S1-7 / S2-1 / S2-F1）
- [x] 教师可见范围 §5 与计划书 §5.3 逐条对应

## 11. 交接说明（S1-8 完成后，供接手 S1-7 的模型阅读）

**当前进度（2026-10-12）**
- 已完成并 commit：S1-1～S1-5（ORM 轨，schema_v1/v2/v3 **FINAL**，commit 1091ae8/4f8c3bd/c29ab7f）、S1-6（sse_events.md **v1.0 定稿** + errata E-9，commit e10abe9）、S1-8（本档 permissions.md **v1.0** + errata E-10 + sse §9 回填）。
- 测试基线：`pytest` 60 passed（模型 12 张 + 一致性测试三轮 + 表级 charset）；conftest 已切换 alembic upgrade head（sfb_test）。
- 未做契约：**S1-7 api.md（下一步）**、S1-9a rubric、S1-10 页面原型、S1-11 旧 JSON 导入。

**S1-8 鉴权决定（S1-7 必须遵守）**
- 方案 A：JWT 存 **httpOnly Cookie**（set_cookie，SameSite=Lax）；REST 与 SSE 同一凭据。
- REST **不引用 Authorization 头**；SSE 走 Cookie（sse_events §9 已回填方案 A）。
- 错误码语义固定：401 未登录 / 403 存在性已知但不符（唯一例外 join_code 错码）/ **404 越权存在性隐藏**。

**S1-7 必须遵守的约束**
1. 验收命令：`grep -c "^\| \`" docs/contracts/api.md` ≥ 25（每端点一行）；每端点含方法/路径/入参/出参/错误码。
2. 端点范围参考计划书文件清单：auth、sessions、messages（回放/历史）、tasks/courses/submissions、revisions、reports、graph、teacher 汇总、SSE（引用 sse_events.md，不重复定义）。
3. 凭据与错误码按本档 §3/§6/§7；教师可见范围按本档 §5（private → 教师 404 是硬规则）。
4. 提交 upsert（E-5）、visibility 应用层校验（E-2）、消息 seq 方案 A（E-1）、SSE 事件引用 sse_events.md 不复制。
5. 提交规范不变：`[S1-7] docs: …`；验收跑过才 commit；不 push；逐份停下确认。

**新模型接手前，请先复述以下三点确认上下文：**

1. S1-8 的鉴权方案是 A（Cookie）
2. S1-7 的验收命令是 grep -c '^| \`' docs/contracts/api.md ≥ 25
3. 教师可见范围硬规则：private → 教师 404，task → 课程教师可见集合

如果新模型能准确复述，说明上下文接手成功。
