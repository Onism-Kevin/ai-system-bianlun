"""S0-5 / S2-10：复盘报告（report）prompt 模板。

S2-10 重写：产出对齐 stage_outputs.ReviewReport（E-24 修订版）：
  summary / strengths / weaknesses / sections[{heading, body, dimension_id}]
  / scores: dict[str, int]（四维度分数，键名用英文 id）

输入扩展：修改稿（revisions 表 final/draft/messages 三级回退）、
反思（sessions.reflection）、rubric（四维度 + 权重）。

策略：面向教师与学生的复盘，既要给可操作的改进建议，也要给出可追踪的
分数。scores 用英文 id 作键（argument_structure 等），与 rubric.json 的
id 字段一致，前端渲染时映射到中文名。

注意：本 prompt 与 S0-3b mini-bench 时期的字段契约不同（旧版只有
score: int），mini-bench 历史数据不重跑、不与本版本对比。
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
学生修改稿：{revision}
学生反思：{reflection}
训练过程记录：
{transcript}

评价量表（四维度，按权重加权）：
- argument_structure（论证结构，权重 {w_structure}）：主张、理由、证据、反例、结论是否齐备且关系清晰。
- evidence_quality（证据质量，权重 {w_evidence}）：证据是否指向原文、课程材料或可查看来源。
- rebuttal_response（反驳与回应，权重 {w_rebuttal}）：面对追问能否识别并回应对方最强论点。
- revision_reflection（观点修订与反思，权重 {w_reflection}）：是否有方向性改进，反思是否具体。

要求：
- summary：总体评价，一到两句话说清表现水平。
- strengths：2-4 条具体亮点（引用训练中的实际内容，不空泛）。
- weaknesses：2-4 条可改进之处，每条要指向具体环节。
- sections：按四维度分节，每节含 heading、body、dimension_id
  （dimension_id 用英文 id：argument_structure/evidence_quality/
  rebuttal_response/revision_reflection）。
- scores：四维度分数，0-100 整数，键名用英文 id
  （argument_structure/evidence_quality/rebuttal_response/
  revision_reflection）。

只输出 JSON，字段为 summary、strengths、weaknesses、sections、scores。"""


def build_messages(
    topic: str,
    stance: str,
    revision: str,
    reflection: str,
    transcript: str,
    rubric: dict,
) -> list[dict]:
    """构造复盘报告阶段的对话消息。

    入参：
    - topic：训练议题
    - stance：学生立场
    - revision：学生修改稿（final/draft/messages 三级回退）
    - reflection：学生反思（NULL 时传"学生未填写反思"）
    - transcript：训练过程记录（render_messages 渲染）
    - rubric：rubric.json 完整内容（含 dimensions[].id/name/weight）
    """
    weights = {d["id"]: d["weight"] for d in rubric["dimensions"]}
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_TEMPLATE.format(
                topic=topic,
                stance=stance,
                revision=revision,
                reflection=reflection,
                transcript=transcript,
                w_structure=weights["argument_structure"],
                w_evidence=weights["evidence_quality"],
                w_rebuttal=weights["rebuttal_response"],
                w_reflection=weights["revision_reflection"],
            ),
        },
    ]
