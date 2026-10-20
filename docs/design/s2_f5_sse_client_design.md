# S2-F5：训练页 SSE 客户端设计（useSSE.ts + 消息流渲染）

> 依据：计划书 v1.1:88（S2-F5 行）+ sse_events.md §2-§9 全文 + api.md:35/38/42/44
> + 后端 events.py/sessions.py 已交付实现（S2-4/S2-5/S2-6）。
> 前置：S2-F1（路由骨架）、S2-F4（TrainingView 骨架）、S2-4（SSE 端点）已交付。
> 用户硬约束（2026-10-19，m02542 字面）：①useSSE.ts=EventSource 封装+Last-Event-ID
> 自动重连+指数退避（sse §8）②消息流渲染（start 创建块/delta 追加/end 定稿/snapshot
> 覆盖）③用户消息本地渲染（不走 SSE 回显）④发送按钮走 POST /{id}/messages ⑤错误横幅
> （model_connection/timeout 等）⑥锚点跳转基础版（source_ref 依赖）⑦pnpm build 零 TS
> 错误。

## 1. 范围与命名

| 计划书交付物 | 实际文件 | 说明 |
|---|---|---|
| `composables/useSSE.ts` | `frontend/src/composables/useSSE.ts`（新建） | EventSource 封装+重连策略+帧→回调 |
| `views/Train.vue` | `frontend/src/views/TrainingView.vue`（改造，S2-F4 已建） | 计划书 Train.vue 是早期命名，S2-F4 已定 TrainingView.vue |

连带改动：`frontend/src/api/types.ts`（消息类型）、`frontend/src/api/sessions.ts`
（submitMessage / listMessages 两个新函数）、`frontend/src/api/errors.ts`
（409 文案泛化，见 §6）。

不在本任务：控制栏四按钮全链路（S2-F6）、coach/rebuttal 真实 quote_refs（S2-9）、
focus/hints 展示（S2-9 出参才有真数据）、wordcloud/report 事件（S3/S4）、
SSE 单测（无前端测试框架，验证手段=pnpm build 零 TS 错误 + 真实联调，计划书:307
「真实模型流式，浏览器验证」）。

## 2. useSSE.ts 设计

### 2.1 为什么不用 fetch 流式解析

EventSource 原生提供三件 S2-F5 需要的能力：①自动重连时携带 `Last-Event-ID`
（服务端 `_resolve_after_seq` 认此头优先于 query，sse §7.1）；②`retry:` 指令
（服务端建流即发 `retry: 5000`，sse §2）驱动重连间隔；③事件名分发
（`addEventListener` per event type）。手写 fetch 解析要把这三件全重造，
且 fetch 无法设置 `Last-Event-ID` 之外的等价行为。代价是 EventSource 只支持 GET
（发送消息走 REST POST，本就是既定架构）。

### 2.2 对外接口

```ts
// frontend/src/composables/useSSE.ts
export interface SseHandlers {
  onStart?: (frame: SpeechStartFrame) => void
  onDelta?: (frame: SpeechDeltaFrame) => void
  onEnd?: (frame: SpeechEndFrame) => void
  onSnapshot?: (frame: SpeechSnapshotFrame) => void
  onError?: (frame: SseErrorFrame) => void   // §5.7 流内 error 事件
  onOpen?: () => void                        // 成功建流（reset 退避档位）
  onFatal?: (reason: string) => void         // done(reason='failed')：展示+不重连
  onFinished?: () => void                    // done(reason='finished')：正常终态
  onGiveUp?: () => void                      // §8 累计 10 次放弃：UI 呈现手动按钮
}

export function useSSE(
  url: string,
  handlers: SseHandlers,
  options?: { afterSeq?: number },
): { close: () => void; reconnect: () => void }
```

- `url`：`/api/sessions/{id}/events`（相对路径，同源，sse §9 Cookie 自动携带）。
- `options.afterSeq`：**仅首连生效**（sse §8 字面：「after_seq 仅首连」）。重连一律
  靠 EventSource 原生 `Last-Event-ID`（服务端优先解析该头）。实现：首连拼
  `?after_seq=N`，重连路径不拼（浏览器自动带头）。
- 返回 `close()`（组件卸载主动断开，幂等）与 `reconnect()`（放弃后手动重连入口）。

### 2.3 §8 重连策略落地（逐条对应契约）

