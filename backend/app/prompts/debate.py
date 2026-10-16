"""S2-4：辩论编排器的 prompt dispatch（docs/design/s2_4_sse_design.md §5）。

按会话运行参数 mode 选 agent_role 与提示词来源（用户 2026-10-16 拍板 1：
debate 固定 con；拍板 2 前的 Q1 裁定：一次 submit = 单条 AI 发言）：

| mode            | agent_role | 提示词来源            |
|-----------------|------------|-----------------------|
| coach           | coach      | prompts/coach.py      |
| rebuttal / con  | con        | prompts/rebuttal.py   |
| debate          | con        | prompts/rebuttal.py   |

轮次模型：一次 POST /messages = 一条 AI 发言（否决 pro+con 双消息——
S0-7 spike 中位 30.8s/峰 57.6s，双发最坏 115s+ 训练场景不可接受）。
"""
from __future__ import annotations

from app.prompts import coach, rebuttal

# mode → agent_role 映射（契约 E-5：agent_role ∈ pro/con/judge/coach；
# debate 固定 con=用户拍板 1「学生持正方辩护，AI 持反方反驳」）
MODE_AGENT_ROLES: dict[str, str] = {
    "coach": "coach",
    "rebuttal": "con",
    "con": "con",
    "debate": "con",
}

# agent_role → prompt 模块（两模块 build_messages 同构，均对齐 E-11 schema）
_AGENT_ROLE_BUILDERS = {
    "coach": coach.build_messages,
    "con": rebuttal.build_messages,
}

# 默认 mode（api.md:28 body 默认值 "debate"）
DEFAULT_MODE = "debate"


def agent_role_for_mode(mode: str) -> str:
    """mode → agent_role（未知 mode 抛 ValueError，由调用方映射 422/500）。"""
    try:
        return MODE_AGENT_ROLES[mode]
    except KeyError as exc:
        raise ValueError(f"未知的训练模式: {mode!r}") from exc


def build_generation_messages(mode: str, history: list[dict]) -> list[dict]:
    """按 mode 选 prompt 模块，构造本轮生成的 messages（[system, user]）。

    history 为带 seq 的训练消息列表（{seq, role, agent_role?, content}，
    对齐 messages 表出参，api.md §1；E-11 同款带 seq 渲染）。
    """
    agent_role = agent_role_for_mode(mode)
    builder = _AGENT_ROLE_BUILDERS[agent_role]
    return builder(history)
