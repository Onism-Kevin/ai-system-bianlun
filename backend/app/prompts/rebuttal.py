"""S0-5：反方对练（rebuttal）prompt 模板。

产出对齐 stage_outputs.CoachTurn（与教练式追问共用同一 schema）：
  question / focus / hints

策略：反方对练侧重「攻击对方论证的薄弱环节」，与教练式追问（引导学生自
己发现问题）视角不同——前者扮演对手施压，后者扮演教练启发。两者都产出一
个追问问题，但 focus 与 hints 的取向不同。
"""

from __future__ import annotations

SYSTEM_PROMPT = (
    "你是高校论证训练平台的反方对练助手，扮演训练对象的对手方。"
    "你只输出合法 JSON，不输出任何解释、markdown 围栏或前后缀文字。"
    "你提问尖锐、直指论证漏洞，但保持学术礼貌，不进行人身攻击。"
)

USER_TEMPLATE = """训练对象提出的立场/论证如下：

{stance}

请作为反方，提出一个最有力的追问，直击其论证最薄弱的环节。

要求：
- question：一个具体的反方追问（一句话到两句话），要能让对方暴露论据不足、
  概念不清或逻辑跳跃。
- focus：这个追问针对的薄弱点是什么（如「缺少数据支撑」「概念偷换」）。
- hints：可选，给对方 1-3 条应对提示（不是答案，是方向）。

只输出 JSON，字段为 question、focus、hints。"""


def build_messages(stance: str) -> list[dict]:
    """构造反方对练阶段的对话消息。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(stance=stance)},
    ]
