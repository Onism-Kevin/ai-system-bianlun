# 用户与课程域数据模型 v1 — FINAL

> 状态：**FINAL（用户 2026-10-12 确认 S1-5 迁移一致性验证通过后转正；此后改任何字段 = 新 migration + 数据迁移脚本）**。
> 勾选结论（2026-10-12）：加 display_name / is_active / 'admin' 枚举 / user_roles.created_at / courses.term；
> 不加 student_no / email / last_login_at。
>
> 依据来源：
> - 《思辨工坊执行计划书 v1.1》任务卡：S2-1（register/login/me + JWT + bcrypt）、S3-1（角色管理 API）、S3-2（课程创建 + 成员 API，建课→学生加入闭环）、S3-3（任务创建 + 加入码 + join API，错码 403）
> - v1.1 技术契约：5.1（`seq BIGINT AUTO_INCREMENT` 风格）、5.3（`task_submissions.student_id` 引用 users、"教师/管理员"字样）
> - 你提供的四表骨架（本会话指令）
>
> 方案第 10 节只有表名 + 一句话描述，字段级定义由本草案首次提出。每表分两栏：
> **有明确依据**（方案功能 / 任务卡 / 技术契约 / 你的骨架直接支撑，无异议即采纳）与
> **行业惯例补充**（逐条勾选，`[ ]` 保持未勾 = 不采纳）。

## 0. 全局约定

| 约定 | 取值 | 说明 |
|---|---|---|
| 主键 | `id BIGINT AUTO_INCREMENT PRIMARY KEY` | 与契约 5.1 风格一致；`task_submissions.student_id` 等跨表引用要求 BIGINT |
| 时间类型 | `DATETIME`（不用 TIMESTAMP） | 避开 2038 上限；默认值 `CURRENT_TIMESTAMP`；`updated_at` 由应用层 SQLAlchemy `onupdate` 维护，**DB 层不加 `ON UPDATE CURRENT_TIMESTAMP`**（errata E-7） |
| 字符集/排序 | utf8mb4 / utf8mb4_unicode_ci | S0-9 已定，三库一致 |
| 删除语义 | 不用 `deleted_at` 软删；账号用 `is_active`、课程用 `is_archived` | 骨架已有；减少状态维度 |
| 角色存储 | `ENUM`（非 lookup 表） | 值少且稳定；方案未要求动态角色 |
| 约束/索引命名 | `pk_<表名>` / `uq_<表名>_<列名>` / `ix_<表名>_<列名>` / `fk_<表名>_<列名>_<被引用表>` / `ck_<表名>_<约束名>` —— **一律表名在前** | 与 `backend/app/models/base.py` 的 `NAMING_CONVENTION` 完全一致（实测产物如 `users.uq_users_username`）；复合唯一键为 `uq_<表名>_<列1>_<列2>`（如 `uq_user_roles_user_id_role`）；FK 列建索引，UNIQUE 列天然有索引 |

## 1. users

### 1.1 有明确依据

| 字段 | 类型 | 约束 | 依据 |
|---|---|---|---|
| `id` | BIGINT | PK AUTO_INCREMENT | 全局约定；契约 5.3 跨表引用 |
| `username` | VARCHAR(50) | NOT NULL, UNIQUE | S2-1 register/login 的登录唯一标识。**规则说明**：username 的字符集/长度/允许字符规则由 S2-1（register API）定义，本表 VARCHAR(50) 只提供存储上限 |
| `password_hash` | VARCHAR(255) | NOT NULL | S2-1 bcrypt（bcrypt 输出 60 字符，255 留算法升级余量） |
| `created_at` | DATETIME | NOT NULL DEFAULT CURRENT_TIMESTAMP | 你的骨架；审计基础列 |
| `updated_at` | DATETIME | NOT NULL DEFAULT CURRENT_TIMESTAMP | 同上；DB 层无 ON UPDATE，由应用层 `onupdate` 刷新（errata E-7） |

### 1.2 行业惯例补充（已勾选定稿 2026-10-12）

- [x] `display_name` VARCHAR(50) NULL — 界面显示名（教师真名/学生昵称），登录仍用 username。**已采纳：加**
- [x] `is_active` TINYINT(1) NOT NULL DEFAULT 1 — 账号停用（毕业/离校），停用即拒登录。**已采纳：加**
- [ ] ~~`student_no`~~ — **已否决：不加**
- [ ] ~~`email`~~ — **已否决：不加**
- [ ] ~~`last_login_at`~~ — **已否决：不加**

## 2. user_roles

### 2.1 有明确依据

| 字段 | 类型 | 约束 | 依据 |
|---|---|---|---|
| `id` | BIGINT | PK AUTO_INCREMENT | 你的骨架 |
| `user_id` | BIGINT | NOT NULL, FK→users.id ON DELETE CASCADE | 你的骨架；S3-1 角色授予 |
| `role` | ENUM('student','teacher','admin') | NOT NULL | 你的骨架；方案第 8 节第 1 条（同账号可多角色）；S3-1；契约 5.3 "教师/管理员"。**'admin' 纯预留，不代表首版实现管理员功能** |
| — | — | UNIQUE(user_id, role) | 你的骨架；方案第 8 节第 1 条（防止同角色重复授予） |

### 2.2 行业惯例补充（已勾选定稿 2026-10-12）

