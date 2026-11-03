# S3 开工前置检查（第 0 步）

> 状态：**待用户审阅**（本文件完成后停下，确认后再开 S3-1）
> 检查人：编程 agent（lead）
> 日期：2026-11-03
> 基线：api.md v1.2（50 端点）/ permissions.md v1.0 / errata E-1~E-28 /
> schema_v1/v2/v3 FINAL / S2 收口总结
> 依据：`docs/s2_closure_summary.md`、`docs/consistency_check_s2_2026-11-02.md`

---

## 0. 检查方法与证据来源

- 逐任务列出 S3 依赖端点（按用户第 0 步清单），对照四列：
  **api.md 行 / backend 实现 / permissions §4 矩阵行 / 错误码列**。
- 实现判定：`grep '@router\.(get|post|patch|put|delete)' backend/app/api/*.py` →
  **28 个路由**（与 S2 收口口径一致）。
- 表结构判定：`backend/alembic/versions/*.py` 的 `op.create_table(` → **12 张表**。
- 测试基线：`backend/venv/Scripts/python.exe -m pytest -rA` →
  **376 passed, 151 warnings in 322.81s（exit 0）**；
  `--collect-only` → **376 tests collected**。

---

## 1. 八点复述（确认上下文接手成功）

1. **鉴权方案 A（Cookie）**：JWT 存 httpOnly Cookie（`access_token`，SameSite=Lax），
   REST 与 SSE 同一凭据；契约不引用 `Authorization` 头（E-10）。
   代码：`backend/app/api/deps.py:get_current_user` 读 `Cookie(alias="access_token")`；
   `auth.py:110-127` `set_cookie`。
2. **教师可见范围**：`visibility='private'` → 教师/管理员一律 **404**（存在性隐藏）；
   `visibility='task'` → 课程教师可见集合（进行中+完成，无提交门槛）。
   代码：`deps.py:can_read_session`（owner 优先级 E-15 / permissions §5.6）。
3. **课程教师一律查 `courses.teacher_id`**：`course_members` 只有学生行，无教师行、
   无角色列（schema_v1 §4.2 / schema_v2 教师可见性注记）。
4. **两级加入码**：`courses.invite_code` 课程级、`tasks.join_code` 任务级，
   两者错误码均 **403**（E-12 对称化；permissions §3 例外条款）。
5. **`task_submissions` 有 `UNIQUE(task_id, student_id)`**：提交 API 必须 **upsert**
   （E-5 补充 2 / schema_v2 表 2 / 计划书 S3-4 备注）。
6. **`sessions.task_id ON DELETE CASCADE`**：删任务会连带删学生练习会话
   （messages/revisions/reports/task_submissions 级联）；S3 推荐
   `tasks.is_archived` 归档而非删除（E-8）。
7. **S3-4 的 submissions 端点 S2 未实现（T-3）**，S3 要从零实现
   （`backend/app/api/` 无 `submissions.py`，grep 无命中）。
8. **S2 收口三条教训**：
   a. 说"已修/已覆盖/与 X 同款"必须贴代码/测试名/文件内容；
   b. 数字先数再写，不凭记忆；
   c. 契约定了但没分配任务的问题，开工前先扫。

---

## 2. 已读文件清单（按用户指定顺序）

