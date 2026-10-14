# S2-4 设计纲要：SSE 端点 + 辩论编排器 + messages 落库

> 状态：**待用户审阅**（用户 2026-10-14 指令：先出设计纲要，审完再写代码）
> 范围依据：计划书 v1.1:197 S2-4 任务卡 + errata E-18（S2-4 = SSE 端点 + 编排器 + messages 落库）
> 契约锚点：`docs/contracts/sse_events.md` v1.0（全文）、`api.md` v1.2（:31-42 端点行 + §2/§3）、
> `errata E-1/E-3/E-5/E-9`、`permissions.md §3/§5/§9`（方案 A Cookie）

---

## 0. S2-4 范围（按 E-18 理解）

| 项 | 内容 |
|---|---|
| **做** | `GET /api/sessions/{id}/events`（SSE 流）+ `POST /api/sessions/{id}/messages`（入站消息 + 触发）+ `services/event_bus.py`（进程内事件总线）+ `services/debate_runner.py`（辩论编排器）+ `prompts/debate.py`（正/反轮次 prompt） |
| **不做（他任务）** | pause/resume/restart/quick 端点（S2-6，本设计预留控制通道）、judge 事件（S2-8/S2-10）、wordcloud 事件（S2-F7/S5）、report_\* 事件（S2-10）、restart 后消息处置（S2-F6，api.md:33）、断线重连回放在前端的落地（S2-F5 useSSE.ts；服务端回放能力本任务交付） |
| **新增端点理由** | `POST /messages` 是编排器唯一触发器（api.md:35 行为段：同步写 messages→异步触发 waiting→generating），不实现则 runner 无入口、S2-4 无法端到端验收。E-18"S2-4 = SSE + 编排器 + messages 落库"已含。|

---

## 1. 架构总览（三层 + 两入口）

```
POST /api/sessions/{id}/messages（S2-4，同步 def）
  ├─ 校验：get_current_user（401）→ can_read/owner（404/403）→ 状态机 waiting（409 非 waiting）
  ├─ INSERT messages(role='user', seq 自增) → 201 {seq, created_at}         【用户消息不回显 SSE】
  └─ BackgroundTasks: debate_runner.run(session_id)  ← 线程池，晚于响应执行
        ├─ submit_message 转移（waiting→generating）+ sessions.status 落库
        └─ 每轮次（pro/con）：
              INSERT message(status='streaming') → seq
              → bus.publish(speech_start)                                  【先落库后发事件】
              for chunk in provider.generate_stream(...):
                  UPDATE message.content 拼接
                  bus.publish(speech_delta)
              UPDATE message(complete) + sessions.status 转移
              → bus.publish(speech_end)
        轮尽 → sessions.status=finished → bus.publish(done)

GET /api/sessions/{id}/events（S2-4，同步 def + StreamingResponse(同步生成器)）
  ├─ 建流前三鉴权（401/404/403，HTTP 层，不产生 error 事件）
  ├─ yield "retry: 5000"
  ├─ 回放：读 DB（after_seq / Last-Event-ID → seq>X）→ 终态消息重编码 start/delta(全量)/end；
  │        在途消息 → snapshot；会话终态 → done + 关流
  ├─ 记录 bus 位置 P（在 DB 读之后）→ 订阅 → 只处理 P 之后的事件（见 §8 竞态）
  └─ 循环：queue.get(timeout=15) → 发事件；超时 → yield ": hb"；done → 关流
```

**异步模型决策（D1）**：SSE 端点用同步 `def` + `StreamingResponse(同步生成器)`；runner 走
`BackgroundTasks`（线程池）。**理由**：本项目 DB 层是同步 SQLAlchemy（`get_db` yield 同步
Session，`TestClient`/alembic 全部同步栈），改异步 SQLAlchemy 是伤筋动骨的大重构，不在
S2-4 范围。Starlette 的 `StreamingResponse` 原生支持同步生成器（线程池迭代），
`queue.Queue`（线程安全）做 runner 线程 ↔ SSE 生成器线程的桥。**代价与边界**：每条 SSE
连接占用一个线程池线程（契约 §2：同会话并发 ≤4，MVP 无瓶颈）；进程内总线 = **单 worker
约束**（uvicorn dev 单进程；多 worker 水平扩展需换 Redis pub/sub，记 S5+ 待办）。

