"""S0-5：四类 stage 输出的 Pydantic schema。

与 mini-bench（S0-3b）已验证的字段契约保持一致（E-11 修订后）：
- decompose -> DecomposeOut（拆解：topic/core_dispute/pro_position/con_position）
- analyze   -> ArgumentMap（分析：nodes/edges；edge.relation 中文六枚举取代旧
  edge.type（support/attack），node 带 source_ref 原文定位——errata E-11，
  2026-10-13 落实）
- coach     -> CoachTurn（教练式追问/反方对练共用：追问 + 参考要点 + quote_refs
  学生原文引用——errata E-11）
- report    -> ReviewReport（复盘报告：分节结构化）

设计要点：
- node type 用 Literal 限定取值，杜绝 bench 中 mimo 出现的非法 "text" 节点。
- CoachTurn/Report 允许自由文本字段，因为其产出本质是自然语言。
- analyze/coach 的 prompt 入参为带 seq 的训练消息（对齐 messages 表出参，见
  api.md §1 messages 行），供 source_ref / quote_refs 引用学生原文（E-11）。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------- 1. 议题拆解 ----------


class DecomposeOut(BaseModel):
    """议题拆解：把一个议题拆成核心争议与正反立场。"""

    topic: str = Field(description="议题名")
    core_dispute: str = Field(description="核心争议，一句话")
    pro_position: str = Field(description="正方核心立场")
    con_position: str = Field(description="反方核心立场")


# ---------- 1b. 议题探索（S2-7，api.md:43） ----------


class ExploreOut(BaseModel):
    """议题探索：ExploreOut 独立 schema（api.md:43，S1-7 用户裁定，E-11）。

    与 DecomposeOut 不共享——decompose 是 spike/mini-bench 用途（topic/
    core_dispute/pro_position/con_position）；explore 是 S2-7 端点用途
    （concepts/scope/subquestions/stakeholders）。不进 STAGE_SCHEMAS。

    前端易失性：explore 结果不落库（MVP 裁定），刷新页面丢失。
    S2-F7 需处理（sessionStorage 恢复 或 UI 提示）。
    """

    concepts: list[str] = Field(description="核心概念，每项格式'概念：说明'")
    scope: str = Field(description="议题讨论的范围与边界")
    subquestions: list[str] = Field(description="子问题，每项格式'子问题：说明'")
    stakeholders: list[str] = Field(description="利益相关方，每项格式'群体：说明'")


# ---------- 2. 论证结构分析 ----------

NodeType = Literal["claim", "evidence", "rebuttal"]
# E-11：edge.relation 取代旧 edge.type（support/attack）——字段名与枚举全变，
# 两字段不并存；与 S4 图谱契约共用同一枚举（api.md §1 analyze 出参）。
EdgeRelation = Literal["支持", "反驳", "补充", "依赖", "限制", "需要证据"]


class SourceRef(BaseModel):
    """原文定位：来自训练对话中的某条消息（E-11）。"""

    message_seq: int = Field(description="来源消息的 seq（全局自增，messages 表主键）")
    quote: str = Field(description="引用的原文片段")


class ArgumentNode(BaseModel):
    id: str
    type: NodeType
    text: str
    # E-11 纯增字段：节点直接来自学生某条消息时给出；综合结论/模型推断/
    # 无直接来源的节点留空（prompt 侧"不确定就留空"）
    source_ref: SourceRef | None = None


class ArgumentEdge(BaseModel):
    source: str
    target: str
    # E-11：取代旧 type 字段（support/attack 已废弃，不并存）
    relation: EdgeRelation


class ArgumentMap(BaseModel):
    """论证结构：论点/证据/反驳节点 + 关系边（relation 中文六枚举，E-11）。"""

    nodes: list[ArgumentNode] = Field(min_length=1)
    edges: list[ArgumentEdge] = Field(default_factory=list)


# ---------- 3. 教练式追问 / 反方对练（共用 schema） ----------


class QuoteRef(BaseModel):
    """追问针对的学生原文引用（E-11，S2-9 验收依赖）。"""

    seq: int = Field(description="被引用学生消息的 seq")
    quote: str = Field(description="引用的原文片段")


class CoachTurn(BaseModel):
    """教练式追问/反方对练：一轮追问 + 可选参考要点 + 学生原文引用（E-11）。"""

    question: str = Field(description="本轮追问问题")
    focus: str = Field(description="本轮考察的能力点或思维盲区")
    hints: list[str] = Field(default_factory=list, description="参考要点/提示")
    quote_refs: list[QuoteRef] = Field(
        default_factory=list, description="追问针对的学生原文引用 [{seq, quote}]（E-11）"
    )


# ---------- 4. 复盘报告 ----------


class ReportSection(BaseModel):
    heading: str
    body: str


class ReviewReport(BaseModel):
    """复盘报告：分节结构化，便于前端渲染与教师批阅。"""

    summary: str = Field(description="总体评价")
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    sections: list[ReportSection] = Field(default_factory=list)
    score: int = Field(ge=0, le=100, description="综合分 0-100")


# ---------- stage -> schema 映射 ----------

STAGE_SCHEMAS = {
    "decompose": DecomposeOut,
    "analyze": ArgumentMap,
    "coach": CoachTurn,
    "report": ReviewReport,
}
