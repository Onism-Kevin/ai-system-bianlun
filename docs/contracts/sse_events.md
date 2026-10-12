# SSE 事件契约（思辨工坊 Web 版）

状态：**定稿 v1.0（2026-10-12，S1-6，用户审阅通过）**
配套勘误：**errata.md E-9**（计划书 S2-4 验收句"每事件 id: 递增整数"→"每消息 id: 递增整数"）
基线：执行计划书 v1.1 第 5.1 节（本契约是其展开与细化，冲突处以本契约为准并回写勘误）
下游：S1-8（鉴权方式，本契约 §9 依赖）→ S1-7（API 契约引用本契约）、S2-4（端点与事件落地）、S2-5（重连回放）、S2-F5（useSSE.ts）

---

## 1. 目的与范围

定义 `/sessions/{id}/events` SSE 流的**事件类型、帧格式、seq 语义、重连回放流程、错误事件结构、前端重连策略**，作为后端（events.py / event_bus.py）与前端（useSSE.ts / Train.vue）共同遵守的唯一契约。

**不在本契约范围**（各自契约负责）：
- 鉴权与可见性矩阵 → S1-8 权限矩阵（本契约预留鉴权接入位，见 §9）
- 历史消息 REST 端点 → S1-7 API 契约
- `judge` 事件 verdict 字段明细 → S1-9a rubric 初稿
- 报告逐节推送（§5.8/§5.9）的落地时机 → S2 报告任务（契约先定帧格式）

## 2. 传输层

| 项 | 值 |
|---|---|
| 端点 | `GET /sessions/{id}/events`（FastAPI 路由前缀以 S1-7 为准） |
| Content-Type | `text/event-stream; charset=utf-8` |
| 必带响应头 | `Cache-Control: no-cache`、`Connection: keep-alive`、`X-Accel-Buffering: no`（防反代缓冲） |
| 心跳 | 服务端每 **15s** 发 SSE 注释行 `: hb`（EventSource 自动忽略注释行；防代理/防火墙掐空闲连接） |
| 重试提示 | 建流后立即发一行 `retry: 5000`（浏览器原生重连的基准间隔；手动退避见 §8） |
| 请求参数 | `?after_seq=<int>`（仅首次连接用，见 §7.2；重连不带，由 EventSource 自动带 `Last-Event-ID` 头） |

**多会话连接数**：前端同时打开的会话流建议 **≤ 4**；HTTP/2 单连接多路复用下无实质限制（本项目 dev 走 http 明文 + vite 代理，浏览器对同域并发连接数也无瓶颈——此为建议值，非硬约束）。

SSE 帧格式（每事件）：

```
event: <事件名>
data: <单行 JSON，禁止内嵌换行>

```

`data:` 必须是**单行** JSON（SSE 按行拆分，多行 data 需客户端拼接，徒增实现复杂度，全契约禁止）。

## 3. seq 与 `id:` 行语义（对齐 errata E-1 方案 A）

- `messages.seq` = 消息主键（BIGINT AUTO_INCREMENT），**跨会话全局自增、会话内严格递增但不连续**——客户端只可假设单调，不得假设连续。
- 只有 **speech_\* 事件**写 `id:` 行，值 = 该消息的 `seq`：
  - `speech_start` / `speech_end` / `speech_snapshot`：`id: <seq>`
  - `speech_delta`：与所属消息的 start **共用同一 seq**（消息内 id: 不变，消息间严格递增）。重放粒度是"整条消息"（E-1：`WHERE session_id=? AND seq>?`），delta 级 id 无意义。
- **勘误引用（E-9）**：计划书 S2-4 验收句"每事件 id: 递增整数"应读作"**每消息** id: 递增整数"，以本节为准（详见 errata.md E-9）。
- **排序保证**：同一 seq 的事件严格按 `speech_start → speech_delta* → speech_end` 顺序发出，**服务端不得乱序**；跨消息按 seq 递增顺序发出。
- **非 speech 事件（judge / wordcloud_ready / report_\* / error / done）省略 `id:` 行**——它们不推进客户端 `lastEventId`，不参与 DB 回放（回放只回放 messages 表）。
- 客户端 `lastEventId` 由 EventSource 原生维护，断线重连时自动带 `Last-Event-ID` 头。

## 4. 事件总表

