# 数据契约草案 v3：消息与记录五表（S1-4 范围）

> **状态：DRAFT —— 等待用户审阅，审阅通过前不得据此写 ORM。**
> 范围：`messages` / `revisions` / `reports` / `feedback_forms` / `audit_events`
> 五张表（任务卡 S1-4，见执行计划书 v1.0）。全局约定沿用 `schema_v1.md` §0。
> **前置拍板**：`messages.seq` 的方案 A/B 见 `schema_v2_tasks.md` 焦点二
> （推荐 A：seq 即主键、无独立 id）。本草案按**方案 A** 行文；
> 若你选 B，仅 messages 表首两行定义不同，其余不变。

## 表 1：`messages`（消息流，契约 5.1/5.2/5.4）

| 列 | 依据 | 说明 |
|---|---|---|
| `seq` BIGINT PK AUTO_INCREMENT | 有明确依据（契约 5.1，方案 A） | 会话内单调序号即主键；对 API 即 message id；回放 `WHERE session_id=? AND seq>?` 走下面的复合索引 |
| `session_id` BIGINT NOT NULL, FK→`sessions.id` ON DELETE CASCADE | 有明确依据（契约 5.1） | 删会话级联删消息 |
| `role` ENUM('user','assistant','system') NOT NULL | 有明确依据（契约 5.1"区分发言方/系统消息"） | 'user'=学生，'assistant'=AI（正/反方/裁判复用同一值，角色名在消息内容/上层 API 里区分），'system'=阶段切换/状态提示 |
| `content` TEXT NOT NULL | 有明确依据 | 暂停续写时整条重写（契约 5.2："追加新 chunk 到同一 DB 行"） |
| `status` ENUM('streaming','complete','paused_truncated') NOT NULL DEFAULT 'streaming' | 有明确依据（契约 5.2/5.4） | SSE 在途=`streaming`；正常完成=`complete`；暂停截断=`paused_truncated`（契约 5.2 原文用词）；**注意**：契约 5.4 重连示例写的 `status='generating'` 与 5.2 的 `paused_truncated` 不统一，勘误统一为 `streaming`（生成中）——见下方"勘误清单" |
| `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP | 全局约定 | |
| `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP | 有明确依据（契约 5.2 续写时间线） | 续写续时刷新 |
| `UNIQUE(session_id, seq)` + 该复合索引作回放主索引 | 有明确依据（契约 5.1；方案 A 下唯一性已蕴含，索引仍保留作覆盖索引，见 v2 焦点二） | 计划书 S1-4 验收句"(session_id, seq) 重复插入被拒"两方案下都成立 |

## 表 2：`revisions`（观点修改稿，S2-11/S4）

| 列 | 依据 | 说明 |
|---|---|---|
| `id` BIGINT PK AUTO_INCREMENT | 表骨架 | |
| `session_id` BIGINT NOT NULL, FK→`sessions.id` ON DELETE CASCADE | 行业惯例（观点稿挂练习会话；无更细契约） | |
| `student_id` BIGINT NOT NULL, FK→`users.id` ON DELETE CASCADE | 行业惯例 | 冗余于 session.owner_id，理由同 v2 焦点三（越权检查免 join） |
| `content` TEXT NOT NULL | 有明确依据（S2-11"草稿保存"+"修改稿"） | 初稿与每版修改稿各一行 |
| `version` INT NOT NULL | 行业惯例 | 从 1 递增；`UNIQUE(session_id, version)` |
| `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP | 全局约定 | "两版本可查"直接按 version 排序 |

**待勾选**：

- [ ] `status` ENUM('draft','final') NOT NULL DEFAULT 'draft' —— S2-11"草稿保存"与"提交定稿"是两态；
      **建议加**：S4 要"复用学生提交的原观点作对比"，需要区分哪版是定稿

## 表 3：`reports`（复盘报告，S1-9/S2-10）

| 列 | 依据 | 说明 |
|---|---|---|
| `id` BIGINT PK AUTO_INCREMENT | 表骨架 | |
| `session_id` BIGINT NOT NULL, FK→`sessions.id` ON DELETE CASCADE | 有明确依据（报告属于会话） | |
| `rubric_version` VARCHAR(20) NOT NULL | 行业惯例 | 报告生成时的量表快照标识（S1-9 rubric.json 版本）；量表改版后旧报告仍可解释 |
| `scores` JSON NOT NULL | 有明确依据（S1-9"四维度+权重"、S2-10"量表四维+依据引用"） | `{"维度名": {"score": 82, "weight": 0.3, "evidence": ["会话内引用"]}}`；用 JSON 而非四列，量表维度增删不改表结构 |
| `overall_score` DECIMAL(5,2) NOT NULL | 有明确依据（S2-10"报告含分"；S3-5 汇总要按分统计） | 加权总分冗余列，免每次 JSON 计算 |
| `summary_text` TEXT NOT NULL | 有明确依据（报告正文） | 结论段落 |
| `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP | 全局约定 | |

