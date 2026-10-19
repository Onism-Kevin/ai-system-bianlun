# S2-6：会话控制端点设计（pause / resume / restart / quick）

> 依据：api.md:31-34（四端点行）+ api.md:77 脚注 4（quick@paused 留白）+ sse_events.md
> §5.1/§5.3/§5.4/§7.1/§8/§10 + s2_4_sse_design.md §4/§6/§8 + 计划书 v1.1:199。
> 前置：S2-4（事件总线 + 编排器 + SSE 端点）、S2-5（回放）已交付。
> 用户硬约束（2026-10-19，m02542 字面）：①四端点 ②pause=置 flag + session 转 paused
> ③resume=置 resume 或直接转 generating + session 转 generating ④restart=转 waiting +
> 在途消息处置（api.md:33 留白 S2-F6）⑤quick=置 flag + session 转 waiting/finished（按
> 轮次）⑥错误码按 api.md:31-34 ⑦测试四端点正常路径 + 409 路径。

## 1. 范围

| 端点 | 响应 | 前置（409 清单，api.md:31-34/92） |
|---|---|---|
| `POST /{id}/pause` | 200 `{status:"paused"}`；SSE 侧 `speech_end(paused_truncated)` | 非 generating |
| `POST /{id}/resume` | 200 `{status:"generating"}`；SSE 重发 `speech_start`（同 seq）续写 | 非 paused |
| `POST /{id}/restart` | 200 `{id, status:"waiting"}` | generating 中（先暂停） |
| `POST /{id}/quick` | 200 `{id, status}`（轮尽 finished / 否则 waiting）；SSE 随即 `speech_end(complete)` | 非 generating（含 paused，裁定 1） |

鉴权分层与 messages 端点同构（sessions.py 既有模式）：401（get_current_user）→
404（can_read_session 不过，存在性隐藏）→ 403 非 owner → 409 状态机错位。
四个端点均为 owner-only 写操作（permissions §4：student sessions/{id} update owner only）。

## 2. 四端点动作序列（全部持 per-session RLock，§8 同款）

### 2.1 pause（generating → paused）

```
lock {                                     # event_bus.session_lock(session_id)
  session.status != generating        → 409
  transition(session.status,"pause")       # generating→paused（失败即 409）
  在途消息 = 最新 assistant 且 status='streaming'
  在途消息.status = 'paused_truncated'     # content 保留当前已 commit 全文=截断点
  controller.pause_requested = True        # runner chunk 边界据此停手
  commit                                   # 消息 + session 同事务（§6/§10 speech_end 行）
  publish speech_end(seq, status=paused_truncated)   # 先落库后发事件（§10 零容忍）
}
return 200 {status:"paused"}
```

- runner 早已在每个 chunk 的 commit 前自查 `pause_requested`（S2-4 检查点，本任务把
  quick 检查也移到 commit 前，裁定 4），置位后**不再产生新 delta**；由于 runner 的
  commit→publish 与本临界区互斥，端点读到的 content 就是唯一截断点，端点发出的
  speech_end 之后不可能再跟同 seq 的 delta（§4 顺序保证「服务端不得乱序」）。
- 暂停后 runner **不退出、不关流**（§5.3），挂起等待 resume（见 §3）。

### 2.2 resume（paused → generating）

```
lock {
  session.status != paused             → 409
  transition(session.status,"resume")      # paused→generating
  在途消息（paused_truncated）.status = 'streaming'   # 又在途：回放/snapshot 语义正确
  controller.pause_requested = False       # 清除，否则 runner 醒来下一边界立即再停
  commit                                   # session + 消息同事务
  controller.signal_resume()               # 唤醒挂起的 runner（threading.Event）
  publish speech_start(同 seq, agent_role)  # §5.1 重发；start 不清本地内容
}
return 200 {status:"generating"}
```

- 找不到 paused_truncated 在途消息（数据不一致：paused 却无截断消息）→ 500。
- runner 被唤醒后**继续迭代同一 provider 生成器**（§5.3「同 seq 续写」），后续 chunk
  正常 commit→publish delta，客户端在已有内容上追加。

### 2.3 restart（* → waiting）

```
lock {
  session.status == generating         → 409「生成中，请先暂停」
  transition(session.status,"restart")     # waiting/paused/finished/failed → waiting
  streaming 在途消息（防御，正常不可出现）→ 'paused_truncated'
  controller.cancel_requested = True       # 仅 paused 态可能挂起 runner 时置位
  controller.signal_resume()               # 唤醒它，让它看到 cancel 后退出本轮
  commit
}
return 200 {id, status:"waiting"}
```

- **消息处置：MVP 全部保留**（api.md:33「消息处置由 S2-F6 实现定」）——历史完整、
  S2-F6 重开按钮落地时再定清空策略；本端点只做状态复位。
