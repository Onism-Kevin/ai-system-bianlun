# S2 契约一致性检查报告（2026-11-02）

> 状态：**已修复第一轮（#1/#2/#3/#7/#8 已修，#4/#5/#6 已记入口径）**
> 任务来源：S2 前端轨收口前，逐条核对 6 个维度，产出 issue 清单。
> 扫描对象：api.md v1.2 / errata E-1~E-28 / permissions.md / sse_events.md /
> backend/app/api 全部端点 / backend/app/services 全部 / frontend/src 全部 /
> docs/design 全部 / docs/prototypes/plan.md
> 前置：S2-F7 两步 + 复盘入口 + reports 502 修复均已落地（commit dc483ad / f9426eb / d0d8526 / 1e8cd88）。
> 修复：#1/#2（commit 22d5cb2）/ #3/#7（本次）。

## 总览

| 级别 | 条数 | 处置 |
|---|---|---|
| 阻塞 | 2 | #1 模型错误映射缺三端点（✅ 已修）/ #2 permissions 矩阵缺三组资源行（✅ 已修） |
| 重要 | 4 | #3 历史页无工作台入口（✅ 已修）/ #4 S2 端点计数口径（✅ 已统一 28）/ #5 契约有但实现无（✅ 已列）/ #6 T-3 submissions（⏳ 记入 S3-4） |
| 次要 | 5 | #7 T-6 假数据（✅ 已修）/ #8 messages POST 矩阵未体现（✅ 已修）/ #9 图谱无入口（⏳ S4）/ #10 无全局导航（⏳ S3）/ #11 前端无自动化测试（⏳ S3 Vitest） |
| 无发现维度 | 3 | 维度 2（errata 落地）/ 维度 3（路由配对）/ 维度 6 已并入 #2 |

---

## 维度 1：S2 端点 vs api.md 字面

### 发现 #4（重要）：S2 实际实现 28 个端点，非 21

**核对过程**：api.md §5 计数把端点分成 auth 3 / sessions 10 / messages 2 / history 2 /
SSE 1 / stage 3 / wordcloud 1 / reports 3 / revisions 4 / courses 6 / tasks 5 /
submissions 3 / feedback 2 / summary 1 / graph 3 / health 1（合计 50）。

按 `grep '^@router\.' backend/app/api/*.py` 逐文件核对，S2 实际实现 **28** 个端点：

| 分组 | 实现端点数 | 明细 |
|---|---|---|
| auth | 3 | register / login / me |
| sessions | 11 | create / get / patch / messages POST / reflection POST / reflection GET / pause / resume / restart / quick / messages GET |
| events（SSE） | 1 | /{id}/events |
| stage | 3 | explore / analyze / coach_turn |
| reports | 3 | POST / GET latest / GET /{id} |
| revisions | 4 | POST / PATCH / GET list / GET /{id} |
| history | 2 | GET list / GET /{id} |
| health | 1 | GET /health |

**口径澄清**：api.md 第 25-45 行恰好 21 行（auth + sessions 核心/控制/消息/反思 +
messages/{seq} + history + events + stage）。但 S2 还实现了 reports（3）/
revisions（4）/ health（1）共 8 个，落在 api.md 第 47-53、74 行。**故"S2 的 21 个
端点"的说法只覆盖了 api.md 前 21 行，漏算了 reports/revisions/health。**

**建议处理**：S2 收口报告统一口径为"S2 实现 28 个端点"；若需按 api.md 行块划分，
写明"api.md 25-45 行 21 个（含 1 个未实现）+ 47-53/74 行 8 个 = 28"。

### 发现 #5（重要）：契约有但实现无（S2 范围内 2 个，均为未来 scope）

| api.md 行 | 端点 | 实现状态 | scope |
|---|---|---|---|
| :39 | `GET /api/messages/{seq}` | **未实现** | S4-4（原文标注） |
| :46 | `GET /api/sessions/{id}/wordcloud` | **未实现** | S2-F7/S5（原文标注） |

- 核对方式：`grep 'messages/\{seq\}|wordcloud' backend/app/api/*.py` → 0 命中。
- **建议处理**：不属 S2 阻塞；在 S2 收口报告的"已知未实现端点"清单中显式列出，
  避免 S3/S4 误以为已交付。S4-4 / S5 开工时补。

### 维度 1 其余核对（无发现）

