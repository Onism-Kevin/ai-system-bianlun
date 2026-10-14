# 契约全域一致性检查报告（2026-10-13）

> 状态：v1.1 定稿（用户 2026-10-13 审阅通过；第一批文档修复 + 第二批 E-11 代码落实均已落地并随本报告 commit）
> 任务来源：用户 m00769 任务书——S1-11 完成后、S2 开工前，逐条核对 7 个维度。
> 前置任务：G1 已由 S1-10 修复（方案 §9 有 `POST /api/sessions/{id}/messages` 而 api.md 漏收，
> api v1.2 已补登）。本报告不再列 G1。

## 总览

| 级别 | 条数 | 处置 |
|---|---|---|
| 前置阻塞 | 3 | #1/#2/#3 全部已修（#2/#3 第一批；#1 第二批 E-11 代码落实） |
| 重要 | 9 | #4 第一批已修；#8 S2-2 已处理（E-15）；#5-#7/#9 分散到对应任务开工前（见待办） |
| 待用户裁定 | 4 | 已全部拍板（见"用户裁定记录"） |
| 次要 | 6 | 5 条第一批已修；§4.3 三功能记 S5+ 不修 |
| **无发现维度** | 4 | 维度 4 大纲 / 路径形态差异（复核后）/ 维度 2 逐表 / 维度 5 逐条 |

> 后续更新（2026-10-14，S2-2/S2-3 收口）：#8 已由 S2-2 落地（can_read_session
> owner 优先级 + errata E-15 + permissions §5.6）；S2-2/S2-3/S2-4 任务内容
> 重分配（状态机基座/端点/SSE+编排器）备案于 errata E-18；api.md:30 PATCH
> 出参平铺勘误见 E-17。

## 用户裁定记录（2026-10-13，用户 m00918）

1. **explore 输出无持久化承载**（原待裁定 10）→ MVP 不做持久化（编辑不落库），记入 S5+ 待办。
2. **analyze NodeType 三枚举 vs §4.1D 八要素**（原待裁定 11）→ 保持三枚举
   （claim/evidence/rebuttal）。方案 §4.1D 是"整理为"，不是"必须每类一个 node"，抽象层级不同。
3. **judge 事件 verdict schema**（原待裁定 12）→ 留 S2-10 或 S4 定，现在不展开
   （等 rubric 落地）。sse_events.md:130 已有占位机制，S2-8 验收不受影响。
4. **audit_events 无模型版本/错误/耗时/重试列**（原待裁定 13）→ 用 detail JSON 承载，
   写进 errata E-13。方案 §10 要求的是"记录"，没规定列结构。

级别调整：原"重要 #1/#2/#3"（E-11 未落实 / E-7 文档矛盾 / S2-3 验收句冲突）用户改判
**前置阻塞**——这 3 条 S2 开工直接踩，等同硬伤。

## 维度 1：方案 §9 API 表 vs api.md v1.2（50 端点）

- **路径形态差异（复核后改判"无发现"）**：方案 §9 的 15 端点中 6 个路径形态与 api.md
  不同（`GET /api/me` vs `GET /api/auth/me`；`POST /api/tasks` vs `POST /api/courses/{course_id}/tasks`；
  `GET /api/tasks` vs `GET /api/courses/{course_id}/tasks`；`POST /api/sessions/{id}/revisions`
  vs `POST /api/revisions`；`GET /api/teacher/tasks/{id}/summary` vs `GET /api/courses/{course_id}/summary`；
  `POST /api/feedback` vs `POST /api/tasks/{task_id}/feedback`）。语义等价，嵌套/扁平是
  契约演进风格差异非缺陷——G1 修补（v1.2）已按 api.md 现行形态定案。**无发现**。
- **方案 §9 端点覆盖核对**：15 个方案端点在 api.md 全部有对应实现（语义等价），无缺失。
  注：v1.1 声称的"sessions 8"是笔误——总表实际 7 行（S1-7 时期），v1.2 补登
  messages×1/reflection×2 后为 10，api.md §5 计数已自洽（50）。

## 维度 2：方案 §10 数据模型 vs schema_v1/v2/v3（逐表逐列）

- **无发现（本维度）**：13 表全部有 schema 定义且逐列核对一致；图谱三表
  （argument_nodes/argument_edges/evidence_sources）schema_v3:88 已声明"S4 草案"，
  计划书 S4-2 正式落表前有效。详见下方待裁定 2 条（NodeType 与 judge verdict 属图谱
  schema 细化，均已拍板）。

## 维度 3：方案 §8 页面 vs S1-10 五页原型

- **无发现**：plan.md §3（五页 + 未入选 5 页去向：登录→工作台页眉、议题探索→训练页
  阶段一面板、教师个人训练页→复用训练页、班级汇总→教师任务页 tab2、历史导出→
  工作台）与五页 HTML 逐一对应；未入选页有明确去向无遗漏。

## 维度 4：sse_events.md 事件表 vs 方案 §4.1 交互需求

