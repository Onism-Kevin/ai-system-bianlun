# 契约定稿 v4：旧 JSON 辩论存档导入映射（S1-11 范围）

> **状态：定稿 v1.0（2026-10-13，S1-11，用户审阅通过；§6 三条裁定已入档）**——前置 S1-4（sessions/messages 表定义）；
> 依据：方案 §4.4"JSON 辩论存档 → 迁移为训练会话、观点版本和复盘记录；兼容旧存档导入"、
> 计划书 S1-11 卡（验收：字段映射表覆盖现存 4 份存档字段）；
> 引用：`schema_v2_tasks.md`（sessions）、`schema_v3_messages.md`（messages/revisions/reports）、`errata.md` E-1（seq 方案 A）。
> 本文件是**兼容性设计文档**，不是运行时代码；MVP 只落映射与只读查看器设计，真导入见 §4。

## §0 现存 4 份存档盘点（字段映射的事实基线）

| 文件 | topic | 独有/缺失字段 | history 条数 | 裁判条目 |
|---|---|---|---|---|
| `history/debate_20260710_202313.json` | 人该不该活着 | **有 `temperature: 0.7`**；无 mode/max_turns/temp_* | 9（正方 4 + 反方 4 + 裁判 1） | 有（评判阶段；内容为模型伦理拒答，见 §5-4） |
| `history/debate_20260712_230428.json` | 人活着有没有意义 | 有 mode/max_turns/temp_zheng/temp_fan；无 temperature | 6（正方 3 + 反方 3） | 无 |
| `history/debate_20260712_230431.json` | 人活着有没有意义 | 同上 | 6 | 无 |
| `history/debate_20260712_230440.json` | 人活着有没有意义 | 同上 | 6 | 无 |

> 第 2-4 份**正文完全相同**（同题同参数同 6 条发言，仅 `timestamp` 不同）= 同一场辩论的三次保存，不是三场不同辩论（见 §5-5）。

## §1 字段映射表

### 1.1 顶层字段

| 旧 JSON 字段 | 现存取值 | 新 schema 目标 | 处置 | 说明 |
|---|---|---|---|---|
| `topic` | 见 §0 | `sessions.topic`（VARCHAR 200） | **可映射** | 直接写入；两份辩题均远小于 200 字符 |
| `mode` | "AI vs AI" | 无对应列 | **忽略**（查看器呈现为 "debate"） | sessions 无 mode 列；新系统本质是人机论证训练，无 AI 对战模式列（见 §5-2 与 §6-1） |
| `max_turns` | 2 | 无对应列 | **忽略** | 新系统无轮次上限列（流程控制由 S2 编排器状态机承担） |
| `temperature` | 0.7（仅第 1 份） | 无对应列 | **忽略** | 新系统模型配置 = `MODEL_DEFAULT` 单环境变量，无温度列（见 §3） |
| `temp_zheng` / `temp_fan` | 0.5 / 0.4（第 2-4 份） | 无对应列 | **忽略** | 同上 |
| `model_zheng` / `model_fan` | 现存 4 份均无 | 无对应列 | **忽略** | 当前桌面版 `save_history` 会写入（`debate_ui.py:1627-1628`），未来存档可能有；无新系统目标列 |
| `model_judge` | 现存 4 份均无 | 无对应列 | **忽略** | 详见 §3 |
| `history[]` | 6 或 9 条 | `messages` 表多行 | **需转换** | 逐条映射，见 §1.2 |
| `timestamp` | "20260710_202313" | `sessions.created_at` | **需转换** | 格式 `YYYYMMDD_HHMMSS`，无时区，按本地时间 `datetime.strptime(s, "%Y%m%d_%H%M%S")` 解析 |

### 1.2 `history[]` 元素 → `messages` 行