| event | id: 行 | data 核心字段 | 触发时机 | 参与回放 |
|---|---|---|---|---|
| `speech_start` | seq | session_id, seq, agent_role | 消息 INSERT（status='streaming'）落库后 | ✅（重编码，§7.1） |
| `speech_delta` | seq | session_id, seq, delta | 每个 LLM chunk | ✅（合并为一条全量 delta） |
| `speech_end` | seq | session_id, seq, status | 消息 UPDATE 终态落库后 | ✅ |
| `speech_snapshot` | seq | session_id, seq, agent_role, content, status | 重连/首连时存在在途消息 | ❌（即时语义，§7.3） |
| `judge` | （省略） | session_id, message_id, verdict | 裁判结构化评审落库后（在 speech_end(judge) 之后，§5.5） | ❌ |
| `wordcloud_ready` | （省略） | session_id, url | 词云生成完成 | ❌ |
| `report_progress` | （省略） | session_id, index, heading | 报告逐节生成（帧格式已定，落地与否 S2 排期定） | ❌ |
| `report_ready` | （省略） | session_id, report_id | 报告落库（同上） | ❌ |
| `error` | （省略） | session_id, code, message, retryable, fatal | 生成异常（§5.7） | ❌ |
| `done` | （省略） | session_id, reason | 会话进入终态（finished/failed） | ❌（重连也会重发） |

`agent_role` ∈ `pro` / `con` / `judge` / `coach`（errata E-5；user/system 消息不走流式）。
`status` ∈ `complete` / `paused_truncated`（E-3；`streaming` 只出现在 snapshot 里）。

## 5. 各事件 payload 与示例帧

### 5.1 speech_start

```json
{"session_id": 7, "seq": 128, "agent_role": "pro"}
```

```
event: speech_start
id: 128
data: {"session_id": 7, "seq": 128, "agent_role": "pro"}
```

**统一规则：`speech_start` 永不清除该 seq 已有的本地内容**（清除/替换只由 snapshot 负责，§5.4）：

- 首次生成：本地本无内容，start 不清 = 开始渲染；
- pause → resume：服务端**重发 speech_start（同 seq）**后继续发 delta，客户端保留已截断的部分继续追加。

### 5.2 speech_delta

```json
{"session_id": 7, "seq": 128, "delta": "我认为……"}
```

每 chunk 一帧，`delta` 为**增量文本**（追加语义）。回放时重编码为一条全量 delta（§7.1）。

### 5.3 speech_end

```json
{"session_id": 7, "seq": 128, "status": "complete"}
```

暂停截断时（S2-6 验收对齐）：

```json
{"session_id": 7, "seq": 128, "status": "paused_truncated"}
```

**暂停不关流**：`paused` 不是会话终态——发完 `speech_end(paused_truncated)` 后 SSE 流**保持打开**，等 resume 后同 seq 续写；关流只发生在 `done`、fatal error（含其后的 done）或网络断。

### 5.4 speech_snapshot

```json
{"session_id": 7, "seq": 128, "agent_role": "pro", "content": "……已生成的累积全文……", "status": "streaming"}
```

**客户端规则：收到 snapshot → 用 `content` 整体替换该 seq 的本地渲染，此后该 seq 的 delta 在其基础上追加。** 这是断线补齐的唯一基准手段（也是客户端幂等性的来源，§7.4）。

### 5.5 judge

```json
{"session_id": 7, "message_id": 135, "verdict": {}}
```

- 裁判**文本**走 speech_\*（agent_role='judge'）；本事件只推**结构化评审结果**。
- `verdict` 字段结构由 S1-9a rubric 定稿后填入（占位，禁止提前发明字段）。
- **顺序保证**：裁判文本流完先发 `speech_end(judge 消息)`，**其后**才发本 judge 事件（结构化结果以文本落库为前提）。

### 5.6 wordcloud_ready

```json
{"session_id": 7, "url": "/static/wordclouds/session_7.png"}
```

`url` 的确切路径形态由 S1-7 API 契约定（占位）。非回放事件：错过本事件的客户端可通过 REST 查询（S1-7 定义）。

### 5.7 error（payload 结构）

```json
{"session_id": 7, "code": "model_timeout", "message": "模型响应超时（read timeout）", "retryable": true, "fatal": true}
```

| code | 后端来源（app/core/exceptions.py） | retryable | fatal | 含义 |
|---|---|---|---|---|
| `model_connection` | ModelConnectionError | true | **true** | 连不上网关（拒绝连接/连接超时/主机不可达/其余传输错误） |
| `model_timeout` | ModelTimeoutError | true | **true** | 连上了但读超时 |
| `model_server`（5xx） | ModelServerError | true | **true** | 网关服务端错误 |
| `model_server`（4xx） | ModelServerError | false | **false** | 可能是请求/prompt 问题，调整后可重试，关流无意义 |
| `structured_validation` | StructuredValidationError | false | **false** | 模型输出未通过 stage schema 校验；重试链路兜底后可降级继续 |
| `internal` | 其他未预期异常 | false | **true** | 未分类故障，附日志 |