- **judge 事件 verdict 字段 schema 未定义**（schema_v3_messages.md:82 judge "verdict
  等 payload 设计随 S2-10 报告需求定"）：judge 事件 data 缺 schema 定义。
  sse_events.md:83-86 合法事件白名单未列 judge，v1.0:263 S2-8 验收要求 judge 事件
  产生即通过。→ 已拍板：留 S2-10 或 S4 定（用户裁定 3），sse_events.md:130 占位
  机制有效，S2-8 验收不受影响。

## 维度 5：permissions.md 矩阵 vs 方案 §4/§5 权限描述

- **无发现**：矩阵与方案角色权限逐条一致（含教师个人训练页=教师 owner 私有会话，
  由学生 sessions 规则覆盖；S5-1"教师查未提交练习 404"与 §5 规则 2 的措辞冲突
  复核为语义等价——查会话 200 vs 查提交记录 404）。

## 维度 6：计划书验收命令逐条核对

- **S2-3 验收句与 E-1 冲突**（v1.0:243 与 v1.1:196，seq "连续" vs 全局交错）——
  前置阻塞 3，第一批已修（errata E-14）。
- **v1.1 两处旧句未跟 E-4 修订**（v1.1:176 "visibility CHECK 生效"；v1.1:183/:264
  spike 标注口径与用户 2026-10-13 裁定冲突）——重要 4，第一批已修。
- **S1-6 验收句措辞**（v1.0:205 "event/id/data 三字段" vs E-9 后 id 仅 speech_* 事件带）——第一批已修。
- **S2-13 单键/双键**（v1.1:270-272 {model_gateway:down} vs api.md:74 双键）——第一批已修。
- **E-9/E-10 取代验收**（v1.0:235/:247 原文保留+errata 备案，机制正常 ✓）。

## 维度 7：errata E-1~E-12 与各文档引用一致性

- **E-7 代码对 schema 文档错**（model_*.py onupdate 应用层 ✓ 但 schema_v1:21/:37/:75、
  schema_v3:27 仍写 DB 层 ON UPDATE CURRENT_TIMESTAMP）——前置阻塞 2，第一批已修。
- **E-11 已落实到 stage_outputs.py**（EdgeRelation 中文六枚举取代旧 EdgeType；
  ArgumentNode 增 source_ref（可选）；CoachTurn 增 quote_refs）——前置阻塞 1，
  第二批已落实（prompt 同步改新 schema + 带 seq 入参；test_stage_schemas 用例更新；
  model_bench.py 加注"历史 bench 快照"注释不随动）。
- **Ollama 残留**（api.md:94、方案:255/:305/:514）——第一批已修。
- **E-1/E-2/E-3/E-5/E-6/E-8/E-12 落实核对**：api.md/schema/permissions 全部 ✓；
  计划书验收句已就地更新（E-4）✓。健康出参点名问题答案：api.md:74 已无 ollama。

## 汇总表（按级别；处置列记录第一批落地情况）

| # | 问题 | 文件+行号 | 级别 | 处置 |
|---|---|---|---|---|
| 1 | E-11 未落实到 stage_outputs.py/prompts（relation 六枚举/source_ref/quote_refs） | stage_outputs.py:33-34,43-46,59-64；analyze.py:27-31,37；coach.py:33 | 前置阻塞 | **第二批已落实**（[S1-收口] code: E-11 落实 commit） |
| 2 | E-7 与 schema 文档矛盾（schema 写 DB 层 ON UPDATE，E-7 定为应用层 onupdate） | schema_v1.md:21,37,75；schema_v3_messages.md:27 | 前置阻塞 | **第一批已修**（改 E-7 口径） |
| 3 | S2-3 验收句与 E-1 冲突（seq 连续 vs 全局交错） | 计划书 v1.0:68,243；v1.1:196 | 前置阻塞 | **第一批已修**（改"会话内单调"+E-14 备案） |
| 4 | v1.1 两处旧句（CHECK 生效/spike 标注口径） | v1.1:176,183,264 | 重要 | **第一批已修** |
| 5 | tasks 表缺训练目标/步骤/提交格式/评价维度列 | schema_v2_tasks.md:25-32 | 重要 | S3-F2 任务创建页开工前定（S3-3 schema 增量） |
| 6 | S3-5 汇总范围缩水（计划书 2 项 vs 方案 §4.2D 5 项） | v1.0:102；方案:160-165 | 重要 | S3-5 开工前裁定 |
| 7 | 方案 §7.4 示例格式过期（type 非 relation、字符串 source_ref） | 方案:350-363 | 重要 | S4-2 开工前重写或加勘误注 |
| 8 | 教师个人训练页可见范围无校验路径 | permissions.md:64 | 重要 | **S2-2 已处理**（can_read_session owner 优先级 + errata E-15 + permissions §5.6） |
| 9 | S5-1 验收句与权限矩阵措辞冲突 | v1.0:346 | 重要 | S5-1 开工前改措辞 |
| 10 | explore 输出无持久化承载 | api.md:43 | 已拍板 | MVP 不持久化，记 S5+ |
| 11 | analyze NodeType 三枚举 vs §4.1D 八要素 | stage_outputs.py:33 | 已拍板 | 保持三枚举，不改 |
| 12 | judge 事件 verdict schema 未定义 | schema_v3_messages.md:82 | 已拍板 | 留 S2-10/S4 定（sse_events:130 占位） |
| 13 | audit_events 无模型版本/错误/耗时/重试列 | schema_v3_messages.md:71-82 | 已拍板 | detail JSON 承载（errata E-13），schema 注记已补 |
| 14 | Ollama 残留 3 处 | api.md:94；方案:255,305,514 | 次要 | **第一批已修**（带修订注记） |
| 15 | S2-13 单键/双键口径 | v1.1:206,272 | 次要 | **第一批已修**（双键） |
| 16 | S1-6 验收句措辞 | v1.0:205 | 次要 | **第一批已修** |
| 17 | wordcloud 生成时机未定义 | sse_events.md:139 | 次要 | **第一批已修**（finished 时生成推送） |
| 18 | rubric D1"七要素"表述 | rubric.json:14 | 次要 | 无发现（自纠：§4.1D 标题即七要素，表述正确） |
| 19 | §4.3 三功能无端点（报告导出/收藏搜索/数据删除） | 方案:169-179 | 次要 | 不修，记 S5+ 范围（产品愿景 vs MVP 端点表） |

