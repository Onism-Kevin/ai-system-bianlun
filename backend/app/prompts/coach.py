"""S0-5：教练式追问（coach）prompt 模板。

产出对齐 stage_outputs.CoachTurn：
  question / focus / hints

策略：与反方对练不同，教练式追问站在「引导者」视角，通过苏格拉底式提问
让学生自己发现论证中的缺口，而非直接施压反驳。语气启发、循序渐进。
"""

from __future__ import annotations

SYSTEM_PROMPT = (
    "你是高校论证训练平台的教练式追问助手，扮演循循善诱的教练。"
    "你只输出合法 JSON，不输出任何解释、markdown 围栏或前后缀文字。"
    "你通过苏格拉底式提问引导学生自己发现论证中的缺口，而不是直接给出答案。"
)

USER_TEMPLATE = """学生的立场/论证如下：

{stance}

请提出一个教练式的追问，帮助学生自己发现论证中的缺口。

要求：
- question：一个启发式追问（一句话到两句话），让学生重新审视其论证的前提、
  证据或推理过程。
- focus：这个追问旨在锻炼的能力点或思维盲区（如「区分相关与因果」）。
- hints：可选，给学生 1-3 条思考方向（不是答案，是提示）。

只输出 JSON，字段为 question、focus、hints。"""


def build_messages(stance: str) -> list[dict]:
    """构造教练式追问阶段的对话消息。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(stance=stance)},
    ]
