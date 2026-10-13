"""S0-5：教练式追问（coach）prompt 模板（E-11 修订版）。

产出对齐 stage_outputs.CoachTurn（errata E-11，2026-10-13 落实）：
  question / focus / hints / quote_refs:[{seq, quote}]

策略：与反方对练不同，教练式追问站在「引导者」视角，通过苏格拉底式提问
让学生自己发现论证中的缺口，而非直接施压反驳。语气启发、循序渐进。
quote_refs 指向追问所针对的学生消息（S2-9 验收"追问含针对学生原文的引用"
依赖该字段）。输入为带 seq 编号的训练消息（对齐 messages 表出参）。

注意：本 prompt 与 S0-3b mini-bench 时期的字段契约不同，mini-bench 历史
数据（spike_results.csv / model_bench_outputs.jsonl）不重跑、不与本版本对比。
"""

from __future__ import annotations

from app.prompts import render_messages

SYSTEM_PROMPT = (
    "你是高校论证训练平台的教练式追问助手，扮演循循善诱的教练。"
    "你只输出合法 JSON，不输出任何解释、markdown 围栏或前后缀文字。"
    "你通过苏格拉底式提问引导学生自己发现论证中的缺口，而不是直接给出答案。"
)

USER_TEMPLATE = """以下是训练对话记录（每条消息带 seq 编号，方括号内为角色）：

{messages}

请基于学生最新的发言，提出一个教练式的追问，帮助学生自己发现论证中的缺口。

要求：
- question：一个启发式追问（一句话到两句话），让学生重新审视其论证的前提、
  证据或推理过程。
- focus：这个追问旨在锻炼的能力点或思维盲区（如「区分相关与因果」）。
- hints：可选，给学生 1-3 条思考方向（不是答案，是提示）。
- quote_refs：追问所针对的学生原文引用，格式为 [{{seq, quote}}] 列表；
  seq 取对话中学生消息的编号，quote 为引用的原文片段；至少给出 1 条。

只输出 JSON，字段为 question、focus、hints、quote_refs。"""


def build_messages(messages: list[dict]) -> list[dict]:
    """构造教练式追问阶段的对话消息。

    入参 messages 为训练消息列表（{seq, role, agent_role?, content}，
    对齐 messages 表出参，见 api.md §1）；按 seq 编号渲染进 prompt，
    供 quote_refs 引用学生原文（E-11）。
    """
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(messages=render_messages(messages))},
    ]