| # | 文件 | 关键行/要点 |
|---|---|---|
| 1 | `思辨工坊执行计划书 v1.1.md`（项目根） | S3 段（:210）只写"与 v1.0 完全一致"，**无 S3 任务卡表** |
| 1b | `思辨工坊执行计划书.md`（v1.0，项目根） | S3-1~S3-6/S3-F1~F4 任务卡在 :94-107；S3-3/S3-4 验收 :330-342 |
| 2 | `docs/s2_closure_summary.md` | 28 端点 / 376 测试 / 遗留项 #1=submissions |
| 3 | `docs/consistency_check_s2_2026-11-02.md` | #5 已知未实现（messages/{seq}、wordcloud）、#6 T-3 submissions |
| 4 | `docs/contracts/api.md` | courses/tasks/submissions/feedback/summary = **:54-70** |
| 5 | `docs/contracts/permissions.md` | §4 矩阵；courses :51-56、tasks :57-61、task_submissions :80-82、feedback_forms :83-84、summary :85、user_roles :48-50 |
| 6 | `docs/contracts/errata.md` | E-1/E-2/E-5/E-8/E-10/E-12/E-15 等全量 |
| 7 | `docs/contracts/schema_v1.md` | users/user_roles/courses/course_members |
| 8 | `docs/contracts/schema_v2_tasks.md` | tasks/task_submissions/sessions（含 UNIQUE 双键、CASCADE） |
| 9 | `docs/contracts/schema_v3_messages.md` | feedback_forms 表 4（UNIQUE(task_id,student_id)） |
| 10 | `backend/app/api/*.py` | 28 端点；无 courses/tasks/submissions/teacher |
| 11 | `backend/app/models/*.py` | 12 张表 ORM 齐备（含 Course/Task/TaskSubmission/FeedbackForm） |
| 12 | `frontend/src/views/DashboardView.vue` | 教师视角骨架，课程/加入仍假数据（:235-250） |
| 13 | `frontend/src/router/index.ts` | 7 条路由（/,/login,/dashboard,/training,/review,/graph,/history），**无教师路由** |

---

## 3. 逐任务依赖端点对照表

> 实现列：✅ 已实现 / ❌ 未实现。
> 矩阵列：✅ 有行 / ⚠️ 无显式行 / ❌ 无行。
> 错误码列：✅ 已定义 / ⚠️ 定义不全。

### S3-1 角色管理 API（teacher 授予 / me 扩展）

| 端点 | api.md | 实现 | permissions §4 矩阵 | 错误码 |
|---|---|---|---|---|
| `POST /api/user_roles`（grant） | **无行** ❌ | ❌ | ✅ :48 `admin\|user_roles\|grant` | **未定义**（api.md 无行） |
| `GET /api/auth/me` | :27 | ✅ `auth.py:110` | ✅ :45-47 | ✅ 401 |

- **契约缺口**：`POST /api/user_roles` 在 api.md 50 端点总表中**没有对应行**
  （`grep user_roles docs/contracts/api.md` → 0 命中）。出参/错误码/路径均未定。
- **实现缺口**：`deps.py` 无 `require_role`（文档串明确"留给 S3 教师端"，
  permissions §8 第二层）；无 admin 种子/自助授予路径。
- ⚠️ **待裁定**：teacher 角色由谁授予？MVP 计划书仅写"可用种子数据"。

### S3-2 课程创建 + 成员 API

| 端点 | api.md | 实现 | permissions §4 矩阵 | 错误码 |
|---|---|---|---|---|
| `POST /api/courses` | :54 | ❌ | ✅ :51 | ⚠️ 只列 401/403，**未列 422** |
| `GET /api/courses`（list） | :55 | ❌ | ⚠️ **无"list"行**（仅 create/update/read） | ✅ 401 |
| `GET /api/courses/{id}` | :56 | ❌ | ✅ :53/:54 | ✅ 401/404 |
| `PATCH /api/courses/{id}` | :57 | ❌ | ✅ :52 | ✅ 401/403/404 |
| `GET /api/courses/{id}/members` | :58 | ❌ | ✅ :55 | ✅ 401/403/404 |
| `POST /api/courses/join` | :59 | ❌ | ✅ :56 | ✅ 401/403（E-12） |

- `Course`/`CourseMember` ORM 已就绪（`models/course.py`：`invite_code String(8)
  unique`、`term`、`is_archived`、`UNIQUE(course_id,user_id)`）。