| 旧字段 | 取值 | `messages.role` | `messages.agent_role` | `messages.content` | 处置 |
|---|---|---|---|---|---|
| `role="正方"` | 全场 | `'assistant'` | `'pro'` | 原 content 直接映射 | 正方辩手=AI 对手之一 |
| `role="反方"` | 全场 | `'assistant'` | `'con'` | 同上 | |
| `role="裁判"` | 仅第 1 份 | `'assistant'` | `'judge'` | 同上 | 裁判=AI |
| `role="正方"` 且 `phase="用户发言"` | 现存 4 份无 | `'user'` | NULL | 同上 | 人机模式存档的学生发言分支（桌面版 `load_history` 按 `phase=="用户发言"` 区分渲染样式，`debate_ui.py:1654`）；新系统 `role='user'` 即学生 |
| `phase` | 开场陈词/辩论阶段/辩论阶段1/总结陈词/评判 | — | — | — | messages 无 phase 列，见 §2-4 |
| `content` | 长文本（含换行、引号） | — | — | TEXT | 原样写入，无需转义 |

### 1.3 派生字段（真导入时生成，查看器不涉及）

| 新列 | 取值 | 依据 |
|---|---|---|
| `sessions.visibility` | `'private'` | 存档无课程任务归属；应用层 `validate_session_visibility()` 要求 private ⇒ task_id 为空（errata E-2） |
| `sessions.status` | `'finished'` | 存档即已完成的辩论（sessions.status 五枚举之一） |
| `messages.status` | `'complete'` | 存档内容均为完成态，无流式截断（messages.status 三枚举，errata E-3） |
| `messages.seq` | 全局交错分配 | 方案 A：seq 即主键、全局自增（errata E-1）；不每会话从 1 连续 |

## §2 版本差异处理

1. **两种 temperature 形态**：形态 A（第 1 份）= 顶层单一 `temperature`；形态 B（第 2-4 份）= 分角色 `temp_zheng`/`temp_fan`。两种均无新系统目标列，统一处置为忽略（原值保留在原 JSON 文件与查看器展示中）。
2. **形态 C（当前桌面存档代码）**：`save_history`（`debate_ui.py:1621-1632`）写 `model_zheng`/`model_fan`/`model_judge` 三字段，现存 4 份存档生成于该代码之前故无此三字段。映射表已覆盖：三字段均无目标列，忽略；`model_judge` 的特殊语义见 §3。
3. **role 中文 → agent_role 英文枚举**：正方→`pro`、反方→`con`、裁判→`judge`（E-5 的 assistant 四细分枚举之三，第四值 `coach` 旧存档不用）。同时 `role` 列一律取 `'assistant'`——旧存档三方均为 AI；`role='user'` 仅用于人机模式存档的学生发言分支（§1.2 末行）。
4. **phase 无目标列**：messages 表无 phase 字段。两种处置——**真导入（S5+）**：仅在阶段切换时插入一条 `role='system'` 消息（content=`进入阶段：开场陈词` 等），不逐条前缀，避免污染 content；**MVP 查看器**：phase 作为消息分组标题渲染，不落库。phase 实际取值集合：{开场陈词, 辩论阶段, 辩论阶段1, 总结陈词, 评判}——"辩论阶段"（第 1 份）与"辩论阶段1"（第 2-4 份）为同一阶段的编号变体，映射时按前缀归并为同一阶段。

## §3 model_judge 处理

`model_judge` 是桌面版配置项（`debate_ui.py:39` `self.model_judge = tk.StringVar(value="qwen3.5:4b")`，UI 滑块/输入框的"裁判模型"配置变量；`save_history` 写入 JSON、`load_history` 读回），**旧 JSON 不含此字段**（现存 4 份存档均无）。**新系统对应 `MODEL_DEFAULT` 环境变量**（`backend/.env`，当前值 `cline/deepseek/deepseek-v4-pro`，见 `docs/deploy.md` §4；新系统为单一默认模型，无 per-role 模型配置，各 stage 的模型选择属 S2 范围，落 `docs/model_selection.md`）。映射结论：真导入时存档内无模型来源可写，全部消息的服务端模型即 `MODEL_DEFAULT`，不区分正/反/裁；`temperature` 同理无来源，使用 `model_provider.generate_stream` 的默认温度（`backend/app/core/model_provider.py`，默认 0.7）。

## §4 导入策略

