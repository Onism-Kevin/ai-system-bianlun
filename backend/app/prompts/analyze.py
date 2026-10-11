"""S0-5：论证结构分析（analyze）prompt 模板。

产出对齐 stage_outputs.ArgumentMap：
  nodes: [{id, type∈claim|evidence|rebuttal, text}]
  edges: [{source, target, type∈support|attack}]

策略：强调节点 type 只能取三值、边 type 只能取两值（bench 中 mimo 因非法
type 被否决）。要求模型先通读材料，抽出论点/证据/反驳，再连支持/攻击边。
"""

from __future__ import annotations

SYSTEM_PROMPT = (
    "你是高校论证训练平台的论证结构分析助手。"
    "你只输出合法 JSON，不输出任何解释、markdown 围栏或前后缀文字。"
    "你严格遵守字段取值约束，不编造 schema 之外的类型。"
)

USER_TEMPLATE = """请分析下面这段论证的结构，输出 JSON。

论证材料：
{passage}

要求：
- nodes：每个节点含 id、type、text。
  - id 用简短标识（如 c1/e1/r1）；
  - type 只能取 claim（论点）/ evidence（证据）/ rebuttal（反驳）三者之一；
  - text 是该节点的内容概括。
- edges：每条边含 source、target、type，表示节点间关系。
  - type 只能取 support（支持）/ attack（攻击）两者之一；
  - source/target 引用 nodes 里出现过的 id。
- 至少给出 1 个节点；有明确推理关系时才连边，不要凭空造边。

只输出 JSON，字段为 nodes、edges。"""


def build_messages(passage: str) -> list[dict]:
    """构造论证分析阶段的对话消息。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(passage=passage)},
    ]