- **方法/路径/入参/出参**：28 个实现端点逐条与 api.md 行字面核对，方法、路径、
  入参 schema、出参 shape 均一致。
- **messages GET（api.md:38）**：`after_seq=0` + `limit?`（默认 200），实现一致
  （sessions.py:621-632）。
- **reports POST（api.md:47）**：无 body，201，返回 ReviewReport；实现一致。
- **PATCH /sessions/{id}（api.md:30 + E-17）**：出参平铺 SessionOut，实现一致
  （sessions.py:321 `return SessionOut.model_validate(session)`）。
- **reflection（api.md:36-37）**：POST `{content}`→200 `{updated_at}`；GET→200
  `{content, updated_at}`（空 content=null 不 404）；实现一致（sessions.py:385/414）。

---

## 维度 2：errata E-17~E-28 是否都落到代码

| errata | 声明 | 落地 | 结论 |
|---|---|---|---|
| E-17 | PATCH /sessions/{id} 出参平铺（同 GET） | sessions.py:321 返回 SessionOut 平铺 | ✅ |
| E-18 | S2-2/3/4 任务重分配（备案） | 状态机/端点/SSE 分工已按此执行 | ✅（备案） |
| E-19 | events 403 无触发路径 | events.py 仅 401/404，无 403 分支 | ✅ |
| E-20 | restart 保留消息 | sessions.py:554-557 只置 status，消息全保留 | ✅ |
| E-21 | explore >5000 防御性检查 | explore.py:38 `_TOPIC_MAX_DEFENSIVE=5000` | ✅ |
| E-22 | explore/analyze/coach StructuredValidationError→422 | explore.py:105 / analyze.py:113 / coach_turn.py:151 | ✅ |
| E-23 | StructuredValidationError 映射分端点（422 vs 502） | 短调用→422；reports→502 | ✅ |
| E-24 | ReviewReport scores dict + score（加权总分） | stage_outputs.py:133-138 + reports.py:290-292 | ✅ |
| E-25 | PATCH diff=修改前后 / GET diff=版本间 | revisions.py:217-232（PATCH）/ 257-269（GET） | ✅ |
| E-26 | （跳过，无操作） | — | ✅（用户已裁定跳过） |
| E-27 | GET reports 不返回 sections[] | reports.py:313-321 只有 summary_text | ✅ |
| E-28 | report_progress/ready 未实现 | 无 SSE 推送；S2-F7 骨架屏替代 | ✅（已澄清） |

**维度 2 无发现**：11 条有操作声明的 errata 全部落地；E-26 为跳过项。

---

## 维度 3：前端页面 vs 路由 vs 入口

### 路由配对（无发现）

router/index.ts 6 条路由 ↔ 6 个视图文件，一一对应：

| 路由 | 视图 | 状态 |
|---|---|---|
| /login | LoginView.vue | ✅ |
| /dashboard | DashboardView.vue | ✅ |
| /training | TrainingView.vue | ✅ |
| /review | ReviewView.vue | ✅ |
| /graph | GraphView.vue | ✅（骨架占位，S4） |
| /history | HistoryView.vue | ✅ |

### 发现 #3（重要）：/history 无工作台入口

- DashboardView 的"我的训练"表行点击 → `router.push('/training?id=...')`
  （DashboardView.vue:74），**不指向 /history**。
- /history 目前仅可从 ReviewView 的"← 历史"按钮进入（ReviewView.vue:67）。
- 工作台是登录后首页，用户不知道 /history 存在——与此前"复盘页无入口"同型缺口。
- **建议处理**：DashboardView 历史表加"查看历史"链接，或行点击跳 /history。

### 发现 #9（次要）：/graph 无任何入口

- GraphView 是 S2-F1 骨架占位（S4 任务），全前端无跳转至 /graph 的按钮。
- 属预期（S4 未做），但 S4 开工时应补入口。
- **建议处理**：S4 任务卡加"入口"验收项。

### 发现 #10（次要）：前端无全局导航

- 各页面只有局部返回按钮（← 工作台 / ← 历史 / 工作台），无顶部导航栏。
- 登录后首页 /dashboard 是唯一 hub；/history、/graph 需靠按钮或 URL。
- **建议处理**：S2 收尾或 S3 加统一导航栏（或至少在 dashboard 补历史入口）。

---

## 维度 4：测试覆盖 vs 端点错误码

### 错误码覆盖矩阵（grep 各 test 文件的 status_code 断言）

