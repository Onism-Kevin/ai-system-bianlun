"""S0-5：议题拆解（explore/decompose）prompt 模板。

产出对齐 stage_outputs.DecomposeOut：
  topic / core_dispute / pro_position / con_position

策略：强调「只输出 JSON、字段齐全、立场中立」。立场须是可辩的具体主张，
而非空泛套话，便于后续论证分析与追问直接引用。
"""

from __future__ import annotations

SYSTEM_PROMPT = (
    "你是高校论证训练平台的议题拆解助手。"
    "你只输出合法 JSON，不输出任何解释、markdown 围栏或前后缀文字。"
    "你立场中立，准确还原议题双方的真实主张。"
)

USER_TEMPLATE = """请把下面的议题拆解为结构化 JSON。

议题：{topic}

要求：
- topic：议题名，尽量精炼（不超过 30 字）。
- core_dispute：这个议题真正的分歧点，一句话说透（不是复述议题）。
- pro_position：正方的核心立场，必须是可辩护的具体主张，不要空泛口号。
- con_position：反方的核心立场，同样要具体、可辩护。

只输出 JSON，字段为 topic、core_dispute、pro_position、con_position。"""


def build_messages(topic: str) -> list[dict]:
    """构造拆解阶段的对话消息。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(topic=topic)},
    ]