- ⚠️ 矩阵无 `teacher | courses | list` 行 → `GET /api/courses` 列表动作靠
  §4 兜底（未列出一律 404），契约与矩阵不一致，需补行。

### S3-3 任务创建 + 加入码 + join API

| 端点 | api.md | 实现 | permissions §4 矩阵 | 错误码 |
|---|---|---|---|---|
| `POST /api/courses/{course_id}/tasks` | :60 | ❌ | ✅ :57 | ⚠️ 只列 401/403/404，**未列 422** |
| `GET /api/courses/{course_id}/tasks`（list） | :61 | ❌ | ⚠️ **无"list"行** | ✅ 401/404 |
| `GET /api/tasks/{id}` | :62 | ❌ | ✅ :59/:60 | ✅ 401/404 |
| `PATCH /api/tasks/{id}` | :63 | ❌ | ✅ :58 | ✅ 401/403/404 |
| `POST /api/tasks/{id}/join` | :64 | ❌ | ✅ :61 | ✅ 401/403/410 |

- `Task`/`TaskSubmission` ORM 已就绪（`models/task.py`：`join_code String(8)
  unique NULL`、`deadline`、`is_archived`、`UNIQUE(task_id,session_id)` +
  `UNIQUE(task_id,student_id)`）。
- ⚠️ 矩阵无 `teacher | tasks | list` / `student | tasks | list` 行 →
  `GET /api/courses/{course_id}/tasks` 列表动作同样靠兜底。
- 硬约束（计划书 S3-3 备注 / permissions §9 Q1）：任务读取权限以 course_members
  为主路径，join_code 仅作入组校验；**若需持久任务成员记录，停下提 schema 增量
  （新 migration + task_members 表），不在 S3 顺手加表**。

### S3-4 提交 API（session→submission 快照）— T-3 从零实现

| 端点 | api.md | 实现 | permissions §4 矩阵 | 错误码 |
|---|---|---|---|---|
| `POST /api/tasks/{task_id}/submissions` | :65 | ❌（T-3） | ✅ :80 | ✅ 401/404 |
| `GET /api/tasks/{task_id}/submissions` | :66 | ❌（T-3） | ✅ :82 | ✅ 401/403/404 |
| `GET /api/tasks/{task_id}/submissions/me` | :67 | ❌（T-3） | ✅ :81 | ✅ 401/404 |

- 出参 `{id, session_id, submitted_at, replaced:boolean}`（api.md:65，已 upsert 语义）。
- 硬约束：`INSERT … ON DUPLICATE KEY UPDATE session_id=?, submitted_at=?`
  （E-5 补充 2）；换会话重做时**旧会话 visibility 处置需明确**（推荐改
  `private`，计划书 S3-4 备注补）；教师"按提交看会话"只读
  `task_submissions` 引用集合（schema_v2 表 3 注记）。
- ⚠️ 前端已预置 `frontend/src/api/types.ts:251 SubmissionResponse`，但注释指向
  `backend/app/schemas/task.py`——**该 schema 文件不存在**（前瞻引用，需在 S3-4
  创建或改注释）。

### S3-5 班级汇总统计 API（含反馈端点）

| 端点 | api.md | 实现 | permissions §4 矩阵 | 错误码 |
|---|---|---|---|---|
| `POST /api/tasks/{task_id}/feedback` | :68 | ❌ | ✅ :83 | ⚠️ 只列 401/404，**未列 422** |
| `GET /api/tasks/{task_id}/feedback` | :69 | ❌ | ✅ :84 | ✅ 401/403/404 |
| `GET /api/courses/{course_id}/summary` | :70 | ❌ | ✅ :85 | ✅ 401/403/404 |

- 出参约束：`summary` 只有 3 字段
  `{submitted_count, total_students, top_pending_verification:[{text,count}]}`
  （api.md:70；Top5）。