| 端点文件 | 200/201 | 401 | 403 | 404 | 409 | 422 | 502 | 504 |
|---|---|---|---|---|---|---|---|---|
| test_auth | ✅ | ✅ | — | — | ✅ | — | — | — |
| test_sessions | ✅ | ✅ | ✅ | ✅ | — | ✅ | — | — |
| test_session_control | — | — | — | — | ✅ | — | — | — |
| test_events | — | — | — | — | ✅ | — | — | — |
| test_history | ✅ | ✅ | — | ✅ | — | — | — | — |
| test_reflection | — | ✅ | ✅ | ✅ | — | ✅ | — | — |
| test_reports | ✅ | ✅ | ✅ | ✅ | — | — | ✅ | ✅ |
| test_revisions | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | — |
| test_explore | ✅ | ✅ | — | ✅ | — | ✅ | — | — |
| test_analyze | ✅ | ✅ | — | ✅ | — | ✅ | — | — |
| test_coach_turn | ✅ | ✅ | — | ✅ | — | ✅ | — | — |
| test_health | ✅ | — | — | — | ✅ | — | — | — |

### 发现 #1（阻塞）：explore/analyze/coach_turn 未映射模型传输层异常

- **现象**：`explore.py:105-109`、`analyze.py:113-117`、`coach_turn.py:151-155`
  只捕获 `StructuredValidationError`。`ModelServerError`/`ModelConnectionError`/
  `ModelTimeoutError` 逃逸 → **500**。
- **对照**：`reports.py:276-287` 已修复（三分支映射 502/502/504），三个短调用端点未同步。
- **契约**：permissions §3 定义 `502 = ModelServerError/ModelConnectionError`、
  `504 = ModelTimeoutError`；但 api.md:43-45 端点错误码列只写「401；404；422」，
  **未列 502/504**——既是实现缺口也是契约缺口。
- **建议处理**：三端点与 reports 同款三分支映射；同时在 api.md:43-45 错误码列补
  502/504（或加 errata E-29 澄清"短调用端点模型故障映射 502/504，与 E-23 的
  StructuredValidationError→422 不冲突"）。

### 维度 4 其余核对（无发现）

- reports 全错误码覆盖（401/403/404/502/504）；revisions 覆盖 401/403/404/409/422；
  sessions 覆盖 401/403/404/422（409 在 control/events 测试）；reflection 覆盖
  401/403/404/422；history 覆盖 401/404（owner-only 无 403 路径）。
- **发现 #11（次要）**：前端组件（RevisionCompare / ReflectionForm / ReportPanel）
  无自动化测试（项目无前端测试框架）。MVP 可接受，但 S2 收尾的浏览器验收必须覆盖
  （用户已确认验收步骤 ①~⑤）。建议 S3 引入 Vitest 时补组件单测。

---

## 维度 5：待办 T-1~T-7 状态

| 待办 | 状态 | 说明 |
|---|---|---|
| T-1 | **已修** | test_stage_schemas 同步 E-24（commit 390e329） |
| T-2 | **已修** | reflection 双端点 + 13 用例（commit 390e329） |
| T-3 | **仍在** | submissions 未实现（S3-4）；S2-F7 占位禁用 + 提示「待 S3-4」 |
| T-4 | **已解决** | F7→ReviewView.vue、F8→HistoryView.vue（用户 2026-11-01 确认） |
| T-5 | **已修** | 删 scrollToMessage 死代码（commit 666d8d3） |
| T-6 | **仍在** | DashboardView 历史表假数据 |
| T-7 | **已修** | health 徽标 unreachable 覆盖「不可达」（commit d683a0c） |

### 发现 #6（重要）：T-3 submissions 未实现

- `POST /api/tasks/{task_id}/submissions`（api.md:65）后端未实现（grep 无路由）。
- S2-F7 提交按钮已禁用 + 提示「待 S3-4」。
- **建议处理**：S3-4 任务卡加"实现 submissions 三端点（POST/GET/GET me）+ upsert 测试"。

### 发现 #7（次要）：T-6 DashboardView 历史假数据

- `frontend/src/api/dashboard.ts:42` `fetchHistory()` 返回硬编码 3 条假数据。
- `frontend/src/views/DashboardView.vue:171` 表头标注「假数据 · GET /api/history 属 S2-12」。
- 历史页（HistoryView）已用真实 `listHistory()`，但工作台未接。
- **建议处理**：DashboardView 接真实 `listHistory()`；与发现 #3 一并修。

