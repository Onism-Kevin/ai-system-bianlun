# S1-10 页面原型提案：五页选型方案

> 状态：**v2（2026-10-13，S1-10）**——提案经用户审阅通过（五页清单/反思 UI/G1/G2 裁定）；五页静态 HTML 已实现于本目录（training / review / graph / teacher_tasks / dashboard）。
> 依据：方案 §8（页面与信息架构，十页，`思辨工坊项目完整方案.md:368-379`）、api.md v1.2（50 端点）、permissions.md v1.0（§4 矩阵 / §5 会话可见范围）、notes §6 第 7 条（反思 UI 已裁定）、计划书 S1-10 任务卡（完成信号：五页可在浏览器打开走通假数据）。

## 1. 五页清单（页面 + 为什么选它）

| # | 页面 | 文件 | 角色 | 一句话理由 |
|---|---|---|---|---|
| 1 | 训练页 | `training.html` | 学生 | 方案 §4.1 主线"人机论证训练"的落点；任务书点名"发送→消息追加"；端点覆盖最全 |
| 2 | 复盘页 | `review.html` | 学生 | 任务书点名"生成报告→四维分数"；方案 §8.6 三要素（量表反馈/版本比较/个人反思）；反思 UI 落点 |
| 3 | 论证图谱页 | `graph.html` | 学生 | 产品与通用聊天的差异点（§4.1D / S4）：relation 六枚举 + source_ref 原文定位 + 待核实标记 |
| 4 | 教师任务页 | `teacher_tasks.html` | 教师 | 双角色必需；教师可见范围硬规则（§5）只能在此体现；课程任务是学生训练的载体 |
| 5 | 首页工作台 | `dashboard.html` | 双角色 | 方案 §8.2 入口；把五页串成产品（学生工作区/教师工作区）；history + 加入任务 + 创建会话 |

选型标准：

- C1 核心回路闭环：训练页（辩论 + 追问 + 修订）→ 复盘页（报告 + 反思 + 提交）两步走通方案 §4.1 学生主线
- C2 双角色代表：学生 3 页 + 教师 1 页 + 双角色入口 1 页；教师侧规则（submissions 仅已提交行、private 会话 404）有承载页
- C3 端点可映射：每页均有明确 api.md 端点；唯一缺口见 §6 G1（训练页发送），如实标注不臆造
- C4 差异化代表：图谱页的 relation/source_ref/verified 是思辨工坊区别于普通聊天机器人的核心
- C5 立项要求：任务书第二步技术要求点名的两个交互（训练页发送、报告页四维分数）直接入选

## 2. 每页详述（核心交互 / API 端点 / 角色权限）

### 页 1：训练页 `training.html`（学生）

- **核心交互**：创建会话（topic/visibility）→ SSE 实时消息流（role + agent_role 徽标，E-5）→ 输入框"发送"追加学生消息 → 教练追问卡片（quote_refs 引用学生原文）→ 控制条（暂停/续写/重开/加速，状态徽标 waiting/generating/paused）→ 保存初稿/修改稿（revisions，version 自增 + diff）→ 阶段一面板（议题拆解：concepts/scope/subquestions/stakeholders）
- **API 端点**：`POST /api/sessions`；`GET /api/sessions/{id}/events`（SSE，事件表全部引 sse_events.md，不重复）；`GET /api/sessions/{id}/messages?after_seq=`；`POST pause|resume|restart|quick`；`POST /api/sessions/{id}/coach_turn`（`{mode:"coach"|"rebuttal"}`）；`POST /api/sessions/{id}/explore`；`POST /api/revisions`（`{session_id, content, status}`）；`POST /api/sessions/{id}/messages`（G1 已补登 api.md v1.2）
- **角色权限**（permissions.md）：student——sessions create/read/update（owner，非 owner 404）；SSE subscribe（同 §5 规则，建流前鉴权）；revisions create/update（owner）。teacher——sessions read（private 一律 404；task 可见集合内可读，MVP 只标注不做视图）；messages 随会话可见规则
- **假数据行为**（第二步）：发送 → 本地数组追加（seq 自增，agent_role 轮换假值）；暂停/加速改状态徽标 + SSE 事件假流

### 页 2：复盘页 `review.html`（学生）