| sse §8 原文 | 实现 |
|---|---|
| onerror 且 15s 窗口内 ≥3 次（窗口内无任何消息）→ close() 转手动退避 | `windowStart`/`errorCount` 计数；onerror 时 `errorCount++`，若距 `windowStart` >15s 则重置窗口；`errorCount >= 3` → `close()` + `scheduleRetry()` |
| 退避档位 1s→2s→4s→8s→16s→30s 封顶 | `backoffSteps = [1000,2000,4000,8000,16000,30000]`，`backoffLevel` 递增封顶；`setTimeout` 到点重建 EventSource |
| 累计 10 次仍未连上→放弃，UI 呈现「连接已断开+[重新连接]」 | `attempts >= 10` → `onGiveUp()` 并停表；不再自动重连 |
| 每次成功收到任意事件→重置窗口计数与退避档位 | 每个事件回调入口统一 `noteActivity()`：`errorCount=0; windowStart=now; backoffLevel=0` |
| done → close 不重连 | `onFinished`/`onFatal` 内 `close()`，并把 `closed=true` 使 onerror 不再触发重连 |
| 重连一律经 useSSE 封装 | 无其他直连 EventSource 的代码路径（TrainingView 只调 useSSE） |

细节裁定：

1. **onerror 不可区分「连接失败」与「流被服务端关闭」**：EventSource 对服务端
   正常关闭的流也会触发 onerror 并自动重连。规避：done 处理器内先 `close()`
   （readyState=CLOSED 后 onerror 不再触发重连），故 done→关流路径安全。意外
   断线（done 前断）才会走到 onerror 重连路径——这正是 §8 的场景。
2. **心跳不计入重置**：`: hb` 注释行不是事件（EventSource 不派发 onmessage），
   不触发 noteActivity。15s 窗口内只收 hb 不收事件 = 半死连接，仍累计错误——
   符合 §8「窗口内无任何消息」语义（hb 是注释帧不是 message）。
3. **abort 后不重连**：`close()` 置 `closed=true`，onerror 早退。卸载时调用
   close 避免离开页面仍重试（配合 §8「累计 10 次放弃」兜底）。
4. **attempts 计数只在 scheduleRetry 里递增**，noteActivity 重置 attempts=0
   （「每次成功收到任意事件→重置」；契约对 attempts 是否重置留白，选重置=
   悲观侧：一次成功就把 10 次预算还清，防长会话偶发抖动永久放弃）。

## 3. 消息流渲染模型（TrainingView）

### 3.1 本地消息表

```ts
interface ChatMessage {
  seq: number
  role: 'user' | 'assistant'
  agent_role: 'pro' | 'con' | 'judge' | 'coach' | null
  content: string
  status: 'streaming' | 'complete' | 'paused_truncated'
  streaming: boolean      // 渲染层辅助：是否显示「生成中」光标
  local: boolean          // true=前端本地渲染的用户消息（不走 SSE 回显）
}
```

`messages` 用 `Map<number, ChatMessage>` + `sortedMessages` computed（按 seq 升序）。
Map 而非数组的理由：snapshot/回放/断线补齐都需要按 seq upsert（sse §7.4 幂等），
数组 splice 查找在 100+ 条消息时 O(n) 且易错位。

### 3.2 事件→状态迁移（§4-§5 逐条）

| 事件 | 动作 | 契约依据 |
|---|---|---|
| `speech_start` {seq, agent_role} | `upsert(seq, {role:'assistant', agent_role, status:'streaming', streaming:true, content:''})`。**若已存在同 seq 且 content 非空，保留 content 不覆盖** | §5.1「永不清本地内容」：pause→resume 服务端重发同 seq start，客户端必须续写而非清零 |
| `speech_delta` {seq, delta} | `content += delta` | §5.2 增量追加 |
| `speech_end` {seq, status} | `status = status; streaming=false` | §5.3/§10：status∈complete/paused_truncated |
| `speech_snapshot` {seq, agent_role, content, status} | `content = content`（整体替换） | §5.4「唯一基准+幂等来源」：断线补齐基准，此后 delta 在其上追加 |
| `error` {code, message, retryable, fatal} | 只进错误横幅，**不动消息表、不重试生成** | §5.7「客户端不得因 error 自动重试生成」 |
| `done` {reason} | reason='finished' → 正常收尾；'failed' → 横幅标 fatal；两者都 close 不重连 | §5.10 |

