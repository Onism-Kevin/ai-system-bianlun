# 数据契约定稿 v2：任务与练习三表（S1-3 范围）

> **状态：FINAL（用户 2026-10-12 批准，S1-5 迁移一致性验证通过后转正；此后改任何字段 = 新 migration + 数据迁移脚本）**——焦点一=应用层强制、焦点二=方案 A、焦点三=student_id 为 FK；
> 对 v1.1 的取代声明集中记录在 `errata.md`（E-1/E-2/E-4/E-5），v1.1 原文不改写。
> 范围：`tasks` / `task_submissions` / `sessions` 三张表（任务卡 S1-3）。
> 全局约定（utf8mb4 / 时间列 / 约束命名表名在前 / 布尔 tinyint(1)）沿用 `schema_v1.md` §0。

## 三个焦点问题的定稿结论（论证过程见草案评审记录）

1. **visibility 校验 = 应用层强制**（errata E-2）：DB 不加 CHECK；
   `validate_session_visibility()` 强制 `visibility='task' ⇔ task_id 非空`。
   理由：DB CHECK 报错不友好、加第三态要 ALTER、跨表存在性本就得应用层查。
   （MySQL 8.4.9 CHECK 可用——8.0.16+——但纯权衡不采用；想加纵深防御可后补。）
2. **messages.seq = 方案 A**（errata E-1，S1-4 落地）：seq 即主键，无独立 id；
   会话内单调由"全局单调序列的子序列仍单调"保证，各会话 seq 交错分配
   （A 得 1,3,5；B 得 2,4），回放按 `(session_id, seq)` 排序严格正确。
3. **task_submissions.student_id = FK**（`users.id`，ON DELETE CASCADE）：
   越权检查免 join sessions、删账号级联清理、DB 层杜绝孤儿提交。

## 表 1：`tasks`（任务）

| 列 | 依据 | 说明 |
|---|---|---|
| `id` BIGINT PK AUTO_INCREMENT | 表骨架 | |
| `course_id` BIGINT NOT NULL, FK→`courses.id` ON DELETE RESTRICT | 有明确依据 | 任务属于课程（S3-2 建课后创建任务）；RESTRICT = 不允许删带任务的课程（MVP 无删课 API，课程走归档，防误删数据） |
| `title` VARCHAR(120) NOT NULL | 有明确依据 | 任务创建页表单字段（长度 120 为起草值） |
| `material` TEXT NULL | 有明确依据 | 任务卡"材料上传"；MVP 形式=文本粘贴（文件上传超首版，S3-2 若要文件再加列） |
| `join_code` VARCHAR(8) NULL UNIQUE | 有明确依据 | 任务级加入码（S3-3 错码 403 验收）；生成规则同 v1：6~8 位 A-Z0-9 剔除 I/O/0/1；NULL=不需要加入码（MySQL UNIQUE 允许多个 NULL） |
| `deadline` DATETIME NULL | **用户拍板加**（errata E-5） | 教学常用（学生端倒计时）；NULL=不限时 |
| `is_archived` TINYINT(1) NOT NULL DEFAULT 0 | **用户拍板加**（errata E-5） | 归档不删任务；MVP 无删任务 API，防将来返工 |
| `created_at` / `updated_at` | 全局约定 | |

## 表 2：`task_submissions`（提交）

| 列/约束 | 依据 | 说明 |
|---|---|---|
| `id` BIGINT PK AUTO_INCREMENT | 表骨架 | |
| `student_id` BIGINT NOT NULL, FK→`users.id` ON DELETE CASCADE | 有明确依据 + 用户拍板（焦点三） | 提交人=会话 owner；越权检查直查此列 |
| `task_id` BIGINT NOT NULL, FK→`tasks.id` ON DELETE CASCADE | 有明确依据 | 任务删除时其提交记录一并删除（防孤儿） |
| `session_id` BIGINT NOT NULL, FK→`sessions.id` ON DELETE CASCADE | 有明确依据（契约 5.3） | 提交会话；UNIQUE 约束第二列 |
| `submitted_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP | 有明确依据（契约 5.3） | |
| `UNIQUE(task_id, session_id)` | 有明确依据（契约 5.3） | 同一会话不能重复提交到同一任务 |
| `UNIQUE(task_id, student_id)` | **用户拍板加**（errata E-5） | 一个学生对一个任务只能有一份提交 |

> **UNIQUE(task_id, student_id) 的连带语义（用户补充 2）**：加此键后学生换会话重做任务
> 会被 DB 拒绝，而产品允许重做 → **S3-4 提交 API 必须 upsert**：
> `INSERT … ON DUPLICATE KEY UPDATE session_id=?, submitted_at=?`
> （或先 DELETE 旧行再 INSERT）。已写入计划书 S3-4 任务备注。
> **用户拍板不加**：~~score / teacher_comment~~（未被要求的人工评分不发明）。

## 表 3：`sessions`（练习会话）

| 列 | 依据 | 说明 |
|---|---|---|
| `id` BIGINT PK AUTO_INCREMENT | 表骨架 | |
| `owner_id` BIGINT NOT NULL, FK→`users.id` ON DELETE CASCADE | 有明确依据 | "个人练习（visibility='private'）仅 owner 可见"（契约 5.3）；删账号级联删其会话 |
| `topic` VARCHAR(200) NOT NULL | 有明确依据 | 五阶段以议题为输入（拆解起点）；长度 200 为起草值 |
| `visibility` ENUM('private','task') NOT NULL DEFAULT 'private' | 有明确依据（契约 5.3） | 校验=应用层 `validate_session_visibility()`（E-2）；**DB 层故意不设 CHECK** |
| `task_id` BIGINT NULL, FK→`tasks.id` ON DELETE CASCADE | 有明确依据（契约 5.3） | `visibility='task'` 时非空（应用层校验）；任务删除时其练习会话一并删除 |
| `status` ENUM('waiting','generating','paused','finished','failed') NOT NULL DEFAULT 'waiting' | 有明确依据 | S2-2 状态机五态 + S2-12"列表含状态/时间"必须落库；应用层在状态转移时写入 |
| `created_at` / `updated_at` | 全局约定 | 列表"时间"列直接取这两列 |

> **用户拍板不加**：~~会话级冗余分数列~~（列表契约只要状态/时间，join reports 成本可忽略）。

**教师可见性**（S3 实现层规则，记录防丢）：教师可见其课程任务下 `task_submissions`
引用的会话（"提交后教师可见；未提交不可见"，S3-4），不扫全部 task 会话。

## 应用层校验函数（S1-3 一并交付）

`validate_session_visibility(visibility: str, task_id: int | None) -> None`
（置于 `backend/app/models/session.py`）：`visibility='task'` 时 task_id 必须非空，
`'private'` 时 task_id 必须为空，违反抛 `ValueError`。S1-3 验收即测此函数
（DB 无 CHECK 是 E-2 的定稿行为，不是缺陷）。

## 删除语义汇总

```
users ──(CASCADE)──> sessions ──(CASCADE)──> task_submissions（S1-4 起还有 messages）
users ──(CASCADE)──> task_submissions
courses ──(RESTRICT)──< tasks ──(CASCADE)──< sessions / task_submissions
```

## 已否决项（留档，详见 errata E-5）

tasks.score？无此项——否决的是：task_submissions.score/teacher_comment、
sessions 冗余分数列、reports.UNIQUE(session_id)（允许重跑取最新）。

## 范围外

- messages / revisions / reports / feedback_forms / audit_events → `schema_v3_messages.md`（S1-4 定稿）
- 图谱三表（argument_nodes / argument_edges / evidence_sources）→ S4 范围，届时另出草案