---

## 2. 事件发射时序（用户问题 1）

单次 `POST /messages` → 一整轮（正+反各一条发言，见待裁定 Q1）：

```
客户端                messages POST              runner(线程)                SSE 流
  │──POST {content}──▶ │                        │                          │
  │                    │ INSERT user msg (seq=U)│                          │
  │◀─201 {seq,created_at}─│                    │                          │
  │                    │──BackgroundTasks──────▶│ submit_message: waiting→generating 落库
  │                    │                       │ INSERT pro msg(streaming, seq=A)
  │                    │                       │ publish speech_start(A,pro) ─────────▶ event: speech_start / id: A
  │                    │                       │ for chunk: UPDATE content+A; publish delta ─▶ event: speech_delta / id: A
  │                    │                       │ UPDATE A=complete; session 转移
  │                    │                       │ publish speech_end(A,complete) ──────▶ event: speech_end / id: A
  │                    │                       │ INSERT con msg(streaming, seq=B)      （同上，agent_role=con）
  │                    │                       │ …… speech_start(B) → delta* → speech_end(B,complete)
  │                    │                       │ 轮尽: session=finished 落库
  │                    │                       │ publish done(finished) ──────────────▶ event: done / 关流
```

- 每轮结束的 `speech_end_complete` 转移目标：**还有轮次 → waiting**（等学生下一条输入，契约
  §10"paused/…"留白按 max_turns 剩余量参数化）；**轮尽 → finished**。
- `done` 只在 finished 发一次；fatal error 路径见 §7。
- 暂停（S2-6）在 chunk 边界插入：UPDATE 在途消息 `paused_truncated` + session→paused 落库
  → `speech_end(paused_truncated)`，**流不关**（sse §5.3）；resume 重发 `speech_start(同 seq)`
  后续写（内容同行重写，契约 5.2）。

---

## 3. seq 分配策略（用户问题 2）

**决策：复用 DB AUTO_INCREMENT，不做应用层分配。**

- `messages.seq` 本就是 BIGINT AUTO_INCREMENT 主键（schema_v3 表 1、errata E-1 方案 A），
  API 对外 message id = seq。
- runner 流程：`INSERT (status='streaming', content='')` → `flush()` 拿 seq → 发
  `speech_start(seq)`。seq 分配与落库同事務，天然满足"先落库后发事件"（§10）。
- 并发语义：AUTO_INCREMENT 在 INSERT 时分配 → **跨会话交错、会话内单调不连续**（E-1 字面）。
  契约保证"同一会话同一时刻至多一条在途消息"，会话内无 seq 乱序可能。
- 否决应用层分配：分散式计数器/预分配都要额外解决持久化与崩溃恢复，且与 E-1 定稿的
  AUTO_INCREMENT 主键语义重复。

---

## 4. 与状态机的对接点（用户问题 3）

| 触发源 | 事件 | 转移 | 落库时机 |
|---|---|---|---|
| `POST /messages`（S2-4） | `submit_message` | waiting→generating | 响应前（与 user msg INSERT 同事务） |
| runner 轮末（S2-4） | `speech_end_complete` | generating→**{waiting, finished}*** | 发 speech_end 之前 |
| runner 异常（S2-4） | `fatal_error` | *→failed | 发 error/done 之前 |
| `POST /pause`（S2-6） | `pause` | generating→paused | runner 在 chunk 边界落库 |
| `POST /resume`（S2-6） | `resume` | paused→generating | 端点层 |
| `POST /quick`（S2-6） | `quick` | generating→**{waiting, finished}*** | runner 收尾落库 |
| `POST /restart`（S2-F6） | `restart` | *→waiting | 端点层 |

