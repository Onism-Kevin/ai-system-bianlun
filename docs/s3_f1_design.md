# S3-F1 设计纲要（教师端 + 全局导航）

> 前置：S3 后端 6/6 已收口（`docs/s3_backend_closure.md`）。
> 性质：**设计纲要，不写代码**。用户审阅后分 3 个 commit 实现。
> 范围：只改 `frontend/src/`；不碰 backend；无 Vitest（`pnpm build` 验 TS）。

---

## 现状关键事实（读码所得）

| 事实 | 位置 | 影响 |
|---|---|---|
| App.vue = `<router-view />`，无布局 | `App.vue:1-10` | 导航栏必须加在 App.vue |
| DashboardView 内联学生+教师两套视图 | `DashboardView.vue:34,172,235` | 教师块是 stub，要拆 |
| ModelGatewayBanner = 告警横幅 + health 徽标 | `ModelGatewayBanner.vue:45-65` | 徽标要拆出才能进导航栏 |
| useHealth 是模块级单例（引用计数轮询） | `useHealth.ts:12-95` | 可直接复用，无需改 |
| types.ts 无 Course/Task/Summary 类型 | `types.ts` | 需新增 |
| CourseItem 藏在 dashboard.ts | `dashboard.ts:12-17` | 应上提到 types.ts |
| G8：注释指向不存在的 schema | `types.ts:250` | S3-F1 修 |

---

## 1. 导航栏布局：顶部固定条（`AppHeader.vue`）

**选顶部固定条，不选侧边。** 理由：
- 现有页面都是"顶栏 + 内容"结构（DashboardView 的 `.hdr`），顶部条与既有视觉一致；
- 侧边栏需要改 App.vue 为 layout shell（sidebar + main），改动更大；
- MVP 教师端页面不多（工作区 + 课程/任务列表），顶部条足够。

布局（Element Plus 风格，flex）：

```
[思辨工坊]  工作台  训练  历史  复盘   |  [教师端]  |  [用户名/角色]  [health 徽标]
```

- 左侧：站点名 + 导航链接；
- 右侧：教师端入口（条件显示）+ 当前用户 + health 徽标。

health 徽标放导航栏右侧（原 `ModelGatewayBanner` 里是页脚）。这是**有意的布局变化**：导航栏要"复用健康状态"（用户要求），徽标放栏内更醒目。

## 2. 视角切换逻辑：条件显示（不是隐藏后 403）

- **工作台**：**按角色分流**（不是"始终显示同一链接"）——导航栏"工作台"的
  目标是 computed：
  ```ts
  const homePath = computed(() =>
    authStore.roles.includes('teacher') ? '/teacher' : '/dashboard'
  )
  ```
  学生"工作台"→ `/dashboard`；教师"工作台"→ `/teacher`。**解决 §2 与 §6 的矛盾**：
  DashboardView 是学生专用，教师的工作台是 TeacherDashboardView，两者不混。
- **教师端入口**：仅 `auth.roles.includes('teacher')` 时显示。
- **训练 / 历史 / 复盘**：**只对学生显示**。
  - 纠正：`/training?id=X` 是学生训练页（AI 教练/反方 + 学生练论证）；
    教师的"训练"是 S3-6 drill 模式（AI 扮学生 + 教师练引导），**语义不同**。
    若对教师显示"训练"，教师点进去看到学生训练页会困惑。
  - 教师的情境演练入口在 **S3-F4** 教师端加（指向 drill 页面），不复用 /training。
- 真实权限由后端 enforce（E-16 分层），导航栏只是便捷入口。

### 2b. 导航栏链接显示矩阵（最终）

| 链接 | 学生 | 教师 | 双角色 |
|---|---|---|---|
| 工作台（分流） | → /dashboard | → /teacher | 按 teacher 优先 → /teacher |
| 训练 | ✅ | ❌ | ✅ |
| 历史 | ✅ | ❌ | ✅ |
| 复盘 | ✅ | ❌ | ✅ |
| 教师端 | ❌ | ✅ | ✅ |

（双角色"工作台"默认教师端；若想学生优先，改 computed 条件即可，一处改动。）

## 3. 教师工作区数据源

`/teacher` → `TeacherDashboardView.vue`：