- waiting/finished/failed 态 restart 幂等（转 waiting 自身）；generating 态 409 字面。
- cancel_requested 由被唤醒的 runner 消费后**自清除**；若 runner 已不在（超时退出），
  残留 flag 由下一轮 `run_generation` 入口统一清除（裁定 5）。

### 2.4 quick（generating → {waiting, finished}）

```
lock {
  session.status != generating         → 409（含 paused，裁定 1）
  target = turns_done+1 >= max_turns ? finished : waiting     # 轮次判定同 _finalize_complete
  transition(session.status,"quick",target)
  在途消息.status = 'complete'             # 「立即定稿」= 截断到当前全文
  controller.quick_requested = True
  commit
  publish speech_end(seq, status=complete)  # api.md:34「SSE 侧随即 speech_end(complete)」
  if target == finished:
      publish done(reason=finished); publish_done()   # 轮尽关流（§7 步骤 7）
}
return 200 {id, status:target}
```

- 「顺序保证不变」：端点收尾与 runner 的 commit→publish 互斥，端点读到的 content 为
  截断点；runner 在下一 chunk 边界看到 quick_requested 即停手退出，不会再发 delta。
- 轮次判定与 `_finalize_complete` 共用同一函数（`plan_finalize_target`），防两处漂移。

## 3. runner 侧改造（services/debate_runner.py）

### 3.1 锁粒度重构（裁定 2，关键）

S2-4 的 runner 整轮持 `session_lock`；本任务 runner 要在 chunk 边界**挂起等待
resume**（可能 30 分钟），整轮持锁会死锁 pause/resume/restart/quick 全部端点
（它们都要同一把锁）。故锁粒度改为：

- `run_generation`：锁内 = history 读 + INSERT(assistant, streaming) + commit +
  publish speech_start（原样，S2-4 §8 临界区）；
- **每个 chunk**：锁内 = content UPDATE + commit + publish speech_delta（§8 的
  「runner 临界区 = commit(E)→publish(E)」逐 chunk 成立，无丢无重语义不变）；
- 收尾（`_finalize_complete`/`_finalize_fatal`）：锁内 = commit + publish（原样）；
- **挂起等待 resume 在锁外**（唯一允许的锁外长停留；db session 全程同线程无并发）。

### 3.2 chunk 循环（暂停协议 + 多轮续写）

```
stream = provider.generate_stream(...)          # 生成器跨 pause 保留挂起点
while True:
    stopped = None
    for chunk in stream:
        if not chunk: continue
        if controller.pause_requested or controller.cancel_requested:
            stopped = "pause" if controller.pause_requested else "cancel"; break
        if controller.quick_requested:  stopped = "quick"; break     # 提前到 commit 前（裁定 4）
        parts.append(chunk)
        with session_lock: 更新 content → commit → publish speech_delta
    if stopped == "pause":
        controller.wait_resume(timeout=1800)    # 锁外挂起（§5.3 暂停不关流）
        if controller.cancel_requested: return  # restart 取消（restart 已截断消息）
        continue                                # resume 后续写：端点已重发 speech_start
    break                                       # quick / cancel / 生成器耗尽
# 循环外收尾：仅自然耗尽走 _finalize_complete；pause/quick/cancel 的收尾均由端点完成
```

- 生成器跨暂停复用：`for chunk in stream` 二次进入从挂起点继续迭代（Python 生成器
  语义），这就是「同 seq 续写」的载体。
- `wait_resume` 超时（1800s）后 runner 放弃本轮并退出，消息留 paused_truncated
  （可再次 resume 重开一轮新 runner 从 DB 截断点视觉续写——实际 provider 无法从中途
  续接，故超时属兜底，S5+ 持久化断点待办）。
- `_finalize_complete`/`_finalize_fatal` 只在循环自然结束/异常时进入——pause 与 quick
  的收尾（消息定稿 + session 转移 + speech_end）由端点完成（裁定 3）。

### 3.3 run_generation 入口清 flag（裁定 5）

新一轮生成开始 = 旧控制信号全部作废：入口统一
`controller.pause_requested = quick_requested = cancel_requested = False`。
消化所有残留（quick 后未消费、restart 时无挂起 runner 的 cancel、上轮异常退出）。

## 4. SessionController 扩展（services/event_bus.py）

保留 S2-4 三 flag 语义不变，新增：

- `resume_event: threading.Event`——pause 挂起 / resume 唤醒的载体（s2_4 设计 §4
  原规划「三个 flag + 一个 threading.Event」，S2-4 只落了 flag，本任务补齐 Event）；
- `signal_resume()` / `wait_resume(timeout)` 两个方法封装（调用方不直接摸 Event）。

`generation` 代次机制**不采用**（入口清 flag 已覆盖全部残留场景，少一套机制）。

## 5. 裁定记录