**待勾选**：

- [ ] `UNIQUE(session_id)` —— 一次会话只存一份最终报告（重跑复盘=覆盖/新版本？）
      —— **建议不加唯一约束**：首版允许重跑生成新报告行，`created_at` 最新者为当前版；
      S3-5 取"每会话最新一份"。若你想强制一版，S2-10 实现要先删旧行，等你表态

## 表 4：`feedback_forms`（学生反馈，S3-5）

| 列 | 依据 | 说明 |
|---|---|---|
| `id` BIGINT PK AUTO_INCREMENT | 表骨架 | |
| `task_id` BIGINT NOT NULL, FK→`tasks.id` ON DELETE CASCADE | 行业惯例（反馈以任务为对象；无更细契约） | |
| `student_id` BIGINT NOT NULL, FK→`users.id` ON DELETE CASCADE | 行业惯例 | |
| `scores` JSON NOT NULL | 行业惯例 | 分项评分（如"题目难度/教练帮助/时间安排"），具体维度 S3 实现定，JSON 免锁死 |
| `comment` TEXT NULL | 行业惯例 | 开放意见 |
| `submitted_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP | 行业惯例 | |
| `UNIQUE(task_id, student_id)` | 行业惯例 | 一生一任务一份反馈 |

> ⚠️ 本表在方案与任务卡中只出现表名（S3-5"反馈表汇总"），无字段级描述，
> 整表为行业惯例起草。若你对反馈内容有具体设计（如问卷题目固定），审阅时提出。

## 表 5：`audit_events`（审计留痕，S3-1/S3-6）

| 列 | 依据 | 说明 |
|---|---|---|
| `id` BIGINT PK AUTO_INCREMENT | 表骨架 | |
| `actor_id` BIGINT NULL, FK→`users.id` ON DELETE SET NULL | 行业惯例 | 操作者；删账号后留痕不删（SET NULL 保事件、断链人）；NULL=系统动作 |
| `action` VARCHAR(64) NOT NULL | 有明确依据（S3-1"留痕"、S3-6"敏感操作"） | 如 `user.login` / `user.deactivate` / `role.grant` / `task.create` / `submission.view` |
| `target_type` VARCHAR(32) NULL | 行业惯例 | 如 `user`/`task`/`session` |
| `target_id` BIGINT NULL | 行业惯例 | |
| `detail` JSON NULL | 行业惯例 | 变更前后值/上下文（S3-6 强调"不记录敏感数据"，密码/密钥永不入此列——实现层约束） |
| `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP | 全局约定 | 建 `(created_at)` 索引供按时间审计查询 |

**待勾选**：

- [ ] `ip` VARCHAR(45) NULL —— 登录留痕常要 IP（IPv6 45 位）；**建议加**（S3-1 登录操作留痕的常见最低要求），但方案未明示，等你表态

---

## 勘误清单（你确认草案后，我改 v1.1 契约时一并执行）

1. **契约 5.4/5.2 状态值不统一**：5.2 定义 `paused_truncated`，5.4 重连示例写 `status='generating'`。
   统一为三值枚举 `streaming`/`complete`/`paused_truncated`，5.4 示例改 `streaming`。
2. **契约 5.1 seq 两句矛盾**：按 schema_v2 焦点二勘误（方案 A 或 B，等你拍板）。
3. **契约 5.3 CHECK**：按 schema_v2 焦点一勘误为"应用层强制"（等你确认）。

## 范围外

- tasks / task_submissions / sessions → `schema_v2_tasks.md`（S1-3 草案，同批审阅）
- 图谱三表 → S4 草案
- teacher 角色的审计细则（哪些动作必留痕）→ S3-1 实现时定，表结构已支持
