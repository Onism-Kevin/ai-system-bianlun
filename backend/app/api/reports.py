"""S2-10：复盘报告 stage API（api.md:47-49）。

POST /api/sessions/{id}/reports — 无 body，读三表 + rubric 生成报告。
GET  /api/sessions/{id}/reports — 返回最新一份。
GET  /api/reports/{id} — 按 id 返回。

流程（POST）：
get_current_user（401）→ can_read_session（404）→ 读 rubric →
读修改稿（final → draft → messages 三级回退）→ 读反思 →
读 messages（user 20 + assistant 5）→ build_messages →
generate_structured → 校验 scores → 计算 overall_score →
拼 summary_text → 落库 reports 表 → 返回 ReviewReport。

错误码（E-23 澄清）：
- 401：未登录 / Cookie 无效
- 403：非 owner（api.md:47 字面）
- 404：会话不存在或 private 越权；GET 无报告
- 502：StructuredValidationError（E-23：reports 端点映射 502，非 422）
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import can_read_session, get_current_user
from app.core.database import get_db
from app.core.exceptions import StructuredValidationError
from app.core.model_provider import ModelProvider
from app.core.structured import generate_structured
from app.models.message import Message
from app.models.revision import Revision
from app.models.report import Report
from app.models.session import TrainingSession
from app.models.user import User
from app.prompts.report import build_messages
from app.prompts import render_messages
from app.schemas.stage_outputs import ReviewReport
from app.services.debate_runner import build_provider

router = APIRouter(prefix="/api", tags=["reports"])

logger = logging.getLogger(__name__)

# MVP 窗口限制（同 coach_turn）
_USER_WINDOW = 20
_AI_WINDOW = 5

# E-24：四维度英文 id（与 rubric.json 一致）
REQUIRED_DIMS = {
    "argument_structure",
    "evidence_quality",
    "rebuttal_response",
    "revision_reflection",
}

_RUBRIC_PATH = Path(__file__).resolve().parent.parent / "rubric" / "rubric.json"

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="资源不存在或无权访问",
)
_FORBIDDEN = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="仅会话所有者可生成报告",
)
_UNPROCESSABLE = status.HTTP_422_UNPROCESSABLE_CONTENT
_BAD_GATEWAY = status.HTTP_502_BAD_GATEWAY


def _load_rubric() -> dict:
    """加载 rubric.json（S1-9 定稿，四维度 v1.0）。"""
    with open(_RUBRIC_PATH, encoding="utf-8") as f:
        return json.load(f)


def _read_revision(db: Session, session_id: int, student_id: int) -> tuple[str, str]:
    """读学生修改稿（三级回退）。

    返回 (revision_text, 标注)。
    1. final revision → (content, "定稿观点")
    2. latest draft → (content, "草稿观点（未定稿）")
    3. messages → (拼接 user 消息, "原始发言（无修改稿）")
    """
    # 1. final
    final = db.scalars(
        select(Revision)
        .where(Revision.session_id == session_id, Revision.student_id == student_id,
               Revision.status == "final")
        .order_by(Revision.version.desc())
        .limit(1)
    ).first()
    if final is not None:
        return final.content, "定稿观点"

    # 2. latest draft
    draft = db.scalars(
        select(Revision)
        .where(Revision.session_id == session_id, Revision.student_id == student_id,
               Revision.status == "draft")
        .order_by(Revision.version.desc())
        .limit(1)
    ).first()
    if draft is not None:
        return draft.content, "草稿观点（未定稿）"

    # 3. messages fallback
    rows = db.scalars(
        select(Message)
        .where(Message.session_id == session_id, Message.role == "user",
               Message.status != "streaming")
        .order_by(Message.seq.asc())
    ).all()
    if rows:
        text = "\n".join(row.content for row in rows)
        return text, "原始发言（无修改稿）"

    return "", "无发言"


def _generate_text(provider: ModelProvider, model: str, messages: list[dict]) -> str:
    """把 provider 流式输出收集为单个字符串（供 generate_structured 使用）。"""
    chunks: list[str] = []
    for chunk in provider.generate_stream(model=model, messages=messages):
        chunks.append(chunk)
    return "".join(chunks)


def _build_summary_text(report: ReviewReport, rubric: dict) -> str:
    """拼 summary_text：sections 按 rubric 四维度顺序 + strengths/weaknesses。

    sections 按 dimension_id 排序（不按 heading 字符串匹配——模型输出的
    heading 可能与 rubric name 不完全一致）。
    """
    rubric_order = [d["id"] for d in rubric["dimensions"]]
    sections_by_dim = {s.dimension_id: s for s in report.sections}
    ordered_sections = [
        sections_by_dim[d] for d in rubric_order if d in sections_by_dim
        # 缺失维度的 section 静默跳过（不占位）。
        # 模型可能未生成某个维度的分节（尤其 D4 在无反思时）。
        # MVP 接受 summary_text 缺节；S2-F7 前端按存在的 ## 标题渲染。
        # S5 若需要"维度完整性校验"，在此处加占位或 502。
    ]

    parts: list[str] = []
    for s in ordered_sections:
        parts.append(f"## {s.heading}\n{s.body}")

    if report.strengths:
        parts.append(
            "**亮点：**\n"
            + "\n".join(f"{i+1}. {s}" for i, s in enumerate(report.strengths))
        )
    if report.weaknesses:
        parts.append(
            "**改进建议：**\n"
            + "\n".join(f"{i+1}. {w}" for i, w in enumerate(report.weaknesses))
        )

    return "\n\n".join(parts)


@router.post("/sessions/{session_id}/reports", status_code=status.HTTP_201_CREATED)
def create_report(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReviewReport:
    """生成复盘报告（api.md:47）。

    流程：
    1. get_current_user → 401；can_read_session → 404
    2. owner 校验 → 403（api.md:47 字面）
    3. 读 rubric.json
    4. 读修改稿（final → draft → messages 三级回退）
    5. 读反思（sessions.reflection，NULL → "学生未填写反思"）
    6. 读 messages（user 20 + assistant 5，按 seq 交错）
    7. build_messages → generate_structured(ReviewReport)
    8. 校验 scores 含全部四维 → 否则 StructuredValidationError → 502
    9. 计算 overall_score = Σ(scores[d] × weight[d])
    10. 拼 summary_text（sections 按 rubric 顺序 + strengths/weaknesses）
    11. 落库 reports 表
    12. 返回 ReviewReport（score = overall_score）
    """
    session = db.get(TrainingSession, session_id)
    if session is None or not can_read_session(db, user, session):
        raise _NOT_FOUND
    if session.owner_id != user.id:
        raise _FORBIDDEN

    rubric = _load_rubric()
    rubric_version = rubric.get("rubric_version", "v1.0")

    # 读修改稿（三级回退）
    revision_text, revision_label = _read_revision(db, session_id, user.id)

    # 读反思（NULL → "学生未填写反思"）
    reflection = session.reflection if session.reflection and session.reflection.strip() else "学生未填写反思"

    # 读 messages（user 20 + assistant 5，按 seq 交错）
    user_rows = db.scalars(
        select(Message)
        .where(Message.session_id == session_id, Message.role == "user",
               Message.status != "streaming")
        .order_by(Message.seq.desc())
        .limit(_USER_WINDOW + 1)
    ).all()
    if len(user_rows) > _USER_WINDOW:
        logger.warning("会话 user 消息超过 %d 条，report 只读最近 %d 条",
                       _USER_WINDOW, _USER_WINDOW)
        user_rows = user_rows[:_USER_WINDOW]
    user_rows.reverse()

    ai_rows = db.scalars(
        select(Message)
        .where(Message.session_id == session_id, Message.role == "assistant",
               Message.status != "streaming")
        .order_by(Message.seq.desc())
        .limit(_AI_WINDOW)
    ).all()
    ai_rows.reverse()

    history = sorted([*user_rows, *ai_rows], key=lambda r: r.seq)
    transcript = render_messages([
        {"seq": r.seq, "role": r.role, "agent_role": r.agent_role, "content": r.content}
        for r in history
    ])

    # stance = revision content（MVP 简化：学生立场见修改稿）
    stance = revision_text if revision_text else "学生未提供明确立场"

    # 构造 prompt 消息
    prompt_messages = build_messages(
        topic=session.topic,
        stance=stance,
        revision=revision_text if revision_text else f"（{revision_label}）",
        reflection=reflection,
        transcript=transcript,
        rubric=rubric,
    )

    provider = build_provider()

    from app.core.config import get_settings  # 延迟导入

    settings = get_settings()
    try:
        result, _ = generate_structured(
            prompt_messages,
            ReviewReport,
            lambda msgs: _generate_text(provider, settings.model_default, msgs),
        )
        # 校验 scores 含全部四维（E-24）——在 try 内，映射 502
        if set(result.scores.keys()) != REQUIRED_DIMS:
            raise StructuredValidationError(
                f"scores 必须包含全部四维度 {sorted(REQUIRED_DIMS)}，"
                f"实际: {sorted(result.scores.keys())}"
            )
    except StructuredValidationError as exc:
        raise HTTPException(
            status_code=_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    # 计算 overall_score = Σ(scores[d] × weight[d])
    weights = {d["id"]: d["weight"] for d in rubric["dimensions"]}
    overall = sum(result.scores[d] * weights[d] for d in REQUIRED_DIMS)
    result.score = round(overall)

    # 拼 summary_text
    summary_text = _build_summary_text(result, rubric)

    # 落库 reports 表
    report_row = Report(
        session_id=session_id,
        rubric_version=rubric_version,
        scores=result.scores,
        overall_score=Decimal(str(round(overall, 2))),
        summary_text=summary_text,
    )
    db.add(report_row)
    db.commit()
    db.refresh(report_row)

    return result


@router.get("/sessions/{session_id}/reports")
def get_latest_report(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """返回会话最新一份报告（api.md:48）。"""
    session = db.get(TrainingSession, session_id)
    if session is None or not can_read_session(db, user, session):
        raise _NOT_FOUND

    row = db.scalars(
        select(Report)
        .where(Report.session_id == session_id)
        .order_by(Report.id.desc())
        .limit(1)
    ).first()
    if row is None:
        raise _NOT_FOUND

    return {
        "id": row.id,
        "session_id": row.session_id,
        "rubric_version": row.rubric_version,
        "scores": row.scores,
        "overall_score": float(row.overall_score),
        "summary_text": row.summary_text,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/reports/{report_id}")
def get_report_by_id(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """按 id 返回报告（api.md:49）。"""
    row = db.get(Report, report_id)
    if row is None:
        raise _NOT_FOUND

    # 权限校验：报告所属会话必须对用户可见
    session = db.get(TrainingSession, row.session_id)
    if session is None or not can_read_session(db, user, session):
        raise _NOT_FOUND

    return {
        "id": row.id,
        "session_id": row.session_id,
        "rubric_version": row.rubric_version,
        "scores": row.scores,
        "overall_score": float(row.overall_score),
        "summary_text": row.summary_text,
        "created_at": row.created_at.isoformat(),
    }