## 第一批修复清单（本次 commit 落地）

| 文件 | 改动 |
|---|---|
| schema_v1.md | :21 全局约定 + :37 users + :75 courses 三处 updated_at 表述改 E-7 口径（应用层 onupdate，DB 层不加 ON UPDATE） |
| schema_v3_messages.md | :27 messages.updated_at 同改 E-7 口径；:81 detail 列加注"模型版本/错误/耗时/重试四项亦进此列（errata E-13）" |
| errata.md | 新增 E-13（audit_events detail JSON 承载）+ E-14（S2-3 seq 验收句备案） |
| api.md | :94 "Ollama/model_gateway 停机"→"模型网关停机" |
| 思辨工坊执行计划书.md（v1.0） | :68 S2-3 任务行 seq 口径 + :205 S1-6 三字段措辞改 E-9 口径；:243 S2-3 验收句改"seq 在会话内单调（全局交错）"（v1.0:68 的 Ollama 保留——v1.1 修订 2.5 已明确 v1.0 原件不受影响，仅修 errata 类冲突） |
| 思辨工坊执行计划书 v1.1.md | :176 S1-3 CHECK→应用层校验；:183 S1-9b 完成信号改产品标准口径；:196 S2-3 同改；:264 S1-9b 验收改产品标准口径（用户 2026-10-13 裁定）；:272 S2-13 单键→双键 |
| docs/思辨工坊项目完整方案.md | :255 架构图 + :305 §6.4 + :514 §13.1 三处 Ollama 残留改模型网关表述（带修订注记）——**该文件原为只读属性，已临时清除后恢复，见汇报说明** |
| sse_events.md | :139 wordcloud 生成时机补注（会话转 finished 时后端生成推送） |

## 待办

1. ~~第二批（S2 开工前，改代码前停下等指令）~~：**E-11 已落实**（第二批，
   commit `[S1-收口] code: E-11 落实`）——`stage_outputs.py`（relation 六枚举
   取代旧 type + source_ref 可选 + quote_refs）+ prompts（analyze/coach/rebuttal
   改新 schema 输出格式、入参改带 seq 消息列表；`__init__.py` 增 render_messages
   共享渲染）+ `test_stage_schemas.py` 用例更新 + `run_spike.py` 假消息带 seq
   + `model_bench.py` 加"历史快照"注释；全量 pytest 通过。prompt 改动说明：
   新 prompt 与 mini-bench 时不同，mini-bench 数据不重跑（历史归档）。
2. **重要 #5-#9 分散到对应任务开工前**：#8→**S2-2 已处理**（can_read_session +
   errata E-15，2026-10-14 收口）、#5→S3-F2（连带 S3-3 schema 增量）、
   #6→S3-5、#7→S4-2、#9→S5-1。S2-2/S2-3/S2-4 任务内容重分配备案见 errata E-18。
3. **S5+**：§4.3 三功能（报告导出/收藏搜索/数据删除）+ explore 输出持久化。

## 覆盖清单

扫描源：方案 §4.1/§4.2/§4.3/§7.4/§8/§9/§10/§13/§15 与全文 grep（Ollama 42 处、
Authorization 13 处、v0.2-draft/v0.1-draft 0 处）；api.md v1.2 全 50 端点；
permissions.md 全文；errata.md E-1~E-12；计划书 v1.1 全文 + v1.0 验收句区
（:180-:360）；schema_v1/v2/v3 全文；sse_events.md 全文；rubric.json；
notes §6/§7；plan.md；legacy_import.md；traces。行号以 read 工具物理行为准。