- **核心交互**：点击"生成报告"→ 假 report_progress/ready 进度（S2-F7 硬约束）→ 四维度分数卡（score + weight + evidence 引用 + rubric_version=v1.0 徽标）+ overall_score + 三段正文（量表/依据/建议，§4.1E"分数不得单独代表能力"）→ 观点版本比较（revisions 列表 + diff_vs_prev）→ **个人反思填写（见 §4）**→ 可选"提交给课程任务"（POST submissions，upsert）
- **API 端点**：`POST /api/sessions/{id}/reports`（同步生成 + SSE 跟进）；`GET /api/sessions/{id}/reports`（最新一份）；`GET /api/reports/{id}`（sections[]）；`GET /api/revisions?session_id=`；`POST /api/sessions/{id}/reflection` + `GET /api/sessions/{id}/reflection`（G2 已补登 api.md v1.2）；`POST /api/tasks/{task_id}/submissions`（`{session_id}`）
- **角色权限**：student——reports create/read（owner，多份取最新）；revisions read（owner）；submissions create（owner + 非课程成员 404 存在性隐藏）。teacher——reports/revisions read（随可见集合，含未提交的 task 会话进度，§5）
- **假数据行为**：生成报告 → 假四维分数（权重 0.30/0.25/0.25/0.20 与 rubric.json 一致）+ evidence 占位 + summary_text 三段

### 页 3：论证图谱页 `graph.html`（学生）

- **核心交互**：点击"抽取论证结构"（analyze，假 nodes/edges）→ 静态布局渲染 → 点节点看 source_ref 原文定位（`{message_seq, quote}`）→ verified=false 节点标"待核实"（§3-3 不确定性可见）→ 可选词云补查入口（未生成 404 的分支演示）
- **API 端点**：`POST /api/sessions/{id}/analyze`；`GET /api/sessions/{session_id}/graph`；`GET /api/messages/{seq}`（原文反查）；`GET /api/sessions/{id}/wordcloud`（可选）
- **角色权限**：student——graph read/analyze（owner）。teacher——graph read（随可见集合）；messages/{seq} 随消息可见规则
- **假数据行为**：静态节点/边，relation 六枚举（支持/反驳/补充/依赖/限制/需要证据）各至少一条

### 页 4：教师任务页 `teacher_tasks.html`（教师）

- **核心交互**：tab 1 任务管理——创建任务（title/material/deadline/need_join_code → join_code 展示）→ 任务列表（deadline/归档标记）→ 提交列表（**仅已提交行，未提交无行**，S3-4）→ 点提交记录只读跳复盘（可见集合）；tab 2 班级汇总——submitted_count / total_students / top_pending_verification Top5
- **API 端点**：`POST /api/courses/{course_id}/tasks`；`GET /api/courses/{course_id}/tasks`；`GET /api/tasks/{task_id}/submissions`；`GET /api/courses/{course_id}/summary?task_id=`；`GET /api/courses`；`GET /api/courses/{id}/members`；`POST /api/tasks/{task_id}/feedback`（`{scores, comment}`，upsert）
- **角色权限**：teacher——courses create/read/update（teacher_id=本人）；tasks create/read/update（所属课程教师）；submissions list（仅已提交行）；summary read（本人课程）；members read（仅学生行）。学生侧 `POST /api/tasks/{id}/join`（403 错码 E-12 / 410 过期）在工作台页演示
- **假数据行为**：提交列表 3 行"已提交"演示，一行"未提交"用注释说明（无行 = 存在性隐藏）

### 页 5：首页工作台 `dashboard.html`（双角色）

- **核心交互**：页眉角色徽标（student/teacher 可并存，方案 §8.1）→ 学生视角：继续上次练习（history 列表 + 状态徽标）/ 加入课程任务（invite_code 输入，403 错码演示）/ 加入单个任务（join_code，410 过期演示）/ 创建个人探索（topic 输入 → POST sessions）；教师视角：我的课程列表 → 跳教师任务页
- **API 端点**：`GET /api/auth/me`；`GET /api/history`；`GET /api/courses/{course_id}/tasks`（学生→成员课程全部任务）；`POST /api/courses/join`（`{invite_code}`，403 E-12）；`POST /api/tasks/{id}/join`（`{join_code}`，410）；`POST /api/sessions`；`GET /api/courses`（teacher→本人教的；student→已加入的）
- **角色权限**：student——history read（owner 视角）；tasks read（§9 Q1：课程成员为主路径）；join 端点（错码对称化）。teacher——courses read（本人教的）
- **假数据行为**：双角色徽标切换演示；health 徽标（`GET /api/health` 匿名，降级也 200）放页脚

## 3. 未入选五页的去向

| 方案 §8 页 | 去向 |
|---|---|
| 1 登录与角色入口 | 折叠进工作台页眉（角色徽标 + 登录/退出占位）。真登录是 S2-1；Cookie httpOnly 在 UI 不可见，独立页无展示价值 |
| 3 议题探索页 | 折叠为训练页阶段一面板（explore 四区块输出；session-scoped，同页更顺；`ExploreOut` schema 已定） |
| 8 教师个人训练页 | 复用训练页（端点集相同，仅角色徽标与只读边界不同；task 会话下教师可见集合内可读） |
| 9 班级汇总页 | 折叠为教师任务页 tab 2（summary 出参仅 3 字段，独立页信息量不足） |
| 10 历史与导出页 | history 折叠进工作台（history.py 两个端点）；导出无端点、删除 MVP 不做（E-8 归档替代），标注留 S2 |