\* 参数化目标：由 max_turns 剩余轮次决定（S2-2 已实现 target 必填 + 全矩阵测试）。
非法转移 → `IllegalTransition` → 409（api.md:92 清单，S2-6 端点映射；S2-4 的 runner 侧
异常路径只走 fatal_error，不存在 409 竞争——生成中收到第二条 messages 已被 waiting 检查拦截）。

**控制通道（预留 S2-6）**：`event_bus` 同模块挂 `SessionController`
（`pause_requested / quick_requested / cancel_requested` 三个 flag + `threading.Event`），
runner 在 **chunk 边界**检查。S2-4 只定义结构并暴露检查点，S2-6 端点置位。

---

## 5. 编排器设计（用户问题 4）

**决策：抽新层 `services/debate_runner.py`，不复用也不改 `core/model_provider.py`。**

- model_provider 是纯传输层（`generate_stream` 窄接口 + 四类异常分类），职责干净；
  辩论编排（轮次、双 stance、DB 交错、总线发射）是业务层，按计划书 v1.1 落
  `services/debate_runner.py`。
- provider 注入（DI）：`run_generation(session_id, provider: ModelProvider)`，默认工厂
  `get_provider()`（settings 驱动：dev/demo→`OpenAICompatProvider`，test→用例自带
  `FakeProvider`）。**不做环境变量魔法**，测试显式传 FakeProvider（chunks + error_after
  现成可用）。
- prompt：新增 `backend/app/prompts/debate.py`——`build_turn_messages(topic, stance,
  history, round_no, max_turns)`；history 复用 `prompts/__init__.py:render_messages`
  （带 seq 渲染，E-11 同款）；stance 系统提示定义正/反立场与回合制规则。**JSON 结构一律
  双花括号转义**（E-11 教训，.format() 安全）。
- 轮次模型：一次 submit = 一轮 = pro 发言 + con 发言（见 Q1 待裁定）；`max_turns` 为运行
  参数不落表（api.md:77 脚注 1），runner 内存持有（请求入参随 BackgroundTasks 闭包传入，
  落一条 `sessions` 无关的运行态——**MVP 形态：内存**，重启即丢，记待办）。

---

## 6. messages 落库时机（用户问题 5）

按 sse_events.md §10 一致性表逐行落地（"先落库后发事件"零容忍）：

| 事件 | 落库动作 | 说明 |
|---|---|---|
| `speech_start` | **INSERT** message(role='assistant', agent_role=pro/con, status='**streaming**', content='')，flush 拿 seq | 行必须存在且带 seq 才能发 start（回放依赖） |
| `speech_delta` | 每 chunk：**UPDATE** content 拼接（同步、同会话） | §10"落库节奏 S2-4 定"→选每 chunk 落：snapshot/回放读 DB 即当前全文，任意时刻断线都正确；性能优化（批量/节流）记待办，MVP 正确性优先 |
| `speech_end` | **UPDATE** message(status='complete'/'paused_truncated', content 终态) **+ sessions.status 联动转移**（同一事务） | §10 原文；转移在发事件前 |
| `error(fatal=true)` | 在途 message 定稿（状态见 Q2）+ sessions.status='failed' | §10 原文 |
| `done` | sessions.status ∈ {finished, failed} **已落库**（done 不转移只确认终态） | §10 原文 |
| user 消息 | `POST /messages` 同步 INSERT(role='user', agent_role NULL)，**不走 SSE 回显** | api.md:35 行为段 + sse §4 补注 |

---

## 7. 错误路径（用户问题 7）

生成层异常 → `core/exceptions` 四类 → sse §5.7 错误码表：

