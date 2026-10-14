"""S2-2：会话状态机（五态）——纯逻辑转移表，不触库、不实现端点。

权威出处（逐条对齐契约）：
- 五态枚举：schema_v2 sessions.status ENUM(waiting/generating/paused/
  finished/failed) DEFAULT waiting，**应用层在状态转移时写入**（schema_v2:61）。
- 端点级 409 清单（api.md:92）：pause 非 generating、resume 非 paused、
  restart 于 generating 中、quick 非 generating、messages 提交于非 waiting
  （"状态机错位，S2-2 转移表"）。
- 端点行（api.md:31-35）：pause→paused；resume→generating；restart→waiting
  （"经状态机合法转移"）；messages 行为=同步写 messages（role='user'）→
  异步触发 waiting→generating；quick="当前消息立即定稿推进"。
- DB/事件一致性（sse_events.md §10:242-248）：speech_end 的 sessions.status
  联动目标契约留白（"paused/…"）；error(fatal=true)→failed 落库；done 时
  status ∈ {finished, failed} **已落库**——done 不触发转移、只确认终态，
  故不进本表；违反"先落库后发事件"=实现 bug 零容忍。
- quick 在 paused 的语义留白（api.md:77 脚注 4）→ S2-6 实现时定，不进转移表。

转移表（事件 → 合法目标态；多目标=参数化转移，transition() 必须显式传 target）：

  waiting    --submit_message------> generating
            --restart-------------> waiting
  generating --pause--------------> paused
            --quick--------------> {waiting, finished}
            --speech_end_complete-> {waiting, finished}
            --fatal_error--------> failed
  paused     --resume-------------> generating
            --restart------------> waiting
            --fatal_error--------> failed
  finished   --restart------------> waiting
  failed     --restart------------> waiting

两个参数化目标均为契约留白（不猜默认值，由调用方按轮次上下文决定）：
- quick / speech_end_complete 定稿后推进到哪一轮由剩余轮次定（max_turns
  是运行参数不落表，api.md:77 脚注 1），本机只约束"仅 generating 可触发、
  目标仅限 waiting/finished"；
- 其余转移目标契约均已钉死，表内唯一确定。
"""
from __future__ import annotations

SESSION_STATES: tuple[str, ...] = (
    "waiting",
    "generating",
    "paused",
    "finished",
    "failed",
)

# 初始态（S2-3 复用）：会话创建即为 waiting（api.md:28 创建返回 status +
# api.md:35 messages 行为）——创建本身不自动进入 generating，等首条消息提交。
# schema_v2 sessions.status DEFAULT waiting 是 DB 兜底，应用层显式写本常量。
INITIAL_STATE = "waiting"
assert INITIAL_STATE in SESSION_STATES

# 事件 → 合法目标态集合；多目标即参数化转移（transition 的 target 必填）
TRANSITIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "waiting": {
        "submit_message": ("generating",),  # api.md:35 messages 提交（异步触发）
        "restart": ("waiting",),  # api.md:33；409 仅在 generating 中（api.md:92）
    },
    "generating": {
        "pause": ("paused",),  # api.md:31
        "quick": ("waiting", "finished"),  # api.md:34（目标留白，参数化）
        "speech_end_complete": ("waiting", "finished"),  # sse_events §10（联动目标留白）
        "fatal_error": ("failed",),  # sse_events §10 error(fatal=true)
    },
    "paused": {
        "resume": ("generating",),  # api.md:32
        "restart": ("waiting",),  # api.md:33（409 仅在 generating）
        "fatal_error": ("failed",),  # sse_events §10：暂停不关流，连接类 fatal 可命中
    },
    "finished": {
        "restart": ("waiting",),  # api.md:33 重开
    },
    "failed": {
        "restart": ("waiting",),  # api.md:33 重开
    },
}


class IllegalTransition(ValueError):
    """非法状态转移（API 层映射 409，对齐 api.md:92 状态机错位行）。

    继承 ValueError 与 validate_session_visibility（errata E-2）同一约定：
    应用层校验函数抛 ValueError，API 层映射 4xx。
    """

    def __init__(self, current: str, event: str, message: str) -> None:
        super().__init__(message)
        self.current = current
        self.event = event


def can_transition(current: str, event: str, target: str | None = None) -> bool:
    """判断 (current, event, target) 是否合法（不抛异常，供端点/UI 查询）。"""
    if current not in TRANSITIONS:
        return False
    targets = TRANSITIONS[current].get(event)
    if targets is None:
        return False
    if target is None:
        return len(targets) == 1
    return target in targets


def legal_events(current: str) -> tuple[str, ...]:
    """当前状态下可触发的事件名（未知状态返回空 tuple）。"""
    if current not in TRANSITIONS:
        return ()
    return tuple(TRANSITIONS[current])


def transition(current: str, event: str, target: str | None = None) -> str:
    """执行状态转移，返回新状态；非法转移抛 IllegalTransition。

    单目标事件（pause/resume/restart/submit_message/fatal_error）：target
    可省略；传入则必须与唯一目标一致，否则视为非法。参数化事件
    （quick/speech_end_complete）：target 必填且 ∈ {waiting, finished}。
    """
    if current not in TRANSITIONS:
        raise IllegalTransition(current, event, f"未知会话状态: {current!r}")
    targets = TRANSITIONS[current].get(event)
    if targets is None:
        allowed = ", ".join(legal_events(current)) or "（终态，无可用事件）"
        raise IllegalTransition(
            current,
            event,
            f"会话处于 {current!r} 态时不能执行 {event!r}（可用事件: {allowed}）",
        )
    if target is None:
        if len(targets) == 1:
            return targets[0]
        raise IllegalTransition(
            current,
            event,
            f"{event!r} 从 {current!r} 态触发需要显式目标态（可选: {'/'.join(targets)}）",
        )
    if target not in targets:
        raise IllegalTransition(
            current,
            event,
            f"{event!r} 从 {current!r} 不能转移到 {target!r}（可选: {'/'.join(targets)}）",
        )
    return target