---

## 维度 6：S2 端点 vs permissions.md §4 矩阵

### 发现 #2（阻塞）：矩阵缺 reflection / history / stage 三组资源行

permissions.md §4（第 41-84 行）逐行核对，S2 已实现但矩阵无对应行的端点：

| 实现端点 | 矩阵有无行 | 说明 |
|---|---|---|
| `POST/GET /api/sessions/{id}/reflection` | **无** | student create/read；teacher 是否可读未定义 |
| `GET /api/history`、`GET /api/history/{id}` | **无** | student read（owner 视角） |
| `POST /api/sessions/{id}/explore` | **无** | student create（会话可见即可） |
| `POST /api/sessions/{id}/analyze` | **无** | student create |
| `POST /api/sessions/{id}/coach_turn` | **无** | student create |

- 矩阵现有覆盖：auth / user_roles / courses / tasks / sessions / events(SSE) /
  messages / revisions / reports / task_submissions / feedback_forms / summary /
  graph / audit_events / health。
- **实现与矩阵的冲突点**：reflection 与 history 是 S2 已交付功能，矩阵无行 →
  S3 教师端实现时无法据矩阵判定教师对 reflection/history 的可见性。
- **建议处理**：补 5 行（reflection create/read ×2、history read、stage create ×3
  或合并为"stage（explore/analyze/coach_turn）"一行）。

### 发现 #8（次要）：messages POST 动作未在矩阵体现

- 矩阵 `student | messages | list / read`（permissions.md:68）只覆盖读路径。
- `POST /api/sessions/{id}/messages`（提交消息）是写动作，矩阵无对应行。
- **建议处理**：补 `student | messages | create` 行（owner，非 waiting → 409）。

---

## 待用户裁定（2026-11-02 已全部裁定）

1. **#1 契约口径**：✅ 已裁定——补 api.md:43-45 端点列（502/504），不加 E-29。
   三端点代码与 reports 同款三分支映射（已落地，commit 22d5cb2）。
2. **#2 reflection 教师可见性**：✅ 已裁定——student-only 403（reflection 私密）。
   矩阵已补 5 行（commit 22d5cb2）。
3. **#3 历史入口形式**：✅ 已裁定——DashboardView 历史表加独立「查看全部历史 →」
   链接（行点击保留跳 /training）。已落地。

---

## 修复状态更新（2026-11-02）

| # | 问题 | 状态 | Commit / 说明 |
|---|---|---|---|
| #1 | explore/analyze/coach_turn 模型故障映射 | ✅ 已修 | 22d5cb2（三端点三分支 + api.md:43-45 补 502/504 + 9 回归测试） |
| #2 | permissions §4 矩阵缺 reflection/history/stage | ✅ 已修 | 22d5cb2（补 5 行：messages create / reflection student+teacher / history / stage） |
| #3 | /history 无工作台入口 | ✅ 已修 | 本次（DashboardView 表头「查看全部历史 →」） |
| #4 | S2 端点计数口径 | ✅ 已统一 | 本报告已写"28 个端点"（api.md 25-45 行 21 + 47-53/74 行 8） |
| #5 | 契约有但实现无（messages/{seq}、wordcloud） | ✅ 已列 | 本报告维度 1 已列；收口报告将沿用 |
| #6 | T-3 submissions 未实现 | ⏳ 记入 S3-4 | 本报告维度 5 已写"S3-4 任务卡加..."；S3-4 开工时落实 |
| #7 | T-6 DashboardView 历史假数据 | ✅ 已修 | 本次（接真实 listHistory()） |
| #8 | messages POST 矩阵未体现 | ✅ 已修 | 22d5cb2（permissions §4 补 messages create 行） |
| #9 | /graph 无入口 | ⏳ S4 | 本报告维度 3 已记；S4 任务卡加"入口"验收项 |
| #10 | 前端无全局导航 | ⏳ S3 | 本报告维度 3 已记；S2 收尾或 S3 加 |
| #11 | 前端无自动化测试 | ⏳ S3 | 本报告维度 4 已记；S3 引入 Vitest 时补 |

---

## 验收命令

```
test -f docs/consistency_check_s2_2026-11-02.md
```

> 本报告第一轮修复已落地（#1/#2/#3/#7/#8），口径已统一（#4/#5），
> 遗留项（#6/#9/#10/#11）已记入对应 S3/S4 任务。待 commit。

