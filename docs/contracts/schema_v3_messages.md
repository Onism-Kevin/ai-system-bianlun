# 数据契约定稿 v3：消息与记录五表（S1-4 范围）

> **状态：FINAL（用户 2026-10-12 批准，S1-5 迁移一致性验证通过后转正；此后改任何字段 = 新 migration + 数据迁移脚本）**——seq=方案 A、messages.status 三值枚举、
> 新增 agent_role 列、revisions.status 加、audit_events.ip 加、reports 不加唯一约束。
> 对 v1.1 的取代声明集中记录在 `errata.md`（E-1/E-3/E-5），v1.1 原文不改写。
> 范围：`messages` / `revisions` / `reports` / `feedback_forms` / `audit_events` 五张表（任务卡 S1-4）。
> 全局约定沿用 `schema_v1.md` §0。**前置**：`sessions` 定义见 `schema_v2_tasks.md`。

## 取代声明（对应 errata.md）

- **本定稿取代 v1.1 契约 5.4 示例中的 `status='generating'`**：以本定稿三值枚举
  `streaming` / `complete` / `paused_truncated` 为准（E-3）。
- **本定稿取代 v1.1 契约 5.1 的 seq 两句矛盾表述**：以方案 A 为准
  （seq 即主键、无独立 id，E-1）。

## 表 1：`messages`（消息流，契约 5.1/5.2/5.4）

| 列 | 依据 | 说明 |
|---|---|---|
| `seq` BIGINT PK AUTO_INCREMENT | 有明确依据（契约 5.1，方案 A） | 会话内单调序号即主键；对 API 即 message id；会话内单调由"全局单调序列的子序列仍单调"保证（各会话 seq 交错分配，非每会话从 1 连续）；回放 `WHERE session_id=? AND seq>?` 走复合索引 |
| `session_id` BIGINT NOT NULL, FK→`sessions.id` ON DELETE CASCADE | 有明确依据（契约 5.1） | 删会话级联删消息 |
| `role` ENUM('user','assistant','system') NOT NULL | 有明确依据（契约 5.1"区分发言方/系统消息"） | 'user'=学生，'assistant'=AI，'system'=阶段切换/状态提示 |
| `agent_role` VARCHAR(16) NULL | **用户拍板必加**（errata E-5，补充 1） | assistant 细分：`'pro'`/`'con'`/`'judge'`/`'coach'`；user/system 消息此列为 NULL。前端按角色渲染（颜色/图标）、S4 图谱按来源区分、S2-9 区分"教练 vs 辩论对手"都需要——高频查询字段不进 detail JSON |
| `content` TEXT NOT NULL | 有明确依据 | 暂停续写时同一行重写（契约 5.2"追加新 chunk 到同一 DB 行"） |
| `status` ENUM('streaming','complete','paused_truncated') NOT NULL DEFAULT 'streaming' | 有明确依据（契约 5.2/5.4 + E-3 统一） | SSE 在途=`streaming`；正常完成=`complete`；暂停截断=`paused_truncated`（契约 5.2 原文用词） |
| `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP | 全局约定 | |
| `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP | 有明确依据（契约 5.2 续写时间线） | 续写续时刷新 |
| `UNIQUE(session_id, seq)` 复合索引 | 有明确依据（契约 5.1；方案 A 下唯一性已蕴含，保留作回放覆盖索引） | S1-4 验收句"(session_id, seq) 重复插入被拒"成立 |

## 表 2：`revisions`（观点修改稿，S2-11/S4）