- `FeedbackForm` ORM 已就绪（`models/feedback.py`：`scores JSON`、`comment`、
  `submitted_at`、`UNIQUE(task_id,student_id)`，upsert 语义）。
- 任务归属：用户指定 S3-5 含 feedback 两端点 + summary；计划书 S3-5 任务卡
  只写"班级汇总统计 API"、文件 `backend/app/api/teacher.py`（feedback 两端点的
  落点需在 S3-5 内部确认，建议同放 `teacher.py` 或独立 `feedback.py`）。

### S3-6 教师个人训练 + 教学情境演练后端

| 端点 | api.md | 实现 | 说明 |
|---|---|---|---|
| `POST /api/sessions` | :28 | ✅ `sessions.py:252` | 复用 |
| `GET/PATCH /api/sessions/{id}` | :29/:30 | ✅ `:278/:291` | 复用 |
| `POST /api/sessions/{id}/messages` | :35 | ✅ `:324` | 复用 |
| `GET /api/sessions/{id}/messages` | :38 | ✅ `:621` | 复用 |

- **无新端点**（复用 S2 sessions/messages）；矩阵行已齐（teacher sessions/{id}
  read :64、teacher reports read :75）。
- **缺失**：`backend/app/prompts/teacher_persona.py` **不存在**（新建项，
  计划书文件清单 :458）；`audit_events` 表已建（`models/audit.py`）但**无任何写入
  helper / 审计细则**（schema_v3 表 5 注："teacher 角色的审计细则 → S3-1 实现时定"）。

### S3-F1~F4 前端

| 任务 | 后端前置 | 前端现状 | 可复用件 |
|---|---|---|---|
| S3-F1 教师工作区 + 课程/任务列表页 | S3-2 | ❌ 无 `frontend/src/views/teacher/` | ✅ `useHealth` / `describeApiError` / `ModelGatewayBanner` |
| S3-F2 任务创建页 | S3-3 | ❌ | ✅ 同上 |
| S3-F3 提交查看 + 汇总页 | S3-4, S3-5 | ❌ | ✅ 同上 |
| S3-F4 教学情境演练页 | S3-6 | ❌ | ✅ 同上 |

- 路由需新增 4 条教师路由（当前 7 条，无 `/teacher/*`）。
- `DashboardView.vue` 教师视角为骨架，课程/加入仍假数据（:235-250），
  `api/dashboard.ts` 的 `fetchTeacherCourses/joinCourse/joinTask` 为假数据，
  端点交付后替换（S2 遗留 #5）。

---

## 4. S3 要从零实现的端点汇总（实现列全 ❌）

| 文件（建议） | 端点 | 归属任务 |
|---|---|---|
| `api/user_roles.py` 或并入 `auth.py` | `POST /api/user_roles` | S3-1 |
| `api/courses.py` | POST/GET `/api/courses`、GET/PATCH `/api/courses/{id}`、GET `/api/courses/{id}/members`、POST `/api/courses/join` | S3-2 |
| `api/tasks.py` | POST/GET `/api/courses/{course_id}/tasks`、GET/PATCH `/api/tasks/{id}`、POST `/api/tasks/{id}/join` | S3-3 |
| `api/submissions.py` | POST/GET `/api/tasks/{task_id}/submissions`、GET `…/submissions/me` | S3-4 |
| `api/teacher.py`（或含 feedback） | POST/GET `/api/tasks/{task_id}/feedback`、GET `/api/courses/{course_id}/summary` | S3-5 |
| 复用 `api/sessions.py` + `prompts/teacher_persona.py` | 情境演练（复用，无新端点） | S3-6 |
| `frontend/src/views/teacher/*.vue` + 路由 | 4 页 | S3-F1~F4 |

---

## 5. 契约缺口与未分配任务扫描（S2 教训 c）