| 区块 | 数据源 | 说明 |
|---|---|---|
| 我的课程 | `GET /api/courses`（教师视角 = `teacher_id=本人`） | 替换 DashboardView 的假数据 |
| 快捷入口：建课 | `POST /api/courses`（表单） | 201 → 刷新列表 |
| 快捷入口：建任务 | 跳转 `/teacher/courses/:id` | 任务在课程详情页建 |
| 快捷入口：看汇总 | 跳转 `/teacher/courses/:id`（汇总属 S3-F3） | 标注"汇总页属 S3-F3" |

## 4. 课程/任务列表页交互：两级下钻（不是三栏）

**选两级下钻：**

```
/teacher              → 课程列表（点课程行）
   ↓
/teacher/courses/:id  → 课程详情头 + 任务列表（点任务行）
   ↓
/teacher/courses/:id/tasks/:tid → 提交列表（S3-F3 实现，F1 放占位）
```

理由：
- 三栏在教师屏幕上挤（课程列表 + 任务列表 + 提交列表同时显示）；
- 任务列表依赖课程（`GET /api/courses/:id/tasks`），下钻更自然；
- 提交列表是 S3-F3 的范围，F1 只放占位视图避免死链。

## 5. 路由设计：并列（非 Vue Router 嵌套）

| 路由 | 视图 | 说明 |
|---|---|---|
| `/teacher` | TeacherDashboardView | 教师工作区 |
| `/teacher/courses/:id` | CourseTasksView | 课程详情 + 任务列表 |
| `/teacher/courses/:id/tasks/:tid` | TaskDetailView（占位） | S3-F3 填实现 |
| `/dashboard` | DashboardView（改学生专用） | 见 §6 |
| `/history` `/review` `/training` `/graph` | 不变 | S2 既有 |

**与学生路由并列**（不是 `children` 嵌套）。理由：App.vue 已提供全局布局（AppHeader），无需子路由的 layout。`/teacher/*` 只是 URL 前缀分组。

## 6. DashboardView 处理：**方案 C（拆分）**

- `DashboardView.vue` → **学生专用**：删除教师视角块（`v-if="activeView==='teacher'"`，`DashboardView.vue:235-259`）与双角色切换器（`:159-165`）。
- 新建 `TeacherDashboardView.vue` → 教师工作区。
- 导航栏"工作台"**按角色分流**（见 §2）：学生 → `/dashboard`，教师 → `/teacher`。**这解决了 §2/§6 的表面矛盾**——不存在"教师点工作台看到学生工作台"的路径。
- **不选 A/B**：A/B 会让教师内容出现在两个地方（DashboardView 教师块 + TeacherDashboardView），重复维护。
- 教师专用用户**手动输 URL** 进 `/dashboard`：看到空的学生工作台，可接受（MVP 不加守卫，用户 2026-11-08 裁定）。

## 7. 复用清单

| 组件/模块 | 处理 |
|---|---|
| `useHealth` | **直接复用**（单例，引用计数）。AppHeader + HealthBadge + ModelGatewayBanner 共享同一条轮询 |
| `describeApiError` / `isUnauthorized` | **直接复用**（`api/errors.ts`），教师端错误文案走同一条路径 |
| `ModelGatewayBanner.vue` | **拆分**：告警横幅保留；health 徽标拆出为 `HealthBadge.vue` |
| `HealthBadge.vue`（新） | 从 ModelGatewayBanner 抽出的徽标，AppHeader 复用 |
| `CourseItem` | 从 `dashboard.ts` 上提到 `types.ts` 为 `CourseOut`，两处共用 |
| `api/courses.ts`（新） | 真实调用：listCourses / getCourse / createCourse / patchCourse / getMembers / joinCourse / listCourseTasks |
| `api/tasks.ts`（新） | 真实调用：getTask / createTask / patchTask / joinTask |
| `dashboard.ts` | 学生侧 joinCourse/joinTask 假数据 → 改为调 `api/courses.ts` + `api/tasks.ts`；demoError403/410 保留（S2-F3 教学演示） |

**不重复造**：不新建第二套错误处理、第二套健康轮询、第二套类型定义。

## 8. G8 修复：改注释指向，不删

`types.ts:250` 现为：

```ts
// 与 backend/app/schemas/task.py 提交出参对应（api.md:65，S3-4 未实现）。
```

