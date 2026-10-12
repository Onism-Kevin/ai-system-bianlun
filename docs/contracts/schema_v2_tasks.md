# 数据契约草案 v2：任务与练习三表（S1-3 范围）

> **状态：DRAFT —— 等待用户审阅，审阅通过前不得据此写 ORM。**
> 范围：`tasks` / `task_submissions` / `sessions` 三张表（任务卡 S1-3，见执行计划书 v1.0）。
> 全局约定（字符集 utf8mb4 / 时间列 / 约束命名表名在前 / 布尔存 tinyint(1)）沿用
> `schema_v1.md` §0，不再重复。表名 15 张口径与《完整方案》第 10 节 + v1.1 一致。

## ⚠️ 审阅前必读：三个你点名的焦点问题

### 焦点一：`sessions.visibility` 的约束放 DB 层还是应用层？

**推荐：应用层强制（DB 不加 CHECK）。** 与你的倾向一致，理由：

1. **报错质量**：DB CHECK 违例只给 `ERROR 1062/3819` + SQLSTATE 23000 通用信息，
   服务层能给出明确的 4xx 与中文原因（"任务练习会话必须关联任务"）；
2. **演进成本**：将来加第三态（如 `public`）时，应用层只改一个校验函数；
   DB CHECK 要 ALTER TABLE 重建约束；
3. **表达力错位**：`visibility='task' → task_id 非空` 这条还好，
   但"task_id 指向的任务必须存在且未归档"本来就必须应用层查——两层写一半反而误导。

**事实澄清**：MySQL 8.4.9（本项目实测版本）CHECK 语法可用（8.0.16+），
"不支持"不是否决理由，纯粹是上面 1/2 条的权衡。
若你想要纵深防御，可以两层都上（DB CHECK 语法本草案已验证可行），**默认不加，等你表态**。

**连带后果（你确认后一并执行）**：
- v1.1 契约 5.3 那句"CHECK 约束"追加勘误为"应用层强制"；
- 计划书 S1-3 验收句"`visibility='task' AND task_id IS NULL` 插入被拒"
  改为"服务层测试断言该状态组合被拒绝"。

### 焦点二：`messages.seq` 的语义（契约 5.1 两句矛盾的解法）

**矛盾点**：契约 5.1 一边写"seq BIGINT AUTO_INCREMENT PRIMARY KEY"，
一边注"主键为独立 id"。且有一个硬约束：**MySQL 每张表只允许一个 AUTO_INCREMENT 列**，
所以"id 是 PK 且自增"和"seq 是全局 AUTO_INCREMENT"**不可能同时成立**。两条路：

| | 方案 A（**推荐**） | 方案 B（你字面倾向的可行版） |
|---|---|---|
| 主键 | `seq`（BIGINT AUTO_INCREMENT PRIMARY KEY），无独立 id | `id`（BIGINT AUTO_INCREMENT PRIMARY KEY） |
| seq | 即主键；API 对外的 message id 就是它 | 应用层生成：事务内 `SELECT MAX(seq)+1 WHERE session_id=?` |
| 竞态 | 无 | 依赖"每会话单写者"不变量（S2-2 状态机保证同一时刻只有一个 generating），重连回放 UPDATE 与新写入并发时有理论竞态 |
| 列数 | 少一列 | 多一列 |
| Last-Event-ID | 直接等于 seq，回放 `WHERE session_id=? AND seq>?` | 同左 |

**推荐方案 A 的核心理由**：契约 5.1 的回放语义（"按 (session_id, seq) 排序"）
只需要 seq，独立 id 没有任何一处被引用；方案 B 用一列冗余换来一个需要
"单写者不变量"背书的生成逻辑，不划算。

**单调性的正确表述（契约措辞应这样勘误）**：
seq 是**全局** AUTO_INCREMENT，会话内单调由"全局单调序列的子序列仍单调"保证；
**不是**"每会话从 1 开始连续编号"，也**不是**"会话 A 占 1-10、会话 B 占 11-20"——
并发写入时各会话的 seq 是**交错**的，例如：

```
时间线：  写A(得1) → 写B(得2) → 写A(得3) → 写B(得4) → 写A(得5)
会话A 的 seq = 1, 3, 5   ← 单调 ✓（回放 ORDER BY seq 正确）
会话B 的 seq = 2, 4      ← 单调 ✓
```

回放查询 `WHERE session_id='A' AND seq > Last-Event-ID ORDER BY seq`
在交错分配下依然严格正确——这正是 `UNIQUE(session_id, seq)` 复合索引的用途
（方案 A 下全局唯一已蕴含会话内唯一，但该复合索引仍保留：它是回放查询的覆盖索引，
且让计划书 S1-4 验收句"(session_id, seq) 重复插入被拒"两种方案下都成立）。

### 焦点三：`task_submissions.student_id` 是 FK 吗？

**是 FK（`users.id`，ON DELETE CASCADE），同意你的倾向。** 三个理由：

1. 越权检查免 join：`GET /api/submissions/{id}` 直接比
   `submission.student_id == current_user.id`，不用先查 sessions 再查 owner；
2. 删账号时提交记录随账号级联清理，不留孤儿行；
3. DB 层保证不可能出现"指向不存在用户的提交"。

`session_id` 同样是 FK（`sessions.id`，ON DELETE CASCADE）——
提交引用的会话本身被删时提交记录无意义。`UNIQUE(task_id, session_id)` 按契约 5.3 保留。

---

## 表 1：`tasks`（任务）