幂等保障（§7.4 at-least-once）：所有写操作按 `seq` upsert；delta 追加语义
「snapshot/start 之后的第一条 delta 从空 content 起」——snapshot 已在服务端
保证只发一次（§8 二层保险，S2-5 已落地 events.py），客户端仍按 seq 覆盖防
服务端重发。

### 3.3 用户消息本地渲染（硬约束 ③）

发送流程：

```
POST /{id}/messages {content}  →  201 {seq, created_at}
      │
      ├─ 立即 upsert({seq, role:'user', local:true, content, status:'complete'})  ← 不依赖 SSE
      └─ 清空输入框
```

用户消息不占 SSE 通道（sse §4 补注 + api.md:35 行为段）。多标签页一致性由各
标签页独立重连回放兜底（MVP 可接受，sse §4 补注）。发送失败走
`describeApiError` + `isUnauthorized`（跳登录）——409 非 waiting 复用会话状态
横幅（见 §6 errors.ts 泛化）。

### 3.4 历史加载与 after_seq 消缝（sse §7.2）

进页面 onMounted 顺序：

```
1. GET /sessions/{id}                 → session.value（状态徽章）
2. GET /sessions/{id}/messages?after_seq=0&limit=200
                                      → messages Map（user 本地历史也在内，DB 里有）
                                        maxSeq = max(messages.seq) 或 0
3. useSSE('/sessions/{id}/events', handlers, { afterSeq: maxSeq })
```

§7.2 原文「首连推荐先 REST 拉历史记最大 seq=X 再 ?after_seq=X 建流」——本方案
即此。裸连（after_seq=0）等价于全量回放，但会让用户先看到 start→delta 全文
「逐字重放」的观感；先 REST 再 after_seq=maxSeq 直接进实时态。

### 3.5 锚点跳转（硬约束 ⑥，基础版）

- 每条消息 DOM `:id="'msg-' + seq"`（`el-card` 外层 div）。
- 点击引用 → `document.getElementById('msg-' + seq)?.scrollIntoView({behavior:'smooth', block:'start'})`
  + `scroll-margin-top: 12px` CSS（sticky 头遮挡补偿，等价计划书:307「锚点
  offset 断言」的 MVP 版）。
- 渲染入口：本任务真实数据里 quote_refs 只有 S2-9 coach/rebuttal 才有，故
  **引用块仅在消息本地渲染时展示占位说明**；滚动函数 `scrollToMessage(seq)`
  对任意 seq 可用（后续任务直接复用）。
- S2-F9 会把「锚点跳转」扩成带高亮闪动的完整版（依赖 analyze 出参）。

### 3.6 状态徽章与 SSE 联动

`session.status` 在控制端点（S2-6）返回后更新；SSE 流本身不改 status（避免
与服务端权威态竞态）。done 到达时若 reason='finished'，本地同步
status='finished'（服务端 quick 轮尽路径已落库 finished）。暂停/恢复后 runner
重发 speech_start 同 seq，消息表不重建块——「续写同一条」观感即计划书 S2-6
完成信号的前端体现。

## 4. 训练控制区（S2-F5 的边界）

按钮渲染按原型的禁用态逻辑（training.html:164-167）：pause/quick 仅 generating、
resume 仅 paused、restart 非 generating。**S2-F5 只做禁用态，不接点击**
（点击全链路属 S2-F6，硬约束④的发送按钮例外——发送走 messages 端点属 S2-F5）。
文案注明「控制端点 S2-6 已交付，按钮接入 S2-F6」。

## 5. 文件级改动清单

| 文件 | 改动 |
|---|---|
| `frontend/src/api/types.ts` | +`MessageOut`（seq/role/agent_role/content/status/created_at）、`MessageListOut`（messages/next_seq）、`SseSpeechStart/SpeechDelta/SpeechEnd/SpeechSnapshot/Error/Done` 帧类型（与 sse §4 逐字对应） |
| `frontend/src/api/sessions.ts` | +`submitMessage(sessionId, content)`（201→MessageCreated）、`listMessages(sessionId, afterSeq=0, limit=200)` |
| `frontend/src/composables/useSSE.ts` | 新建，§2 设计 |
| `frontend/src/views/TrainingView.vue` | 改造四占位卡：会话信息保留、辩论对话→消息流、消息输入→真发送、训练控制→禁用态；+错误横幅区 |
| `frontend/src/api/errors.ts` | 409 文案泛化（见 §6） |
| `docs/contracts/api.md` | 无需改（端点 S2-6 已登记；本任务纯前端消费） |
| `docs/contracts/sse_events.md` | 无需改（契约 v1.0 已覆盖全部事件） |