- [x] `role` 枚举增加 `'admin'` — **已采纳**（纯预留占位）
- [x] `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP — 角色授予时间审计。**已采纳：加**

## 3. courses

### 3.1 有明确依据

| 字段 | 类型 | 约束 | 依据 |
|---|---|---|---|
| `id` | BIGINT | PK AUTO_INCREMENT | 你的骨架 |
| `teacher_id` | BIGINT | NOT NULL, FK→users.id ON DELETE RESTRICT | 你的骨架；S3-2 建课（RESTRICT 语义见 §5） |
| `name` | VARCHAR(100) | NOT NULL | 你的骨架；S3-2 |
| `description` | TEXT | NULL | 你的骨架 |
| `invite_code` | VARCHAR(8) | NOT NULL, UNIQUE | 你的骨架；S3-2「建课→学生加入闭环」需要课程级加入码 |
| `created_at` | DATETIME | NOT NULL DEFAULT CURRENT_TIMESTAMP | 你的骨架 |
| `updated_at` | DATETIME | NOT NULL DEFAULT CURRENT_TIMESTAMP | 你的骨架；DB 层无 ON UPDATE，由应用层 `onupdate` 刷新（errata E-7） |
| `is_archived` | TINYINT(1) | NOT NULL DEFAULT 0 | 你的骨架（学期结束归档） |

### 3.2 行业惯例补充（已勾选定稿 2026-10-12）

- [x] `term` VARCHAR(20) NULL — 学年学期标签（如 "2026秋"）。**已采纳：加**（NULL 列预留）
- [ ] 多教师协同（如 course_teachers 关联表）— **已否决：不加**（不发明复杂关系）
- [x] `invite_code` 生成规则：6~8 位 `A-Z0-9`，剔除易混淆字符 `I/O/0/1` — 非 DB 字段问题，属 S3-3 实现约束。**已采纳**（写入 S3-3 任务说明）

## 4. course_members

### 4.1 有明确依据

| 字段 | 类型 | 约束 | 依据 |
|---|---|---|---|
| `id` | BIGINT | PK AUTO_INCREMENT | 你的骨架 |
| `course_id` | BIGINT | NOT NULL, FK→courses.id ON DELETE CASCADE | 你的骨架 |
| `user_id` | BIGINT | NOT NULL, FK→users.id ON DELETE CASCADE | 你的骨架 |
| `joined_at` | DATETIME | NOT NULL DEFAULT CURRENT_TIMESTAMP | 你的骨架 |
| — | — | UNIQUE(course_id, user_id) | 你的骨架（防重复加入） |

### 4.2 行业惯例补充（已勾选定稿 2026-10-12）

- [ ] ~~`left_at` 退课语义~~ — **已否决：不加**（方案无退课流程，需要时一行 ALTER）
- [x] 成员表不存教师行 — **已采纳**。教师身份一律查 `courses.teacher_id`，避免权限判断出现两个真相来源

## 5. 删除语义与关系（草案定稿即生效）

```
users 1──* user_roles        （删账号连带清角色）ON DELETE CASCADE
users 1──* course_members    （删账号连带清成员）ON DELETE CASCADE
users 1──* courses.teacher_id（有课教师不可直接删）ON DELETE RESTRICT
courses 1──* course_members  （删课连带清成员）ON DELETE CASCADE
```

- `courses.teacher_id` 用 RESTRICT：防止删教师账号后孤儿课无人管理；正确流程是先归档/转移课程再删账号
- 唯一键汇总：`users.username`、`user_roles(user_id, role)`、`courses.invite_code`、`course_members(course_id, user_id)`

**应用层约束（DB 层不做）**：

- 创建课程时，应用层必须校验 `courses.teacher_id` 对应用户拥有 `teacher` 角色；DB 层不做此约束（MySQL 不支持跨表 CHECK）。该约束由 S3-2（建课 API）落地。

## 6. 范围外与勘误

- **本草案只覆盖 S1-2 四表**。tasks / task_submissions / sessions 属 S1-3（届时同格式出草案）；messages / revisions / reports / feedback_forms / audit_events 属 S1-4；argument_nodes / argument_edges / evidence_sources 属 S4-1（直接 ORM+migration，无契约草案要求）
- **一级还是两级加入码**：任务卡 S3-2（课程加入码）与 S3-3（任务加入码）并存，即两级都要。若你只想要一级，请审阅时指出，影响 tasks 表设计（S1-3 范围）
- **表数勘误**：v1.1 的 S1-5 验收写"14 张表"，你本轮给出的完整名单是 15 张（task_submissions 为 v1.1 追加）。S1-5 验收时按 **15 张**核对
- v1.1 契约 5.3 的 `sessions.visibility` CHECK 约束在 sessions 表（S1-3 范围），本草案不触碰；四表不承担权限判断职责

## 7. 起草原则对照

| 你的原则 | 本草案落点 |
|---|---|
| 未来要用的字段宁可先加 | `term`、`display_name`、`is_active`、`admin` 枚举值列入待勾选并给出建议 |
| 不发明复杂关系 | 无独立 students 表、无多教师表、成员表不存教师行 |
| 权限按契约 5.3 走 | 四表不引入权限字段；可见性仍归 sessions（S1-3） |
| user_roles 支持多角色 | UNIQUE(user_id, role)，方案第 8 节第 1 条 |