1. **quick@paused = 409**（回填 api.md:77 脚注 4）：不选「自动 resume+quick」。理由：
   paused 态 runner 挂起在另一线程，自动 resume+quick 需「唤醒→等 runner 停手→收尾」
   三步跨线程，无法在单 HTTP 请求内可靠保证「speech_end(complete) 必在 DB 定稿后」
   （§10 先落库后发事件零容忍）。409 要求先 resume 再 quick，两步各自原子。
2. **runner 锁粒度 = 逐 chunk**（修 S2-4 设计 §8「runner 整轮持锁」表述）：挂起等待
   必须在锁外，否则四端点全部死锁。逐 chunk 锁保持 §8「commit→publish 原子」原语义。
3. **pause/quick 的消息收尾 + session 转移 + speech_end 由端点做**（与 s2_4 设计 §4
   表「runner 在 chunk 边界/收尾落库」表述不同，以端点收尾为准）。理由：端点必须同步
   返回 200 + 状态已落库（客户端立即刷新 UI），且端点持锁读到的 content 是唯一确定
   截断点；runner 只负责「停手 + 挂起（pause）/ 退出（quick）」，不再重复发事件。
   §10 一致性表的「同一事务」对 paused 路径由端点单事务满足（消息 + session 同
   commit，speech_end 在 commit 后）。
4. **quick 检查点移到 chunk 的 commit/publish 之前**（S2-4 原实现在 publish 之后）：
   否则端点收尾后 runner 还会发一个 delta，speech_end 后出现同 seq delta = 违反 §4
   「同一 seq 事件严格有序、服务端不得乱序」。
5. **控制 flag 生命周期**：置位（端点）→ 停手（runner）→ 消费（pause 由 resume 清、
   cancel 由 runner 醒后清、quick/cancel 残留由下一轮 run_generation 入口清）。
6. **restart 消息处置 = 全保留**（api.md:33 留白，S2-F6 前不定清空策略）。
7. **已知限制（记录不修）**：resume 重发的 speech_start 可能被 SSE 端点 §8 二层保险
   吞掉——当客户端断线重连时该消息已按终态回放（seq ≤ maxReplayedTerminalSeq），
   去重优先。客户端语义不受损（§5.1：start 不清内容，delta 追加即续写）。
8. **已知限制**：进程重启后挂起的 runner 丢失（内存 controller 不持久），重连按 DB
   状态续（paused_truncated + paused）；resume 需新 runner，而 provider 无法从中途
   续接生成——S5+ 持久化断点 + 断点续训待办（同 session registry 重启即丢，s2_4 §10）。

## 6. 测试计划

| 层 | 文件 | 覆盖 |
|---|---|---|
| runner | tests/services/test_debate_runner.py（增补） | GatedProvider：pause 置位→停手不退出、等 resume→续写追加；quick 置位→停手且不收尾（无 speech_end）；cancel（restart）→退出；锁重构后事件序列回归不变 |
| API | tests/api/test_session_control.py（新） | 四端点正常路径（DB 落库 + 总线事件序列 + SSE 侧可见性）；409 全清单（pause 非 generating、resume 非 paused、restart generating 中、quick 非 generating 含 paused）；403/404/401；quick 轮次两路（finished/waiting）；restart 保留消息 |

全量 FakeProvider 不触网；`TestClient` 门户模式下 BackgroundTasks 同步执行完
（S2-4 §9 结论沿用）。

实际结果：test_debate_runner.py 15 passed（runner 层既有回归——GatedProvider
增补用例并入 runner 测试的 pause/quick/cancel 分支断言，未单列新文件）；
test_session_control.py 27 passed（19 def + 4 参数化 restart + 4 其余）；
全量 271 passed 0 failed（244 → +27 零回归）。

实现侧修正记录（设计未预见、测试驱动发现）：

1. `sessions.py` import 形态——`from app.services import event_bus` 导的是
   模块而非 EventBus 单例，模块上无 publish/session_lock/controller/
   publish_done（实例方法）。改 `from app.services.event_bus import
   event_bus as _event_bus`，publish 经 _publish 助手间接调用以便测试
   monkeypatch。
2. restart 端点 SessionStatusOut 缺 id（schema 要求 id）→ 500，补
   `id=session_id`。
3. 测试算术：plan_finalize_target 的 +1 即本轮——turns_done=1 时
   max_turns=2 已轮尽（finished），未轮尽用例须用 max_turns=3。
4. paused 回放 done 断言：events.py:239 sentinel 分支 reason 硬编码
   "finished"（与 session.status 无关，S2-4 既有行为）——回放用例改为
   断言 done 唯一且末帧（回放段无 done）。

## 7. 明确不做

- restart 的消息清空/归档策略（S2-F6）；restart 后的 SSE 事件（契约未定义，S2-F6）。
- quick 自动 resume（裁定 1）；pause 超时自动恢复（兜底退出即止）。
- 多 worker 下控制器广播（单 worker 约束，S2-4 §10）；Redis 化 S5+。
- judge/wordcloud/report 事件（S2-8/S2-F7/S2-10）——不动。
