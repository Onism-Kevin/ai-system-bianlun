# S3 待办与未完成项清单（收口前跟踪）

> 状态：**跟踪中**（不阻塞 S3-2/S3-3 编码）
> 更新：2026-11-05（S3-1 审阅后）
> 约定：本文件只记"待办/未完成"，已完成项在汇报里贴证据，不在此重复。

---

## 1. S3-1 代码防御性待办（用户 2026-11-05 记入）

### 待办 1：register 的 except IntegrityError 范围太广

- **位置**：`backend/app/api/auth.py:register`
- **现状**：`try/except` 包住 `db.commit()`，该提交同时插入
  `users` + `UserRole(student)` + `UserRole(admin if ADMIN_USERNAME seed)`。
  若将来任一 `UNIQUE` 冲突（不止用户名），都会返回 detail="用户名已被占用"，
  **误导**。
- **为何当前不触发**：新 user 不可能已有角色行（`users.id` 新生成），
  故实际只有 `UNIQUE(username)` 可能撞；ADMIN_USERNAME 路径也无唯一键冲突。
- **修法（S3 收口时）**：捕获后判断 `"username" in str(exc)`；
  不是用户名冲突就 `raise` 重新抛（让全局 handler 处理），
  或细分 detail。

### 待办 2：ADMIN_USERNAME 的"仅首次注册生效"语义

- **要求**：`backend/.env.example` 的 `ADMIN_USERNAME` 注释需补一句：
  "仅对'该用户名首次注册'生效；若账号已存在，需手动用 SQL 或已有
  admin 账号授予，不会追溯。"
- **现状**：**未能落地** —— 该文件路径被 CC Safety Net 按
  `secret.basename.env` 规则拦截（`.env` 与 `.env.example` 同 basename 前缀），
  `ops_read_files` 返回 `CREDENTIAL_DENIED`，`ops_bash` 写入被
  `BLOCKED by CC Safety Net`。
  已如实上报，未用变通路径绕过，也**未触碰** `backend/.env`（真实密钥）。
- **处置**：等用户手动追加该注释（内容见"附：.env.example 待追加片段"）。
  代码侧 `config.py` 的 `admin_username: str = ""` 已落地，功能不受影响。

---

## 2. S3-0 遗留待办（前置检查 §5 未关闭项）

| # | 项 | 级别 | 归属 | 状态 |
|---|---|---|---|---|
| G5 | `audit_events` 无写入 helper / 审计动作细则 | 次要 | S3-1（动作清单）+ S5 | ⏳ 待办 1 中一并定义；MVP 只写 `login` + `role.grant` |
| G8 | `frontend/src/api/types.ts:251` 注释指向不存在的 `backend/app/schemas/task.py` | 次要 | S3-4 | ⏳ 随 S3-4 创建 schema 或改注释 |
| G6a | 前端无全局导航 | 次要 | S3-F1（裁定 5：纳入 S3-F1） | ⏳ 待 S3-F1 |
| G6b | 前端无自动化测试（Vitest） | 次要 | S4/S5（裁定 5：S3 不引入） | ⏳ 待 S4/S5 |
| G7 | errata E-4 表数口径（15 = 12 + 3） | 次要 | S3-0 | ✅ 已修（errata.md:48） |
| G1 | `POST /api/user_roles` 补 api.md 行 | 阻塞 | S3-1 | ✅ 已修（api.md:28） |
| G2 | permissions §4 补 list 行 | 阻塞 | S3-0 | ✅ 已修（4 行） |
| G3 | S3 端点错误码补 422 | 次要 | S3-0 | ✅ 已修 |
| G4 | admin 种子 | 阻塞 | S3-1 | ✅ 已修（ADMIN_USERNAME） |

---

## 2.5 S3-2 审阅后的修正与待办（2026-11-07）

### ✅ 已修

| # | 项 | 修法 | 测试证据 |
|---|---|---|---|
| S3-2a | `GET /api/courses` union 合并后无序 | `result.sort(key=lambda c: c.id)`（修法 A） | `test_list_courses_dual_role_union` 改为断言 `ids == sorted(ids)`，并构造"加入课 id 小 / 教课 id 大"使不排序必失败 |
| S3-2b | `is_archived` 422 测试缺失 | 补 `test_patch_course_is_archived_non_bool_returns_422`（用 `"maybe"`） | ✅ |

### ⚠️ 行为修正（重要）

- **Pydantic v2 会把字符串 `'true'`/`'1'`/`'yes'`/`'no'`/`'0'` 强制转换为 bool**
  （实测 `pydantic.BaseModel(is_archived='true').is_archived == True`）。
  因此"前端传 `'true'` → 422"**不成立**；只有真正非 bool 值
  （`'maybe'`、`[]`）才 422。
  已补 `test_patch_course_is_archived_string_true_coerced` 记录此行为。

### ⏳ 待办

| # | 项 | 级别 | 归属 |
|---|---|---|---|
| S3-2c | `POST /api/courses` 的 409（加入码 5 次重试仍冲突）分支无测试 | 次要 | S5 压测时补（32^8 空间，极端场景） |
| S3-2d | **产品决策**：列表是否带 invite_code | 待拍板 | 用户 2026-11-07 倾向 A（一律不带）；当前实现 = A |

---

## 3. S3 收口数字口径（防混淆，用户 2026-11-05 强调）

- api.md §5 的 **51 = 契约端点总数**（含 S4 图谱、S5 等未实现项），
  **不是已实现数**。
- S2 收口已实现 **28** 个。
- S3 计划实现 ≈ 51 − 28 − 2（`GET /api/messages/{seq}`、`wordcloud`，S4/S5）
  = **21 个左右**。
- **S3 收口时必须单独记**"已实现 X 个 / 未实现 Y 个"，
  **不得**与 §5 的 51 混写（S2 收口 #4 的"21 vs 28"就是这个混淆）。

---

## 4. S3 已交付（截至 2026-11-05）

| 任务 | 交付 | 测试 | Commit |
|---|---|---|---|
| S3-0 | 契约补登（user_roles 行 + 422 + list 4 行 + E-4 口径） | — | ebfc47f |
| S3-1 | 角色管理 API + ADMIN_USERNAME 种子 | 11（新增） | 8238833 |
| S3-2 | 课程创建 + 成员 API（6 端点） | 31（新增） | 待 commit |

---

## 附：`.env.example` 待追加片段（用户手动）

```env

# --- S3-1：首个管理员账号种子（可选）---
# 指定用户名后，该账号注册时自动获得 admin 角色（可授予 teacher/admin）。
# 仅对"该用户名首次注册"生效；若账号已存在，
# 需手动用 SQL 或已有 admin 账号授予，不会追溯。
# 留空 = 不启用种子。生产部署按需填写；切勿把真实密钥写进本文件。
ADMIN_USERNAME=
```