## 6. 已知问题与裁定

1. **errors.ts 409 文案泛化**：现有 `describeApiError` 409 写死「用户名已被占用」
   （register 语义，api.md:25）。S2-F5 起 messages 409（「会话当前状态不接受新消息」
   sessions.py:105）与控制端点 409（S2-F6）都走 409。裁**定**：409 分支改为
   透传后端 detail（403/404 同款），无 detail 兜底「当前状态不允许此操作」。
   register 的「用户名已被占用」由后端 detail 承载（S2-1 实现现状如此）——
   前端不再按状态码猜语义。
2. **user 消息本地渲染与 DB 回放的重复**：进页面 REST 拉历史含 user 消息（DB 里
   有），SSE 回放只回 assistant（events.py 跳过 role!='assistant'）——两条路径
   不重叠，Map upsert 天然去重。
3. **断线时本地未发送成功的 user 消息**：POST 失败（断网）时消息不入 Map，
   重连后回放只有 assistant。裁**定**：MVP 接受（发送失败即横幅报错，用户手动
   重发）；多标签页场景本就 MVP 可接受。
4. **SSE 与 REST 时序竞态**：发送 POST 201 返回时 SSE 流可能已推 speech_start
   （BackgroundTasks 与响应并发）。upsert 按 seq 幂等，无观感问题。
5. **浏览器限制单域 6 条 SSE 连接**：每训练页 1 条流，MVP 无冲突（sse §8 慢
   客户端假设同会话 ≤4 连接）。

## 7. 测试与验证

无前端测试框架（无 vitest 依赖，S2-F1 决策：验证=pnpm build 零 TS 错误）。
本任务验证手段：

1. `pnpm build`（vue-tsc -b && vite build）零 TS 错误——tsconfig 全开
   （noUnusedLocals/noUnusedParameters/erasableSyntaxOnly/noFallthroughCasesInSwitch）。
   实际结果：✅ 通过（built in 388ms；chunk >500kB 警告为 element-plus 既有
   体积提示，非本任务引入，S2-F1 起即存在）。
2. 真机联调（计划书:307 验收）：`pnpm dev` + 后端 FakeProvider 或真实模型，
   浏览器验证：①消息逐字增长（delta 追加）②暂停→续写同一条续写（§5.1）③
   断网重连补齐（§8 退避+回放）④点击锚点滚动定位。
3. 后端既有 271 用例零回归（本任务不触后端代码）。实际结果：✅
   `271 passed, 49 warnings in 204.33s`（2026-10-20 复跑确认）。

### 7.1 构建期修复记录（3 处 TS 错误，均为本任务代码）

| 错误 | 修法 |
|---|---|
| `TrainingView.vue(2,31) TS6133: 'reactive' declared but never read` | 删 reactive import（v-model 用 ref 即可） |
| `TrainingView.vue TS6196: 'MessageOut' declared but never used` | 删 MessageOut import（history 行类型由 listMessages 返回推断） |
| `TS2339: Property 'value' does not exist on type 'never'`（`sse.status.value`） | 根因：`let sse: ReturnType<typeof useSSE> \| null` 在模板里 TS 窄化为 never（setup 内 let 非响应式）。修法：`UseSseResult` 显式类型 import + 新增 `sseStatus` ref 镜像连接态，模板读 `sseStatus`；`sse` 仅脚本内持有（reconnect 按钮调 `sse?.reconnect()`） |

## 8. 明确不做

- 控制栏四按钮点击全链路（S2-F6）。
- 流内 error 的自动重试（契约明令禁止，§5.7）。
- quote_refs 真实渲染（S2-9 coach/rebuttal 出参）、focus/hints（S2-9）。
- 多标签页实时同步（MVP 各页独立回放）。
- SSE 单测框架引入（等 S2-F9 或用户统一拍板）。
- 「连接已断开」UI 的完整重连管理页（S2-F9：本任务只做放弃态横幅+手动按钮）。