- **MVP（S1 范围）：只设计映射 + 只读查看器，不做真导入。** 查看器 = 读一份旧 JSON 渲染为 messages 列表（按 agent_role 分栏/配色、phase 分组标题、顶部展示 topic/timestamp/桌面版参数），纯前端渲染不落 DB。
- **不实现真导入的理由**（超出 MVP 复杂度）：需创建 session（owner 归属：旧数据无用户身份；visibility/task_id 校验；status 状态机）、seq 按方案 A 全局交错分配（errata E-1）、时间戳处理（原 timestamp 还是导入时刻）、messages 批量插入与 `UNIQUE(session_id, seq)` 约束。
- **真导入功能是 S5 或后续版本的范围**（方案 §4.4"迁移为训练会话、观点版本和复盘记录"）。真导入时的开放问题留 S5 定：①"观点版本"从何而来（闭幕陈词？裁判总结？）；②"复盘记录"从何而来（裁判条目？但第 1 份裁判为拒答，见 §5-4）；③owner 归属与 `visibility`；④时间戳口径。

## §5 已知坑

1. **pwsh 默认编码读 UTF-8 JSON 会乱码**——导入脚本/查看器数据层必须显式 `-Encoding UTF8`（pwsh `Get-Content`）或 python `open(..., encoding="utf-8")`（桌面版 `save_history` 本身即 utf-8 写出，`debate_ui.py:1620`；S1-11 素材盘点时实测确认乱码现象）。
2. **mode 全为 "AI vs AI"**（桌面版不含人机模式）——新系统无 sessions.mode 列，导入时该值丢弃，查看器按 "debate" 呈现（落点待确认，见 §6-1）。
3. **phase 字段新 schema 没有**——处置见 §2-4（真导入=阶段切换插 system 消息；查看器=分组标题）。
4. **裁判条目可能是模型拒答**——第 1 份存档的裁判内容拒绝评判该辩题（伦理拒答而非裁决），查看器/真导入均不得将其当作评判结论展示。
5. **第 2-4 份存档正文重复**（仅 timestamp 不同）——查看器按文件粒度独立渲染即可，无需去重，但 UI 上应显示各自 timestamp 避免误认为三场辩论。
6. **timestamp 无时区**——文件名与 JSON 内 `timestamp` 均编码本地时间（`YYYYMMDD_HHMMSS`），解析按本地时区；真导入写入 `created_at` 时同样无时区语义，与全局 DATETIME 约定一致。
7. **重复存档去重（真导入时）**：第 2-4 份重复存档（同题同参数同 6 条发言，仅 timestamp 不同）在真导入时需去重——建议策略：按 (topic, history[] 内容 hash) 去重，保留最早 timestamp 或用户指定的那一份。MVP 查看器不去重（按文件粒度独立渲染），但 UI 应标注'此三条疑为同场辩论的多次保存'。
8. **极端议题触发模型拒答的议题范围启示**：极端议题触发模型拒答（第 1 份'人该不该活着'的裁判条目为伦理拒答）——不仅影响查看器语义标注，也说明桌面版在这类议题上无法产出有效训练内容。新系统的议题范围界定（S2 或产品设计层）应显式排除此类议题，或在 MVP 加'拒答检测 + 提示用户换议题'机制。此项列入 S2 或产品待办，不在 S1-11 范围。

## §6 裁定记录（用户 2026-10-13 审阅）

1. **mode → "debate" 落点**：接受查看器呈现层（契约无 sessions.mode 列）。**真导入（S5）时在 `audit_events.detail` 记 `{"source":"legacy_desktop","original_mode":"AI vs AI"}`**，保数据来源可追溯，不污染 sessions 表。
2. **真导入开放问题全留 S5**：接受——§4 四个问号（观点版本/复盘记录来源、owner 归属、时间戳口径）S1-11 只登记不展开，全部留给 S5 任务书。
3. **查看器原型**：裁定做——`docs/prototypes/legacy_import.html`（读一份 JSON 渲染 messages 列表、phase 作分组标题、裁判拒答加警示标、第 2-4 份重复存档 UI 标注'疑为同场辩论的多次保存'），作为 S1-11 收口追加小任务；commit 归属裁定为**单独 commit `[S1-11] docs: 旧 JSON 存档只读查看器原型`**（文件虽是 S1-10 原型目录的延伸，任务归属为 S1-11）。
