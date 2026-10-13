"""S0-5：stage prompt 模板包。

每个模块暴露 build_messages(...) -> list[dict]，产出与 schemas.stage_outputs
中对应的 schema 严格对齐。

E-11（errata，2026-10-13 落实）：analyze/coach/rebuttal 的 build_messages
接收训练消息列表（{seq, role, agent_role?, content}，对齐 messages 表出参，
见 api.md §1），prompt 内按 seq 编号渲染——analyze 的 source_ref 与 coach 的
quote_refs 均引用这些 seq。report/explore 入参不含 seq，保持原样。
"""
from __future__ import annotations

_ROLE_LABELS = {
    "user": "学生",
    "pro": "正方",
    "con": "反方",
    "judge": "裁判",
    "coach": "教练",
    "system": "系统",
    "assistant": "助手",
}


def render_messages(messages: list[dict]) -> str:
    """把带 seq 的消息列表渲染为 prompt 内文本（每条一行，带角色徽标）。

    输入形状对齐 messages 表出参（api.md §1）：
    [{seq, role, agent_role?, content}, ...]
    """
    lines = []
    for m in messages:
        key = m.get("agent_role") or m.get("role", "")
        label = _ROLE_LABELS.get(key, m.get("role", "unknown"))
        lines.append(f"{m['seq']}. [{label}] {m['content']}")
    return "\n".join(lines)
