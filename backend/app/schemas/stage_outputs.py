"""S0-5：四类 stage 输出的 Pydantic schema。

与 mini-bench（S0-3b）已验证的字段契约保持一致：
- decompose -> DecomposeOut（拆解：topic/core_dispute/pro_position/con_position）
- analyze   -> ArgumentMap（分析：nodes/edges，type 受限枚举）
- coach     -> CoachTurn（教练式追问：追问 + 参考要点）
- report    -> ReviewReport（复盘报告：分节结构化）

设计要点：
- type 用 Literal 限定取值，杜绝 bench 中 mimo 出现的非法 "text" 节点。
- CoachTurn/Report 允许自由文本字段，因为其产出本质是自然语言。
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


# ---------- 2. 论证结构分析 ----------

NodeType = Literal["claim", "evidence", "rebuttal"]
EdgeType = Literal["support", "attack"]


class ArgumentNode(BaseModel):
    id: str
    type: NodeType
    text: str


class ArgumentEdge(BaseModel):
    source: str
    target: str
    type: EdgeType


class ArgumentMap(BaseModel):
    """论证结构：论点/证据/反驳节点 + 支持/攻击边。"""

    nodes: list[ArgumentNode] = Field(min_length=1)
    edges: list[ArgumentEdge] = Field(default_factory=list)


# ---------- 3. 教练式追问 ----------


class CoachTurn(BaseModel):
    """教练式追问：一轮追问 + 可选参考要点，供教师/学生参考。"""

    question: str = Field(description="本轮追问问题")
    focus: str = Field(description="本轮考察的能力点或思维盲区")
    hints: list[str] = Field(default_factory=list, description="参考要点/提示")


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
