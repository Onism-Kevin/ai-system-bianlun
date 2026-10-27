"""S0-5 / S2-7：议题探索（explore）prompt 模板。

S2-7 重写：产出对齐 stage_outputs.ExploreOut（api.md:43，E-11）：
  concepts / scope / subquestions / stakeholders

与旧版（DecomposeOut: topic/core_dispute/pro_position/con_position）不同：
ExploreOut 面向"议题探索"阶段，产出概念/范围/子问题/利益方四要素。
DecomposeOut 保留给 spike/mini-bench 用途（STAGE_SCHEMAS 不变）。

策略：强调「只输出 JSON、字段齐全、立场中立」。每项格式为"概念：说明"，
便于前端 S2-F7 拆解显示（标题 + 正文）。
"""

from __future__ import annotations

SYSTEM_PROMPT = (
    "你是高校论证训练平台的议题探索助手。"
    "你只输出合法 JSON，不输出任何解释、markdown 围栏或前后缀文字。"
    "你立场中立，准确还原议题的各方面要素。"
)

USER_TEMPLATE = """请对下面的议题进行探索性拆解，输出结构化 JSON。
议题：{topic}

要求：
- concepts：议题涉及的核心概念或术语。每项格式为"概念名：一句话说明"，
  例如"学术诚信：指学术研究中遵循诚实、公正原则的行为规范"。
- scope：议题讨论的范围与边界（哪些在范围内，哪些不在）。
- subquestions：将议题分解为 3-5 个子问题。每项格式为"子问题：一句话说明"，
  例如"评价标准：用什么指标衡量学术诚信水平"。
- stakeholders：议题涉及的利益相关方。每项格式为"群体/角色：一句话说明立场"，
  例如"学生：关注成绩公平性，反对绝对透明的评分标准"。

只输出 JSON，字段为 concepts、scope、subquestions、stakeholders。"""


def build_messages(topic: str) -> list[dict]:
    """构造拆解阶段的对话消息。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(topic=topic)},
    ]
