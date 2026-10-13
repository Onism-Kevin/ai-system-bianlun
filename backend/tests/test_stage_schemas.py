"""S0-5 验收：四类 stage schema 各 3 样例（1 合法 / 2 非法）校验结果符合预期。

对齐计划书 S0-5 验收命令：pytest backend/tests/test_stage_schemas.py -v
四类 = DecomposeOut / ArgumentMap / CoachTurn / ReviewReport
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.stage_outputs import (
    ArgumentMap,
    CoachTurn,
    DecomposeOut,
    ReviewReport,
)


# ---------- DecomposeOut ----------

class TestDecomposeOut:
    def test_valid(self):
        obj = DecomposeOut.model_validate_json(
            '{"topic":"AI 进课堂","core_dispute":"效率与依赖的权衡",'
            '"pro_position":"应合理引入","con_position":"应限制使用"}'
        )
        assert obj.topic == "AI 进课堂"

    def test_invalid_missing_field(self):
        with pytest.raises(ValidationError):
            DecomposeOut.model_validate_json('{"topic":"x","core_dispute":"y"}')

    def test_invalid_wrong_type(self):
        with pytest.raises(ValidationError):
            DecomposeOut.model_validate_json(
                '{"topic":123,"core_dispute":"y","pro_position":"p","con_position":"c"}'
            )


# ---------- ArgumentMap（E-11：relation 六枚举取代旧 type；source_ref 可选） ----------

class TestArgumentMap:
    def test_valid(self):
        obj = ArgumentMap.model_validate_json(
            '{"nodes":[{"id":"c1","type":"claim","text":"论点",'
            '"source_ref":{"message_seq":3,"quote":"原文片段"}}],'
            '"edges":[{"source":"c1","target":"e1","relation":"支持"}]}'
        )
        assert len(obj.nodes) == 1
        assert obj.nodes[0].source_ref.message_seq == 3
        assert obj.edges[0].relation == "支持"

    def test_valid_without_source_ref(self):
        """source_ref 可选：综合结论/模型推断的节点可不给（E-11 prompt 规则）。"""
        obj = ArgumentMap.model_validate_json(
            '{"nodes":[{"id":"c1","type":"claim","text":"论点"}],"edges":[]}'
        )
        assert obj.nodes[0].source_ref is None

    def test_invalid_node_type(self):
        # mimo 在 bench 中因非法 type "text" 被否决——这里固化该约束
        with pytest.raises(ValidationError):
            ArgumentMap.model_validate_json(
                '{"nodes":[{"id":"c1","type":"text","text":"x"}],"edges":[]}'
            )

    def test_invalid_edge_relation(self):
        # E-11：relation 只取中文六枚举；旧 support/attack 已被取代（不并存）
        with pytest.raises(ValidationError):
            ArgumentMap.model_validate_json(
                '{"nodes":[{"id":"c1","type":"claim","text":"x"}],'
                '"edges":[{"source":"c1","target":"c1","relation":"support"}]}'
            )

    def test_invalid_edge_old_type_field(self):
        # E-11：type 字段已不存在——旧格式（edge.type=support）整体校验失败
        with pytest.raises(ValidationError):
            ArgumentMap.model_validate_json(
                '{"nodes":[{"id":"c1","type":"claim","text":"x"}],'
                '"edges":[{"source":"c1","target":"c1","type":"support"}]}'
            )

    def test_invalid_empty_nodes(self):
        with pytest.raises(ValidationError):
            ArgumentMap.model_validate_json('{"nodes":[],"edges":[]}')


# ---------- CoachTurn（E-11：增 quote_refs） ----------

class TestCoachTurn:
    def test_valid(self):
        obj = CoachTurn.model_validate_json(
            '{"question":"你的证据来源是？","focus":"证据可靠性",'
            '"hints":["查原始研究"],"quote_refs":[{"seq":3,"quote":"据调查显示…"}]}'
        )
        assert obj.focus == "证据可靠性"
        assert obj.quote_refs[0].seq == 3

    def test_valid_without_quote_refs(self):
        """quote_refs 可选（默认空列表）。"""
        obj = CoachTurn.model_validate_json(
            '{"question":"q","focus":"f","hints":[]}'
        )
        assert obj.quote_refs == []

    def test_invalid_missing_question(self):
        with pytest.raises(ValidationError):
            CoachTurn.model_validate_json('{"focus":"x"}')

    def test_invalid_hints_not_list(self):
        with pytest.raises(ValidationError):
            CoachTurn.model_validate_json('{"question":"q","focus":"f","hints":"不是列表"}')

    def test_invalid_quote_refs_not_list(self):
        with pytest.raises(ValidationError):
            CoachTurn.model_validate_json(
                '{"question":"q","focus":"f","hints":[],"quote_refs":"不是列表"}'
            )


# ---------- ReviewReport ----------

class TestReviewReport:
    def test_valid(self):
        obj = ReviewReport.model_validate_json(
            '{"summary":"整体良好","strengths":["论点清晰"],"weaknesses":["证据不足"],'
            '"sections":[{"heading":"论点构建","body":"..."}],"score":82}'
        )
        assert obj.score == 82

    def test_invalid_score_out_of_range(self):
        with pytest.raises(ValidationError):
            ReviewReport.model_validate_json(
                '{"summary":"s","score":120}'  # score > 100
            )

    def test_invalid_score_not_int(self):
        with pytest.raises(ValidationError):
            ReviewReport.model_validate_json(
                '{"summary":"s","score":"很高"}'
            )