| # | 问题 | 级别 | 证据 | 建议处置 |
|---|---|---|---|---|
| G1 | `POST /api/user_roles` 在 api.md **无端点行**，路径/入参/出参/错误码全缺 | **阻塞 S3-1** | `grep user_roles docs/contracts/api.md` → 0 | S3-1 开工前补 api.md 行（或出 errata E-29）；需用户裁定入参 `{user_id, role}` 与错误码（403 非 admin / 409 重复角色 / 422） |
| G2 | permissions §4 **无 `courses` / `tasks` 的 `list` 行**，`GET /api/courses`、`GET /api/courses/{id}/tasks` 无矩阵依据 | 阻塞 S3-2/S3-3 | permissions.md §4 :51-61 无 list | 补 2 行（teacher/student × list），或确认"list 由 read 隐含" |
| G3 | S3 端点错误码列**普遍未列 422**（POST courses/tasks/feedback） | 次要 | api.md :54/:60/:68 | 实现会自然产生 422；建议补登或出 errata |
| G4 | **admin 种子/授予路径缺失**：teacher 授予仅 admin 可做，但无 admin 账号、无种子脚本 | 阻塞 S3-1 | permissions :48；无 scripts 种子 | 需裁定：种子 SQL / 首账号提权 / S3-1 内置自授（需用户拍板） |
| G5 | `audit_events` 无写入 helper、无审计动作细则 | 次要 | `models/audit.py` 无 service；schema_v3 表 5 注 | S3-1/S3-6 内定义动作清单（login/role.grant/task.create/submission.view…） |
| G6 | consistency #10（前端全局导航）、#11（Vitest 组件测试）**未分配进任何 S3 任务卡** | 次要 | consistency_check :126-130/:171-173；S3 任务卡无此二项 | 用户确认是否纳入 S3-F1~F4；否则记 S4/S5 |
| G7 | errata E-4 称 S1-5 表数 14→**15**，但 migration 实际建 **12** 张（users/audit_events/courses/user_roles/course_members/tasks/feedback_forms/sessions/messages/reports/revisions/task_submissions） | 次要（文档） | `grep op.create_table alembic/versions/*.py` → 12 | 15 可能含 S4 图谱 3 张；建议勘误或注明口径 |
| G8 | `frontend/src/api/types.ts:251` 注释指向不存在的 `backend/app/schemas/task.py` | 次要 | 文件不存在 | S3-4 创建 schema 或改注释 |

---

## 6. 已知阻塞 / 待用户裁定

1. **G1 + G4（S3-1 前置）**：`POST /api/user_roles` 契约与 admin 授予路径均缺。
   建议用户裁定：① api.md 补该端点行（入参 `{user_id, role}`，仅 admin）；
   ② MVP 如何产生第一个 admin（种子 SQL / 首账号自助提权 / 代码内置）。
2. **G2（S3-2/S3-3 前置）**：`list` 动作是否由矩阵 `read` 隐含，或补行。
3. **S3-3 硬约束确认**：无需持久任务成员表（当前 Q1 决议），S3-3 只做 join_code
   入组校验 + course_members 主路径。
4. **S3-5 feedback 端点落点**：并入 `teacher.py` 或独立 `feedback.py`（建议后者，
   与 api.md 分组一致）。

---

## 7. 测试基线（证据）

```
$ cd backend && venv/Scripts/python.exe -m pytest --collect-only -q
376 tests collected in 0.74s

$ cd backend && venv/Scripts/python.exe -m pytest -rA
...
376 passed, 151 warnings in 322.81s
[exit code: 0]
```

- 与 S2 收口总结一致（376 passed / 0 failed）。
- 测试底座：`sfb_test` + alembic upgrade head + 每用例 TRUNCATE
  （`tests/api/conftest.py` 复用 `tests/models/conftest.py`）。
- 前端：**无 Vitest**（`grep vitest package.json` → 无），S3-F1~F4 无自动化测试。

---

## 8. 建议开工顺序与确认项