**两个字段的正交语义**：

- **`fatal`（流的生死）**：`fatal=true` → 本次失败关流；`fatal=false` → **流保持打开、会话继续**（该消息的最终命运由后续 `speech_end` 或新的 `error(fatal=true)` 决定）。客户端靠它区分"这次失败关流"和"这次失败但会话能继续"。
- **`retryable`（用户动作的预期收益）**：服务端未来是否可能恢复、用户手动重试是否有望成功。与 fatal 正交（如 model_connection：fatal=true 本次关流 + retryable=true 稍后手动重试可能成功）。

**fatal 后必须发 done**：服务端发 `error(fatal=true)` → 发 `done(reason='failed')` → 关流。**`done` 是客户端唯一需要处理的终态信号**（error 事件只用于即时错误展示）；断线后重连时，回放发现 `sessions.status='failed'` 同样发 `done(reason='failed')`——两条路径终态逻辑一致。

**关键区分（生成层 vs 传输层）**：`error` 事件 = **生成层失败**（本次 LLM 调用终止）。客户端**不得**因 error 事件自动重试生成（防止重复调用/循环失败），只呈现错误 UI + 手动重试入口。自动重连（§8）只针对**传输层断线**（onerror 且无 error/done 到达）。

HTTP 层错误**不进事件流**：未鉴权/无权限 → 建流前 `403`；session 不存在 → `404`（S1-8/S1-7 定义细节）。流内异常（回放时 DB 读失败等）→ 发 `error(code=internal)` → `done(reason='failed')` → 关流。同一会话同一时刻至多一条在途消息（顺序轮转：pro→con→…→judge），error 只描述当前在途生成。

### 5.8 report_progress（帧格式已定，落地与否 S2 排期定）

```json
{"session_id": 7, "index": 2, "heading": "论点构建"}
```

Spike 报告（docs/spike_report.md:83）建议报告阶段复用本契约逐节推送 sections 以满足"生成中反馈"UI 硬约束（中位 30.8s / 峰值 57.6s）。

### 5.9 report_ready（同上）

```json
{"session_id": 7, "report_id": 3}
```

### 5.10 done

```json
{"session_id": 7, "reason": "finished"}
```

`reason` ∈ `finished` / `failed`（对应 sessions.status 终态）。**done 是唯一终态信号**：正常完成（session 终态回放后）与 fatal error（§5.7）都会到达 done。客户端收到 done → **主动 close()，不重连**。

## 6. 错误事件约定

见 §5.7 表与语义。补充：

- HTTP 层错误不进事件流（§5.7 末段）。
- 流内异常顺序固定：`error` → `done(reason='failed')` → 关流（§5.7）。
- 同一会话同一时刻至多一条在途消息，error 只描述当前在途生成。

## 7. 重连流程

### 7.1 回放（有 Last-Event-ID 头时）

1. 客户端断线 → EventSource 重开同一 URL，自动带 `Last-Event-ID: <最后收到的 speech_* id>`。
2. 服务端鉴权（S1-8 矩阵）通过后执行：
   `SELECT seq, agent_role, status, content FROM messages WHERE session_id=? AND seq>? ORDER BY seq`
3. 对每条**已终态**（complete / paused_truncated）消息按序重编码回放：
   `speech_start(seq)` → `speech_delta(seq, 全量 content 一条)` → `speech_end(seq, status)`
4. 若存在 `status='streaming'` **在途**消息 → 发一条 `speech_snapshot`（累积全文，§5.4），之后该消息的新 chunk 继续以 `speech_delta` 实时推送。
5. 若 session 已终态 → 回放完发 `done`（含 status=failed → `done(reason='failed')`，§5.7）并关闭；否则进入正常实时推送。

### 7.2 首次连接（无 Last-Event-ID）

- 推荐路径：客户端先 REST 拉历史（S1-7），记录最大 seq=X，再以 `?after_seq=X` 建流；服务端对 `after_seq` 走**与 §7.1 完全相同的回放路径**（`seq > X`），消除 REST→SSE 窗口丢消息的缝。
- **裸连（不带 after_seq 也无 Last-Event-ID）等价于 `after_seq=0` → 回放该会话全部消息（+ 在途 snapshot）**——回放路径只有一条。

### 7.3 在途消息的 snapshot（首连同样适用）

首连（含裸连）时若恰有在途消息 → 同样发 `snapshot`（§5.4），避免"REST 历史停在旧 seq、新消息已开始流动"的渲染缺口。

### 7.4 幂等与至少一次语义

