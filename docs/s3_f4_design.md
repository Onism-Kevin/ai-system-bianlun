# S3-F4 设计纲要（教学情境演练页）

> 前置：S3 后端 6/6 收口；S3-F1/F2/F3 前端已交付。
> 性质：**设计纲要，不写代码**。用户审阅后实现。
> 范围：只改 `frontend/src/`；不改后端契约。

---

## 现状关键事实（读码所得）

| 事实 | 位置 | 影响 |
|---|---|---|
| `SessionCreateBody` 缺 `mode`/`max_turns` | `types.ts:29-33` | 后端有（默认 debate/1），前端类型漏 → drill 必须补类型并传 mode |
| `createSession(body)` 已接受 body | `sessions.ts:13` | 无需新函数，补类型即可 |
| `useSSE` 是独立 composable | `useSSE.ts` | 可直接复用（SSE 连接/重连） |
| `TrainingView` 610 行，逻辑完整 | `TrainingView.vue` | 消息 Map + SSE + 控制栏，需决定复用方式 |
| `roleLabel`/`agentTagType` 在 TrainingView 内 | `TrainingView.vue` | drill 的标签不同（教师/正方学生） |
| `/teacher` 路由已有守卫 | `router/index.ts` | drill 页自动受守卫保护 |
| 后端 drill 模式已支持 | `prompts/debate.py` + `teacher_persona.py` | `mode="drill"` → agent_role="pro" |

---

## 1. 页面位置：新建 `/teacher/drill` 独立页（不复用 /training）

**理由**：
- `/training` 是学生语义（AI 教练/反方 + 学生练论证）；drill 是教师语义（AI 正方学生 + 教师练引导）。**标签、上下文、交互提示都不同**。
- 复用 /training 需在每处按 mode 分支，引入隐藏耦合。
- 独立页 `/teacher/drill` 由路由守卫自动保护（学生进不来）。

路由：
```ts
{ path: '/teacher/drill', name: 'teacher-drill', component: () => import('../views/teacher/DrillView.vue') },
```

入口：`TeacherDashboardView` 加"情境演练"按钮 → `/teacher/drill`。

## 2. 会话创建：补 `SessionCreateBody` 类型 + 传 mode（不新增函数）

`types.ts`：
```ts
export interface SessionCreateBody {
  topic: string
  mode?: string        // S3-F4 补：debate/coach/rebuttal/drill
  max_turns?: number   // S3-F4 补：默认 1
  visibility?: 'private' | 'task'
  task_id?: number | null
}
```

`DrillView` 创建会话：
```ts
const session = await createSession({
  topic, mode: 'drill', max_turns: 8, visibility: 'private', task_id: null,
})
router.push(`/teacher/drill?id=${session.id}`)
```

**不新增 `createDrillSession`**——端点是同一个 `POST /api/sessions`，只是 body 多一个 mode 字段。

## 3. 教师视角 UI

| 区块 | 内容 |
|---|---|
| 顶部 | 议题输入（创建 drill 会话）+ 会话信息卡（id/议题/状态） |
| 中部 | 消息流：AI 学生（agent_role=pro）+ 教师输入（role=user） |
| 底部 | 教师输入框（textarea + 发送） |
| 控制栏 | 复用 pause/resume/restart/quick（`api/sessions.ts` 已有） |

**暂停语义**：drill 也是 `generating` 状态机，pause/resume/restart/quick 语义与学生训练**相同**（E-20 restart 保留消息）。直接复用四个端点，无需新语义。

## 4. agent_role 显示：mode-aware 标签

drill 模式的标签映射（与学生训练不同）：

| 消息 | 学生训练（/training） | drill（/teacher/drill） |
|---|---|---|
| role=user | 学生 | **教师** |
| assistant + pro | AI 正方 | **正方学生** |
| assistant + con | AI 反方 | （drill 不会出现） |

实现：抽 `utils/roleLabels.ts`，导出 `labelsForMode(mode)`：
```ts
export function labelsForMode(mode: string) {
  if (mode === 'drill') return { user: '教师', ai: '正方学生' }
  return { user: '学生', ai: 'AI' }
}
```