1. **先裁定 G1/G4**（S3-1 前置）→ 再开 S3-1（补 `require_role` + 授予端点 +
   `me` 已就绪）。
2. 顺序链路：S3-1 → S3-2 → S3-3 → S3-4 → S3-5；S3-6 与 S3-4 无强依赖（依赖 S2-3
   已交付，可与 S3-2/3 并行）。
3. 每 2-3 个任务停下汇报一次，不合并汇报；每轮跑**全量** pytest（`-rA`）。
4. 顺手发现的问题记入本文件 §5 的"待办"，**不顺手改其他文件**。

---

## 9. 验收命令（本检查的复现入口）

```
test -f docs/s3_prerequisite_check.md
grep -c '^| `' docs/contracts/api.md          # 期望 50（补登后 51）
grep -c '@router\.' backend/app/api/*.py      # 期望 28（合计）
grep -c 'op\.create_table(' backend/alembic/versions/*.py   # 期望 12
cd backend && venv/Scripts/python.exe -m pytest -rA          # 期望 376 passed
```

---

## 10. 裁定落实（2026-11-03，用户审阅通过 + 6 裁定）

### 追问 G2：确认补 **4 行**（非 2 行）

理由：两个 list 端点各有两个角色视角，且 list 与已存在的
`courses/{id} read`、`tasks/{id} read`（按已知 ID 取单条）语义不同——
是"枚举集合"动作。4 行：

```
| teacher | courses | list | courses.teacher_id = 本人（本人所教课程） |
| student | courses | list | course_members 含本人（已加入的课程） |
| teacher | tasks   | list | 课程教师（本人课程的全部任务） |
| student | tasks   | list | 课程成员（course_members 含本人；成员课程的全部任务） |
```

### 裁定 1（G1）：POST /api/user_roles 补 api.md 行（漏收补登，非取代）

入参 `{user_id, role}`；出参 201 `{user_id, role, granted_at}`；
错误码 401/403/404/409/422。已补至 api.md:28。

### 裁定 2（G4）：admin 种子 = 环境变量 ADMIN_USERNAME

`register` 时 `if username == settings.admin_username: 授予 admin 角色`。
`ADMIN_USERNAME` 写进 `.env.example`。S3-1 落地。

### 裁定 3（G3）：三个端点错误码列补 422

`POST /api/courses`、`POST /api/courses/{course_id}/tasks`、
`POST /api/tasks/{task_id}/feedback` 均加"；422 入参校验"。漏收补登，非取代。

### 裁定 4：S3-5 feedback 落点 = 独立 `api/feedback.py`

`teacher.py` 只放 `GET /api/courses/{course_id}/summary`（纯教师动作）。

### 裁定 5（G6）：全局导航纳入 S3-F1；Vitest 留 S4/S5

### 裁定 6（G7）：E-4 加口径注释（15 = 12 + 3）

### G5 / G8 处理

- G5：S3-1 定义 audit 动作清单，MVP 只写 `login` + `role.grant`。
- G8：S3-4 随实现创建 schema 或改 `types.ts:251` 注释。

### 契约改动清单（S3-0 已落地）

| 文件 | 改动 | 证据行 |
|---|---|---|
| `docs/contracts/api.md` | +`POST /api/user_roles` 行（:28） | `grep -c '^| \`'` 50→51 |
| `docs/contracts/api.md` | courses/tasks/feedback 三端点 +422（:55/:61/:69） | `grep -n "422 入参校验"` |
| `docs/contracts/api.md` | §5 端点覆盖补 user_roles 1，合计 50→51（:109） | `grep -oE "合计 5[01]"` |
| `docs/contracts/permissions.md` | §4 +4 行 list（:52-53/:60-61） | `grep -nE "\| list \|"` |
| `docs/contracts/errata.md` | E-4 +口径注（:48） | `grep -n "口径注"` |

> **当前状态：契约已补登，等待全量 pytest 通过后 commit。随后开 S3-1。**