- 事件**先落库后发送**（INSERT 拿到 seq → 发 start；UPDATE 终态 → 发 end）：任何已发出的事件必可回放，语义为 **at-least-once**。
- 客户端必须幂等：按 `seq` upsert 渲染；snapshot 的替换语义天然吸收重复回放。

## 8. 前端重连策略（useSSE.ts 实现）

1. **传输层断线**（onerror、无 error/done 到达）：
   - 计数窗口：任意 **15s** 内 onerror ≥ 3 次（且窗口内无任何消息到达）→ 认定原生重试不健康 → `close()` 转入手动退避。
   - 手动退避序列：1s → 2s → 4s → 8s → 16s → **30s 封顶**，累计 **10 次**仍未连上 → 放弃，UI 呈现"连接已断开 + [重新连接]"手动按钮。
   - 每次成功收到任意事件 → 重置窗口计数与退避档位。
2. **收到 `done`** → 主动 close()，不重连（唯一终态信号；fatal error 后服务端必发 done，客户端终态逻辑只挂 done，error 事件仅用于即时错误展示）。
3. 重连一律经 useSSE.ts 封装（Train.vue 不裸 new EventSource）；`Last-Event-ID` 由 EventSource 原生携带，`after_seq` 仅首连附带。

## 9. 鉴权接入位（S1-8 已回填：方案 A）

**方案 A：Cookie 会话（S1-8 定稿，2026-10-12）**——JWT 存 **httpOnly Cookie**（`set_cookie`，SameSite=Lax），REST 与 SSE 同一凭据；同源（vite 代理）下 EventSource 自动携带 Cookie，无需 query token。

- 鉴权失败发生在建流前（HTTP 403），不产生 error 事件（约束不变）。
- 方案 B（`?token=` 查询参数，§2 预留位保留但不启用）已否决，对比见 permissions.md §6.1。
- 细节与 CORS/CSRF 处置见 permissions.md §6.3；S1-7 API 契约不引用 Authorization 头（errata E-10）。

## 10. 与数据库状态机的一致性约束

| 事件 | DB 前置（必须先落库） |
|---|---|
| speech_start | INSERT message(status='streaming', agent_role=…) —— seq 已分配 |
| speech_delta | 无（chunk 异步追加 content；落库节奏 S2-4 定，不影响契约） |
| speech_end | UPDATE message(status='complete'/'paused_truncated', content 终态) + sessions.status 联动（paused/…） |
| error(fatal=true) | 生成失败已确定（message 终态）+ sessions.status='failed' 落库 |
| done | sessions.status ∈ {finished, failed} **已落库**——error→done 顺序同样受此约束（§5.7） |

违反"先落库后发事件"= 回放会丢事件，属后端实现 bug，契约层零容忍。

## 11. 决策记录（2026-10-12 用户审阅定稿）

| # | 决议 | 结果 |
|---|---|---|
| Q1 | `id:` 粒度 = 消息级（同消息所有 delta 共用 seq） | 采纳，**回写 errata E-9** |
| Q2 | 首连消除 REST→SSE 缝 → `after_seq` 参数（A 方案） | 采纳 |
| Q3 | 非 speech 事件省略 `id:` 行（不推进 lastEventId） | 采纳 |
| Q4 | 心跳 15s、retry: 5000、退避参数（1s→30s 封顶、10 次上限、15s 窗口 3 次 error） | 按本文数值 |
| Q5 | report_progress / report_ready 帧格式纳入本契约 | 纳入；落地与否 S2 排期定 |
| Q6 | judge 仅承载结构化 verdict，裁判文本走 speech_\* | 采纳；**补充顺序：speech_end(judge) 先，judge 事件后** |
| Q7 | at-least-once + 客户端按 seq upsert 幂等 | 采纳 |
| Q8 | 心跳/退避先硬编码 | 采纳 |
| 新增 | **fatal 语义与 fatal 后 done**：5xx/连接/超时/internal fatal=true；4xx/结构校验 fatal=false；fatal error → done('failed') → 关流 | 按 §5.7（用户裁定） |
| 新增 | 6 处补充：judge 顺序、暂停不关流、resume 重发 start 且 start 永不清、同 seq 事件严格有序、裸连=after_seq=0、连接数建议 ≤4 | 全部采纳 |

## 12. 验收锚点（S1-6）

- [x] 事件表含 event / id / data 三字段（§4）
- [x] `speech_snapshot` 出现且定义完整（§4/§5.4/§7.3）
- [x] 重连流程：Last-Event-ID → 回放 + snapshot（§7.1/§7.3）
- [x] 错误事件 payload 结构 + 错误码表（含 fatal 列）（§5.7）
- [x] 前端 EventSource 重连策略（§8）
- [x] E-9 回写勘误（§3 + errata.md）