| 列 | 依据 | 说明 |
|---|---|---|
| `id` BIGINT PK AUTO_INCREMENT | 表骨架 | |
| `course_id` BIGINT NOT NULL, FK→`courses.id` ON DELETE RESTRICT | 有明确依据 | 任务属于课程（S3-2 建课后创建任务）；RESTRICT = 不允许删带任务的课程（MVP 本无删课 API，课程走归档，与 teacher_id 同哲学：防误删数据） |
| `title` VARCHAR(120) NOT NULL | 有明确依据 | 任务创建页表单字段（长度 120 为起草值） |
| `material` TEXT NULL | 有明确依据 | 任务卡"材料上传"；**MVP 形式 = 文本粘贴**（文件上传涉及对象存储，超出首版，S3-2 实现时若要文件再加列） |
| `join_code` VARCHAR(8) NULL UNIQUE | 有明确依据 | 任务级加入码（S3-3 错码 403 验收）；生成规则同 v1：6~8 位 A-Z0-9 剔除 I/O/0/1；NULL = 不需要加入码的任务 |
| `created_at` / `updated_at` | 全局约定 | |

**待勾选（审阅时表态）**：

- [ ] `deadline` DATETIME NULL —— 教学常用（学生端倒计时）；方案未明示，**建议加**（NULL=不限时）
- [ ] `is_archived` TINYINT(1) NOT NULL DEFAULT 0 —— 归档不删任务；MVP 无删任务 API，**建议加**防将来返工
- [ ] 学生可见性细则（未加入课程学生 404 等）归 S3 实现层，不进表结构

## 表 2：`task_submissions`（提交）

| 列 | 依据 | 说明 |
|---|---|---|
| `id` BIGINT PK AUTO_INCREMENT | 表骨架 | |
| `student_id` BIGINT NOT NULL, FK→`users.id` ON DELETE CASCADE | 有明确依据 + 你的拍板（焦点三） | 提交人 = 会话 owner；越权检查直查此列 |
| `task_id` BIGINT NOT NULL, FK→`tasks.id` ON DELETE CASCADE | 有明确依据 | 任务删除时其提交记录一并删除（同焦点一连带：无删任务 API，行为仅防孤儿） |
| `session_id` BIGINT NOT NULL, FK→`sessions.id` ON DELETE CASCADE | 有明确依据（契约 5.3） | 提交会话；UNIQUE 约束的第二列 |
| `submitted_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP | 有明确依据（契约 5.3） | |
| `UNIQUE(task_id, session_id)` | 有明确依据（契约 5.3） | 同一会话不能重复提交到同一任务 |

**待勾选（审阅时表态）**：

- [ ] `UNIQUE(task_id, student_id)` —— 一个学生对一个任务只能有一份提交。
      **建议加**：教学语境几乎必然如此；契约 5.3 只写了 (task_id, session_id)，
      不加的话学生换会话可反复提交，S3-5 汇总统计语义会乱。若你想允许多次提交取最高，
      请明说，那 S3-5 统计口径要一起定。
- [ ] `score` DECIMAL(5,2) NULL + `teacher_comment` TEXT NULL —— 教师人工评分/评语列。
      方案 S3-5 只提"汇总统计"未明示人工评分；报告 score 是 AI 生成的。
      **建议先不加**，S3 需求明确后再加（加列无损，但首版不发明没被要求的功能）。

## 表 3：`sessions`（练习会话）

| 列 | 依据 | 说明 |
|---|---|---|
| `id` BIGINT PK AUTO_INCREMENT | 表骨架 | |
| `owner_id` BIGINT NOT NULL, FK→`users.id` ON DELETE CASCADE | 有明确依据 | "个人练习（visibility='private'）仅 owner 可见"（契约 5.3）；删账号级联删其会话 |
| `topic` VARCHAR(200) NOT NULL | 有明确依据 | 五阶段以议题为输入（拆解的起点）；长度 200 为起草值 |
| `visibility` ENUM('private','task') NOT NULL DEFAULT 'private' | 有明确依据（契约 5.3） | 校验层=应用层（见焦点一，待你确认） |
| `task_id` BIGINT NULL, FK→`tasks.id` ON DELETE CASCADE | 有明确依据（契约 5.3） | `visibility='task'` 时非空（应用层校验）；任务删除时其练习会话一并删除 |
| `status` ENUM('waiting','generating','paused','finished','failed') NOT NULL DEFAULT 'waiting' | 有明确依据 | S2-2 状态机五态 + S2-12"列表含状态/时间"必须落库；由应用层在状态转移时写入 |
| `created_at` / `updated_at` | 全局约定 | 列表"时间"列直接取这两列 |

**待勾选（审阅时表态）**：

- [ ] 会话级冗余分数列（最新报告 score 冗余到 sessions，列表免 join reports）
      —— **建议不加**：S2-12 列表契约只要求"状态/时间"，join reports 成本可忽略

**教师可见性**（S3 实现层规则，记录在此防丢）：`visibility='task' AND task_id`
指向的任务属于教师所在课程 → 教师可见该会话及其 messages。
"提交后教师可见；未提交不可见"（S3-4）——即教师默认只见该任务的
`task_submissions` 引用的会话，不扫全部 task 会话。此规则在 S3-4 实现，不动表结构。

## 删除语义汇总

```
users ──(CASCADE)──> sessions ──(CASCADE)──> messages / task_submissions
users ──(CASCADE)──> task_submissions
courses ──(RESTRICT)──< tasks ──(CASCADE)──< sessions / task_submissions
```

## 范围外

- revisions / reports / feedback_forms / audit_events / messages → `schema_v3_messages.md`（S1-4 草案，同批审阅）
- 图谱三表（argument_nodes / argument_edges / evidence_sources）→ S4 范围，届时另出草案
- 学生加入课程/任务的中间流程（S3-3）不新增表（course_members / join_code 已覆盖）
