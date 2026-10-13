"""S0-5：论证结构分析（analyze）prompt 模板（E-11 修订版）。

产出对齐 stage_outputs.ArgumentMap（errata E-11，2026-10-13 落实）：
  nodes: [{id, type∈claim|evidence|rebuttal, text, source_ref?:{message_seq, quote}}]
  edges: [{source, target, relation∈{支持,反驳,补充,依赖,限制,需要证据}}]

策略：强调节点 type 只能取三值、边 relation 只能取中文六值（relation 取代旧
type∈support/attack，两者不并存）。source_ref 只给"直接来自学生某条消息"的
节点——综合结论/模型推断留空（不确定就留空）；留空的节点其"待核实"语义由
S4 图谱层裁决。输入为带 seq 编号的训练消息（对齐 messages 表出参）。

注意：本 prompt 与 S0-3b mini-bench 时期的字段契约不同（bench 版旧枚举），
mini-bench 历史数据（spike_results.csv / model_bench_outputs.jsonl）不重跑、
不与本版本对比。
"""

from __future__ import annotations

from app.prompts import render_messages

SYSTEM_PROMPT = (
    "你是高校论证训练平台的论证结构分析助手。"
    "你只输出合法 JSON，不输出任何解释、markdown 围栏或前后缀文字。"
    "你严格遵守字段取值约束，不编造 schema 之外的类型。"
)

USER_TEMPLATE = """请分析下面这段训练对话的论证结构，输出 JSON。

训练对话（每条消息带 seq 编号，方括号内为角色）：
{messages}

要求：
- nodes：每个节点含 id、type、text；可选 source_ref。
  - id 用简短标识（如 c1/e1/r1）；
  - type 只能取 claim（论点）/ evidence（证据）/ rebuttal（反驳）三者之一；
  - text 是该节点的内容概括；
  - source_ref：{{message_seq, quote}}——仅当该节点**直接来自学生某条消息**时
    给出：message_seq 填该消息的 seq，quote 填引用的原文片段；综合结论、模型
    推断或无直接来源的节点不要给 source_ref（不确定就留空）。
- edges：每条边含 source、target、relation，表示节点间关系。
  - relation 只能取 支持 / 反驳 / 补充 / 依赖 / 限制 / 需要证据 六者之一；
  - source/target 引用 nodes 里出现过的 id。
- 至少给出 1 个节点；有明确推理关系时才连边，不要凭空造边。

只输出 JSON，字段为 nodes、edges。"""


def build_messages(messages: list[dict]) -> list[dict]:
    """构造论证分析阶段的对话消息。

    入参 messages 为训练消息列表（{seq, role, agent_role?, content}，
    对齐 messages 表出参，见 api.md §1）；按 seq 编号渲染进 prompt，
    供 source_ref 引用（E-11）。
    """
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(messages=render_messages(messages))},
    ]