`MessageStream` 组件接收 labels 作为 prop。

## 5. 复用策略：抽共享组件，不复制粘贴

**抽 `components/MessageStream.vue`**（从 TrainingView 的 v-for 块抽出）：
- props：`messages`（ChatMessage[]）、`labels`（{user, ai}）
- 纯渲染：head（角色标签 + agent_role 徽标 + seq + 截断/生成中）、content（+ 流式光标）
- 保留 TrainingView 的 CSS class（`msg`/`is-user`/`is-ai`/`role-*`/`head`/`content`/`cursor`）

**TrainingView 重构**：模板里的 v-for 块替换为 `<MessageStream :messages="messages" :labels="{user:'学生',ai:'AI'}" />`。**行为不变**（纯渲染替换）。

**DrillView 用 `MessageStream` + `useSSE` + `api/sessions`**：
- 消息 Map + upsert + maxSeq + loadHistory + connectSse：与 TrainingView 同构，抽到 DrillView 内（或进一步抽 `useChatStream` composable，见下）
- 控制栏：复用四个 api 函数
- 错误处理：复用 `useLoadError` + `describeApiError`

**进一步抽象（可选，S5）**：抽 `composables/useChatStream.ts` 封装 messageMap + SSE + send + control，TrainingView 与 DrillView 共用。S3-F4 先用 `MessageStream` 组件 + DrillView 内联逻辑，降低重构风险。

## 6. 错误处理：复用 useLoadError + describeApiError

- 创建会话/加载会话：401 → `goLogin()`（带 redirect）；403/404 → `loadError` 空状态；网络 → toast + 重试
- 发送消息：409（非 waiting）→ `describeApiError` 透传（同 TrainingView）
- 控制按钮：409 状态机错位 → `describeApiError`（同 TrainingView）
- **不新写一套错误处理**

## 7. 空状态

- 无会话（未创建 drill）→ 议题输入 + "创建演练"按钮
- 无消息 → `el-empty` "还没有引导。教师发送第一条引导，AI 学生将回应。"
- 加载中 → loading 占位

---

## 文件清单 + 实现顺序

| 步骤 | 文件 | 动作 |
|---|---|---|
| 1 | `api/types.ts` | `SessionCreateBody` 补 `mode`/`max_turns` |
| 2 | `utils/roleLabels.ts` | 新增：`labelsForMode(mode)` |
| 3 | `components/MessageStream.vue` | 新增：从 TrainingView 抽出消息流渲染 |
| 4 | `views/TrainingView.vue` | 模板 v-for 块替换为 `<MessageStream>`（行为不变） |
| 5 | `router/index.ts` | 加 `/teacher/drill` 路由 |
| 6 | `views/teacher/DrillView.vue` | 新增：完整 drill 页 |
| 7 | `views/teacher/TeacherDashboardView.vue` | 加"情境演练"入口按钮 |

**每步后跑 `pnpm build`，零 TS 错误。**

## 浏览器验收步骤

1. 教师登录 → `/teacher` → 点"情境演练" → 进 `/teacher/drill`
2. 输入议题 → 创建 → 跳 `/teacher/drill?id=X`，会话信息卡显示 id/议题/状态
3. 教师发送引导 → AI 学生（标签"正方学生"）回应 → 消息流显示
4. 控制栏 pause/resume/restart/quick 可用，状态变化正确
5. 学生登录访问 `/teacher/drill` → 路由守卫拦截，跳 `/dashboard`
6. 401/403/404/断网 → 与 commit C 行为一致
7. `pnpm build` 通过，`git status` clean

## 待用户确认的开放点

1. **TrainingView 是否重构为用 MessageStream**？（我倾向是——纯渲染替换，风险低；若担心，可只给 DrillView 用，TrainingView 不动）
2. **drill 的 max_turns 默认值**：建议 8（教师引导需要多轮）；学生训练默认 1。
3. **议题输入框**：drill 页顶部是"创建新演练"还是"选择已有演练"？（MVP 建议只做"创建新演练"）
