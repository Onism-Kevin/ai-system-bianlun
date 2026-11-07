# S3 后端收口检查（轻量）

> 检查人：编程 agent（lead）
> 日期：2026-11-07
> 性质：**S3 后端 6/6 收口后的轻量对账**（非全量 consistency_check）
> 依据：`docs/s3_open_items.md`、`docs/contracts/api.md`、`backend/` 实测

---

## 1. 数字对账：逐任务相加 = 499 ✅

| 任务 | 测试文件 | grep '^def test_' | 汇报数 |
|---|---|---|---|
| S3-1 | test_user_roles.py | 11 | 11 ✅ |
| S3-2 | test_courses.py | 31（fix 后） | 31 ✅ |
| S3-3 | test_tasks.py | 31 | 31 ✅ |
| S3-4 | test_submissions.py | 18 | 18 ✅ |
| S3-5 | test_feedback_api.py + test_teacher.py | 13 + 6 | 19 ✅ |
| S3-6 | test_drill.py + test_audit_api.py | 6 + 7 | 13 ✅ |
| **合计** | | **123** | **123 ✅** |

`376（S2 基线）+ 123 = 499` ✅
全量 pytest 实测：`499 passed, 281 warnings in 463.19s`。

> 注意：S3-2 取 **fix 后 31**（首次 commit 是 29，见 `s3_open_items.md`「S3-2 测试清单漏列」）。

## 2. 测试文件基名查重 ✅

```
$ find tests -name 'test_*.py' | xargs -n1 basename | sort | uniq -d
（空，无重复）
```

第三次踩坑风险已排除。已知记录：
- S3-5：`test_feedback.py` → 改名 `test_feedback_api.py`（与 models 同名）
- S3-6：`test_audit.py` → 改名 `test_audit_api.py`（与 models 同名）

**新增测试文件前必须先查重**（`s3_open_items.md` 待办，用户裁定不补 `__init__.py`）。

## 3. 欠账清零确认

| 欠账 | 状态 | 证据 / 去向 |
|---|---|---|
| S3-1 待办 1：register `except IntegrityError` 范围太广 | **延后** | `auth.py:88` 仍在（返回"用户名已被占用"）。记入收口，S5 前修 |
| S3-1 待办 2：ADMIN_USERNAME 语义写进 `.env.example` | **待用户手动** | 安全网拦截 `.env*`，片段在 `s3_open_items.md` 附录；代码侧 `config.py` 已落地 |
| G5：audit helper | **已部分落地** | `auth.py:129`（user.login）+ `user_roles.py:89`（role.grant）；其余动作留 S5 |
| G8：`types.ts:250` 注释指向不存在的 `schemas/task.py` | **还在 → S3-F1 必修** | `frontend/src/api/types.ts:250` 未改；S3-F1 动前端时一并修 |
| G6a：前端无全局导航 | **还在 → S3-F1 处理** | 裁定 5 已纳入 S3-F1 |
| G6b：前端无自动化测试（Vitest） | **延后 S4/S5** | 裁定 5：S3 不引入 |

**S3-F1 前必须修**：G8（types.ts 注释）。
**非阻塞**：待办 1（S5）、ADMIN_USERNAME（用户手动）、G6b（S4/S5）。

> ⚠️ `s3_open_items.md` 的 G5 行是**陈旧**的（仍写"待办 1 中一并定义"），
> S3-6 已落地两条。本收口文档以实测为准。

## 4. 端点对账：46 vs 51 ✅

| 口径 | 值 | 分解 |
|---|---|---|
| 已实现路由 | **46** | 28（S2）+ 18（S3） |
| 契约端点行 | **51** | 28（S2）+ 18（S3）+ **5（S4/S5 未实现）** |

**5 个未实现端点**（S4/S5，记在 `s3_open_items.md`）：
1. `GET /api/messages/{seq}`（S4-4）
2. `GET /api/sessions/{id}/wordcloud`（S5）
3. `POST /api/sessions/{session_id}/graph`（S4）
4. `GET /api/sessions/{session_id}/graph`（S4）
5. `GET /api/graphs/{graph_id}`（S4）

**口径一致**：46 = 已实现；51 = 契约总数；差 5 = 未实现。**不混写**（用户 2026-11-05 强调）。

---

## 结论

- 数字链 `376 → 486 → 499` 完整对上，逐任务相加 = 499 ✅
- 基名查重干净 ✅
- 欠账仅 1 条需在 S3-F1 前修（G8 types.ts 注释），其余延后或待用户手动
- 端点口径 46（已实现）/ 51（契约）一致，5 个未实现已列清单

**S3 后端 6/6 收口完成。下一步 S3-F1（前端）。**