| 列 | 依据 | 说明 |
|---|---|---|
| `id` BIGINT PK AUTO_INCREMENT | 表骨架 | |
| `session_id` BIGINT NOT NULL, FK→`sessions.id` ON DELETE CASCADE | 行业惯例（观点稿挂练习会话） | |
| `student_id` BIGINT NOT NULL, FK→`users.id` ON DELETE CASCADE | 行业惯例 | 冗余于 session.owner_id，越权检查免 join（同 v2 焦点三哲学） |
| `content` TEXT NOT NULL | 有明确依据（S2-11"草稿保存"+"修改稿"） | 初稿与每版修改稿各一行 |
| `version` INT NOT NULL | 行业惯例 | 从 1 递增；`UNIQUE(session_id, version)` |
| `status` ENUM('draft','final') NOT NULL DEFAULT 'draft' | **用户拍板加**（errata E-5） | 区分草稿与定稿；S4"复用学生提交的原观点作对比"需要知道哪版是定稿 |
| `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP | 全局约定 | "两版本可查"按 version 排序 |

## 表 3：`reports`（复盘报告，S1-9/S2-10）

| 列 | 依据 | 说明 |
|---|---|---|
| `id` BIGINT PK AUTO_INCREMENT | 表骨架 | |
| `session_id` BIGINT NOT NULL, FK→`sessions.id` ON DELETE CASCADE | 有明确依据（报告属于会话） | |
| `rubric_version` VARCHAR(20) NOT NULL | 行业惯例 | 报告生成时的量表快照标识（S1-9 rubric.json 版本）；量表改版后旧报告仍可解释 |
| `scores` JSON NOT NULL | 有明确依据（S1-9"四维度+权重"、S2-10"量表四维+依据引用"） | `{"维度名": {"score": 82, "weight": 0.3, "evidence": ["会话内引用"]}}`；JSON 免锁死维度增删 |
| `overall_score` DECIMAL(5,2) NOT NULL | 有明确依据（S2-10"报告含分"；S3-5 按分统计） | 加权总分冗余列，免每次 JSON 计算 |
| `summary_text` TEXT NOT NULL | 有明确依据（报告正文） | 结论段落 |
| `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP | 全局约定 | |

> **用户拍板不加**：~~UNIQUE(session_id)~~（errata E-5）——允许重跑复盘生成新报告行，
> `created_at` 最新者为当前版；S3-5 取"每会话最新一份"。

## 表 4：`feedback_forms`（学生反馈，S3-5）

| 列 | 依据 | 说明 |
|---|---|---|
| `id` BIGINT PK AUTO_INCREMENT | 表骨架 | |
| `task_id` BIGINT NOT NULL, FK→`tasks.id` ON DELETE CASCADE | 行业惯例（反馈以任务为对象） | |
| `student_id` BIGINT NOT NULL, FK→`users.id` ON DELETE CASCADE | 行业惯例 | |
| `scores` JSON NOT NULL | 行业惯例 | 分项评分，具体维度 S3 实现定，JSON 免锁死 |
| `comment` TEXT NULL | 行业惯例 | 开放意见 |
| `submitted_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP | 行业惯例 | |
| `UNIQUE(task_id, student_id)` | 行业惯例 | 一生一任务一份反馈 |

> ⚠️ 本表在方案与任务卡中只出现表名（S3-5"反馈表汇总"），无字段级描述，
> 整表为行业惯例起草。若对反馈内容有具体设计（如问卷题目固定），S3 实现前提出。

## 表 5：`audit_events`（审计留痕，S3-1/S3-6）

| 列 | 依据 | 说明 |
|---|---|---|
| `id` BIGINT PK AUTO_INCREMENT | 表骨架 | |
| `actor_id` BIGINT NULL, FK→`users.id` ON DELETE SET NULL | 行业惯例 | 操作者；删账号后留痕保留（SET NULL 断链人、保事件）；NULL=系统动作 |
| `action` VARCHAR(64) NOT NULL | 有明确依据（S3-1"留痕"、S3-6"敏感操作"） | 如 `user.login` / `user.deactivate` / `role.grant` / `task.create` / `submission.view` |
| `target_type` VARCHAR(32) NULL | 行业惯例 | 如 `user`/`task`/`session` |
| `target_id` BIGINT NULL | 行业惯例 | |
| `detail` JSON NULL | 行业惯例 | 变更前后值/上下文（S3-6"不记录敏感数据"：密码/密钥永不入此列——实现层约束） |
| `ip` VARCHAR(45) NULL | **用户拍板加**（errata E-5） | IPv6 上限 45 位；登录留痕常用 |
| `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP | 全局约定 | 建 `(created_at)` 索引供按时间审计查询 |

## 范围外

- tasks / task_submissions / sessions → `schema_v2_tasks.md`（S1-3 定稿）
- 图谱三表 → S4 草案
- teacher 角色的审计细则（哪些动作必留痕）→ S3-1 实现时定，表结构已支持