| 模型异常 | SSE code | fatal | 流 | runner 动作 |
|---|---|---|---|---|
| ModelConnectionError | `model_connection` | true | 关 | 在途消息定稿（Q2）→ session=failed 落库 → error → done(failed) → 关流 |
| ModelTimeoutError | `model_timeout` | true | 关 | 同上 |
| ModelServerError(5xx) | `model_server` | true | 关 | 同上 |
| ModelServerError(4xx) | `model_server` | **false** | **不关** | 发 error(fatal=false)；runner 中止本轮，session 保持 generating，在途消息留 streaming——"最终命运由后续 speech_end 或新 error(fatal=true) 决定"（sse §5.7 字面；手动重试入口属 S2-F6） |
| StructuredValidationError | `structured_validation` | false | 不关 | 同上（辩论轮次是流式文本，理论不触发；防御性映射） |
| 其他异常 | `internal` | true | 关 | 同 fatal 行 |

顺序固定：`error` → `done(reason='failed')` → 关流（sse §5.7）。**客户端不自动重试生成**；
自动重连只针对传输层断线（sse §8）。HTTP 层错误（401/404/403）发生在建流前，不进事件流。

---

## 8. Last-Event-ID 回放流程（用户问题 6）

一条回放路径服务两种入口（sse §7.2）：

```
GET /events?after_seq=X            （首连：前端先 REST 拉历史，带最大 seq）
GET /events + Last-Event-ID: X     （EventSource 原生重连自动带）
裸连（都没有）≡ after_seq=0
```

端点流程：
1. 建流前三鉴权：401（无/无效 Cookie）/ 404（会话不存在 or private 越权，存在性隐藏）/
   403（角色不符——**见下方 D8 注**）。均在建流前 HTTP 返回，不产生 error 事件。
2. `yield "retry: 5000"`（sse §2：建流后立即发）。
3. 读 DB：`SELECT seq, agent_role, status, content FROM messages WHERE session_id=? AND seq>? ORDER BY seq`。
4. 对每条**已终态**消息重编码：`speech_start(seq)` → `speech_delta(seq, 全量 content 一条)` →
   `speech_end(seq, status)`（§7.1 步骤 3）。
5. 若有 **status='streaming' 在途**消息 → 发 `speech_snapshot`（累积全文 + status）；其后该
   seq 的新 chunk 以 delta 实时追加（§5.4 替换语义）。
6. 若 `sessions.status ∈ {finished, failed}` → 发 `done(reason=…)` → 关流（§7.1 步骤 5）；
   否则进入实时循环。
7. **实时循环**：`queue.get(timeout=15)` 取总线事件 → 按帧格式发；超时 → `yield ": hb"`（15s
   心跳）；收到 done sentinel → 发 done 帧 → 关流。

**竞态消解（D3 核心，逐情形推导）**：回放读 DB 与订阅总线之间存在窗口——runner 在
"DB 提交 → 总线发布"两步间推进，SSE 端在"读 DB → 订阅"两步间推进，两窗口交叠时会丢
（事件已提交但既不在回放里也没进订阅队列）或重（事件在回放里又在队列里再来一次）。
**解法：per-session 锁把两侧各自的两步变原子**（`event_bus` 每会话一把
`threading.RLock`）：
- runner 临界区 = `commit(E)` → `bus.publish(E)`（publish 是 O(订阅者数) 的队列 append，毫秒级）；
- SSE 临界区 = `回放读 DB` → `读总线单调位置 P` → `订阅 queue`；
- 之后只处理位置 > P 的事件。锁保证：事件要么整体在 SSE 临界区**之前**完成（→ 必在
  回放里且 P 含它 → 跳过），要么整体在**之后**开始（→ 必进订阅队列）。**无丢无重。**
- 第二层保险：speech_\* 事件再按 `session_seq <= maxReplayedTerminalSeq` 跳过
  （终态消息已重编码回放）；非 speech 事件（error/done）天然只发一次且在 commit 之后。
- 锁序无死锁：唯一资源序为 会话锁 → 总线内部锁（publish/subscribe 都短临界）；不同会话
  的锁互不相干；总线锁持有者不反向索取会话锁。
