"""S0-5：反方对练（rebuttal）prompt 模板（E-11 修订版）。

产出对齐 stage_outputs.CoachTurn（与教练式追问共用同一 schema，errata E-11
落实后同带 quote_refs）：
  question / focus / hints / quote_refs:[{seq, quote}]

策略：反方对练侧重「攻击对方论证的薄弱环节」，与教练式追问（引导学生自己
发现问题）视角不同——前者扮演对手施压，后者扮演教练启发。两者产出同一个
追问问题，但 focus 与 hints 的取向不同；quote_refs 指向被攻击的学生消息。

注意：本 prompt 与 S0-3b mini-bench 时期的字段契约不同，mini-bench 历史
数据（spike_results.csv / model_bench_outputs.jsonl）不重跑、不与本版本对比。
"""

from __future__ import annotations

from app.prompts import render_messages

SYSTEM_PROMPT = (
    "你是高校论证训练平台的反方对练助手，扮演训练对象的对手方。"
    "你只输出合法 JSON，不输出任何解释、markdown 围栏或前后缀文字。"
    "你提问尖锐、直指论证漏洞，但保持学术礼貌，不进行人身攻击。"
)

USER_TEMPLATE = """以下是训练对话记录（每条消息带 seq 编号，方括号内为角色）：

{messages}

请作为反方，针对学生最新的发言提出一个最有力的追问，直击其论证最薄弱的环节。

要求：
- question：一个具体的反方追问（一句话到两句话），要能让对方暴露论据不足、
  概念不清或逻辑跳跃。
- focus：这个追问针对的薄弱点是什么（如「缺少数据支撑」「概念偷换」）。
- hints：可选，给对方 1-3 条应对提示（不是答案，是方向）。
- quote_refs：你攻击所针对的学生原文引用，格式为 [{{seq, quote}}] 列表；
  seq 取对话中学生消息的编号，quote 为引用的原文片段；至少给出 1 条。

只输出 JSON，字段为 question、focus、hints、quote_refs。"""


def build_messages(messages: list[dict]) -> list[dict]:
    """构造反方对练阶段的对话消息。

    入参 messages 为训练消息列表（{seq, role, agent_role?, content}，
    对齐 messages 表出参，见 api.md §1）；按 seq 编号渲染进 prompt，
    供 quote_refs 引用学生原文（E-11）。
    """
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(messages=render_messages(messages))},
    ]