## 4. 反思填写 UI 提案（notes §6 第 7 条）

- **位置**：复盘页——方案 §8.6 复盘页三要素"量表反馈、观点版本比较、个人反思"的第三项（方案为最高权威，placement 以此为准）
- **形态**：独立"个人反思"卡片 = 多行 textarea + "保存反思"按钮；置于"生成报告"按钮上方相邻处；按钮旁提示"未填写反思时 D4 按'反思缺失'计"
- **时机裁定建议**：报告生成前填写——D4 评分依赖反思文本（rubric 待改进/未达标档均含"反思缺失或套话"），报告 prompt 需要"修改稿 + 反思"两项输入
- **可改性**：反思保存后可修改，重跑报告反映最新文本（reports 无 UNIQUE，重跑=新行，E-5）
- **【缺口 G2 已裁定】存储**：schema_v3 `revisions` 无反思列（content/version/status），`feedback_forms` 是任务级 UX 反馈（scores/comment）非自反思。用户 2026-10-13 裁定方案 **(a2)：sessions 表加 `reflection TEXT NULL` 列**——MVP 简化原则，单会话单文本不版本化，UPDATE 同一列；(a1) 新表与复用 revisions 均否决（后者污染 D4"修订质量"判定）。配套 API `POST/GET /api/sessions/{id}/reflection`（api.md v1.2 已补登），schema 增量为 2026-10-13 第二个 migration（schema_v2 FINAL-2026-10-13）。

## 5. 第二步执行约定（确认五页后生效）

- 技术：静态 HTML + 内联 CSS + 原生 JS；无构建工具、无 Vue/React；docs/prototypes/ 下五文件
- 每页**顶部标注条**：对应角色 + 对应 API 端点清单（G1/G2 已裁定并补登 api.md v1.2，按正式端点标注）
- 每页**底部标注区**：本页未实现交互（留 S2/S3/S4，按 §2 各页权限段的"假数据行为"之外的真实实现点）
- 视觉：不追求配色/字体/间距；追求区块/字段/按钮的 IA 正确

## 6. 契约缺口（均已裁定，2026-10-13）

### G1 训练页"发送"无端点——已裁定：补登 api.md v1.2

- 事实：方案 §9 定义 `POST /api/sessions/{id}/messages`（提交观点或回应）；api.md v1.1 总表 47 行无此端点；§5 计数写"sessions 8（含 pause/resume/restart/quick）"而总表 sessions 段实际 7 行、所列分组数相加 48≠47——三者共同印证漏收
- 影响：训练页核心交互"点击发送→消息追加"、教练追问（coach_turn 的 `quote_refs:[{seq,quote}]` 引用学生消息 seq）均依赖它
- 裁定（用户 2026-10-13）：接受"漏收修正"，**不写 errata**（非取代/差异，是漏收）；已补登 api.md v1.2 sessions 段 quick 之后，入参 `{content}` / 出参 `{seq, created_at}` / 行为（同步写 messages `role='user'` → 异步 waiting→generating → SSE 推送下一轮）/ 错误码（401；403 非 owner；404；409 非 waiting）按用户给定 spec 落笔
- **用户消息由前端本地渲染，不走 SSE 回显**（用户裁定，多标签页一致性 MVP 可接受）——已写入 api.md messages 行备注
- 备选已排除：无合适替代端点（coach_turn 入参仅 `{mode}`；revisions 是修改稿不是消息）

### G2 反思存储未定义——已裁定：(a2) sessions 加列（见 §4）

## 7. 备选组合（用户确认时可换页）

- 换法 A：工作台 ↔ 登录页（独立登录表单页）——若认为入口需单独成页
- 换法 B：议题探索页独立成页，训练页去掉阶段一面板——若认为议题研究是产品另一半主线
- 换法 C：班级汇总页独立，教师任务页只留任务管理——若教师页信息量过大

每次换页牵动 §2 端点映射表，确认后先更新本文件再执行第二步。

## 8. 待用户拍板清单（2026-10-13 全部裁定）

1. 五页清单——**接受推荐**（training / review / graph / teacher_tasks / dashboard），未入选页去向接受；备选换法 A/B/C 均不采纳
2. G1——**补登 api.md v1.2**（漏收修正，不写 errata）；用户消息前端本地渲染不走 SSE
3. G2——**裁定 (a2) sessions 加 reflection 列**（schema 增量，2026-10-13 第二个 migration）
4. 议题探索折叠为训练页阶段一面板——**接受**
5. 反思 UI 时机"报告生成前填写"——**接受**