改为：

```ts
// 与 backend/app/schemas/submission.py 的 SubmissionPostResponse 对应
//（api.md:65，S3-4 已实现）。
```

理由：`SubmissionResponse` 是**真实在用的类型**（S3-F3 会消费），删注释会丢映射文档；backend 实际文件是 `submission.py`（S3-4 产出），不是 `task.py`。

---

## 文件清单 + Commit 计划

### Commit A：导航栏 + 路由骨架（不接数据）

| 文件 | 动作 |
|---|---|
| `components/HealthBadge.vue` | 新：health 徽标（从 ModelGatewayBanner 拆出） |
| `components/AppHeader.vue` | 新：顶部导航栏 + `<HealthBadge />` + 角色条件入口 |
| `components/ModelGatewayBanner.vue` | 改：删徽标 div，只留告警横幅 |
| `App.vue` | 改：`<AppHeader />` + `<router-view />` |
| `router/index.ts` | 改：加 `/teacher`、`/teacher/courses/:id`、`/teacher/courses/:id/tasks/:tid` |
| `views/TeacherDashboardView.vue` | 新：占位（"教师工作区（S3-F1 commit B 填数据）"） |
| `views/CourseTasksView.vue` | 新：占位 |
| `views/TaskDetailView.vue` | 新：占位（"提交查看属 S3-F3"） |

### Commit B：教师工作区（我的课程 + 快捷入口）

| 文件 | 动作 |
|---|---|
| `api/courses.ts` | 新：真实调用 + `CourseOut` 类型 |
| `api/types.ts` | 改：上提 `CourseOut`（原 CourseItem）；新增 TaskOut/SubmissionListItem |
| `views/TeacherDashboardView.vue` | 改：接 `GET /api/courses` + 建课表单 + 快捷入口 |
| `views/DashboardView.vue` | 改：删教师块 + 双角色切换器（学生专用） |
| `api/dashboard.ts` | 改：joinCourse/joinTask 接真实调用 |

### Commit C：课程/任务列表页 + G8 修复

| 文件 | 动作 |
|---|---|
| `api/tasks.ts` | 新：真实调用（listCourseTasks / getTask / createTask / patchTask） |
| `views/CourseTasksView.vue` | 改：课程详情头 + 任务列表（点任务 → `/tasks/:tid`） |
| `views/TaskDetailView.vue` | 改：占位保持（S3-F3 填） |
| `api/types.ts` | 改：G8 注释指向 `submission.py` |

**每步后跑 `pnpm build`，零 TS 错误。**

---

## 开放点（用户 2026-11-08 已全部确认）

1. **教师专用用户访问 `/dashboard`**：✅ **不加守卫**。导航栏"工作台"按角色分流
   （教师 → `/teacher`），教师不会误入；手动输 URL 看到空学生列表可接受（MVP）。
2. **health 徽标从页脚移到导航栏**：✅ **接受**。导航栏全局可见，比页脚显眼。
3. **`TaskDetailView` 占位**：✅ **接受**。F1 建占位路由避免死链，S3-F3 填实现。
4. **`demoError403/410` 保留**：✅ **接受**。S2-F3 教学演示，F1 不动。

## 浏览器验收步骤（每个 commit 后都要跑）

**Commit A（导航栏 + 路由骨架）：**
1. 学生账号登录 → 导航栏显示 工作台/训练/历史/复盘，**不显示** 教师端。
2. 教师账号登录 → 导航栏显示 工作台/教师端，**不显示** 训练/历史/复盘。
3. 教师点"工作台" → 跳 `/teacher`；学生点"工作台" → 跳 `/dashboard`。
4. health 徽标在导航栏可见；gateway down 时显示"不可达"。

**Commit B（教师工作区）：**
5. 教师登录 → `/teacher` 显示"我的课程"列表（真实 `GET /api/courses` 教师视角）。
6. 建课表单提交 → 课程出现在列表。

**Commit C（课程/任务列表 + G8）：**
7. 点课程 → `/teacher/courses/{id}` 显示任务列表（真实 `GET /api/courses/{id}/tasks`）。
8. 点任务 → 跳 TaskDetailView 占位页。

**另有类型级验收**：每步后 `pnpm build` 零 TS 错误（前端无 Vitest，浏览器验收由用户做）。
