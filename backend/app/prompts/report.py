"""S0-5：复盘报告（report）prompt 模板。

产出对齐 stage_outputs.ReviewReport：
  summary / strengths / weaknesses / sections[{heading, body}] / score(0-100)

策略：面向教师与学生的复盘，既要给可操作的改进建议，也要给出可追踪的分数。
score 用 0-100 整数便于纵向对比；sections 允许模型按论点组织长文分析。
"""

from __future__ import annotations

SYSTEM_PROMPT = (
    "你是高校论证训练平台的复盘报告助手。"
    "你只输出合法 JSON，不输出任何解释、markdown 围栏或前后缀文字。"
    "你评价客观、具体，既肯定亮点也指出可改进之处，不空泛褒贬。"
)

USER_TEMPLATE = """请根据本次训练的完整过程，生成一份复盘报告。

训练议题：{topic}
学生立场：{stance}
训练过程记录：
{transcript}

要求：
- summary：总体评价，一到两句话说清表现水平。
- strengths：2-4 条具体亮点（引用训练中的实际内容，不空泛）。
- weaknesses：2-4 条可改进之处，每条要指向具体环节。
- sections：按分析维度分节，如「论点构建」「证据运用」「反驳应对」，
  每节含 heading 与 body。
- score：综合分，0-100 的整数。

只输出 JSON，字段为 summary、strengths、weaknesses、sections、score。"""


def build_messages(topic: str, stance: str, transcript: str) -> list[dict]:
    """构造复盘报告阶段的对话消息。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_TEMPLATE.format(topic=topic, stance=stance, transcript=transcript),
        },
    ]