- 该逻辑用 FakeProvider + 并发 publish 的单测钉死（§9 总线层用例）。

---

## 9. 测试策略（用户问题 8）

全部 FakeProvider 驱动（`app/core/model_provider.py:FakeProvider` 现成：chunks +
error + error_after），不触网：

| 层 | 文件 | 覆盖 |
|---|---|---|
| 编排器单测 | `tests/services/test_debate_runner.py` | 事件序列 start→delta*→end；DB 行（streaming→complete、content 拼接、agent_role 交替）；session 转移 waiting→generating→waiting/finished；轮尽 done；fatal 三异常逐一类（error→done 序列 + session=failed + 在途消息定稿）；非 fatal（4xx）不关流语义 |
| 总线单测 | `tests/services/test_event_bus.py` | 多订阅者收全量；§8 去重/竞态逻辑（预置终态消息 + 并发 publish + 订阅 → 断言无丢无重）；心跳超时由 API 测试覆盖 |
| API 流式 | `tests/api/test_events.py` | 建流前 401/404（private 非 owner）；after_seq 回放（终态三件套重编码）；Last-Event-ID 头回放；在途 snapshot；finished 会话 → 回放+done+关流；FailedProvider 驱动真实一次生成 → 收全序列 + done |
| 入口 | `tests/api/test_messages.py` | 201 {seq, created_at}；非 waiting → 409；404/403/401；触发后 DB 出现 assistant 消息（FakeProvider） |

`TestClient` 的 `client.stream("GET", url)` 可读 SSE 帧（httpx 流式），同步生成器 +
`queue.Queue` 在 TestClient 下可直接跑。**TestClient 门户模式下 BackgroundTasks 在
响应返回前同步执行完**——故 `test_messages.py` 里 post 之后直接断言 DB/总线即可；
`test_events.py` 的实时流用例则在开流后用线程触发 runner（或预置在途/终态 DB 状态后
裸连测回放）。

---

## 10. 明确不做 / 边界

- **单 worker**：进程内 EventBus，多 worker 部署需 Redis pub/sub（S5+ 待办，dev 单进程无影响）。
- **judge / wordcloud_ready / report_\*** 事件不在 S2-4（S2-8/S2-10/S2-F7）；总线事件类型开放，后续任务直接 publish。
- **pause/resume/quick/restart 端点** S2-6；runner 的 chunk 边界检查点 + controller 结构本任务预留。
- **前端 useSSE.ts**（S2-F5）：本任务只交付服务端；前端重连退避按 sse §8 由 F5 实现。
- **max_turns/mode 运行参数**：内存持有（BackgroundTasks 闭包），不落表（脚注 1）；进程重启后运行态丢失，重连后按 DB 状态续（restart 由 S2-F6 定）。
- **慢客户端背压**：每订阅者无界 queue（MVP），慢客户端堆积记 S5+；契约建议同会话流 ≤4。

---

## 11. 待裁定问题（请拍板）

1. **Q1 轮次粒度**：一次 `POST /messages` = 一轮 = **pro+con 两条发言**（我推荐，与
   api.md:35"下一轮 AI 生成"及默认 max_turns=1 匹配，一轮=正反各一发）？还是 = 单条
   （pro only / con only 交替）？
2. **Q2 fatal error 时在途消息的终态**：推荐 `complete`（已生成部分即最终内容，失败在
   会话层）；备选 `paused_truncated`（语义偏"暂停截断"，与 pause 场景混用）。
3. **Q3 运行参数载体**：max_turns/mode 内存持有（推荐，MVP）；还是在 messages 请求体带
   （api.md:35 只定义 `{content}`，加字段要勘误，不推荐）。
4. **Q4 403 行在 events 端点**：读路径下 `can_read_session` 不过即 404（存在性隐藏），
   403 不可达（与 S2-3 GET 一致）。api.md:42 的"403 已存在但角色不符"保留字面但无触发
   路径——认可此处理？
