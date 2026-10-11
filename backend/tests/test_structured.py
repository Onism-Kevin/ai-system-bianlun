"""S0-4 单测：structured 链路（JSON 提取 + Pydantic 校验 + 错误回填重试）。

用一个可编排的假模型 `ScriptedModel` 驱动全链路，不触网、不依赖 key。
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.core.exceptions import StructuredValidationError
from app.core.structured import extract_json_text, generate_structured


class Item(BaseModel):
    name: str
    count: int


class ScriptedModel:
    """按脚本顺序返回文本；记录每次收到的 messages 供断言回填。"""

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = list(outputs)
        self.calls: list[list[dict]] = []

    def __call__(self, messages: list[dict]) -> str:
        self.calls.append([dict(m) for m in messages])
        if not self._outputs:
            raise AssertionError("模型脚本已耗尽但仍在调用")
        return self._outputs.pop(0)


class TestExtractJsonText:
    def test_plain_json_passthrough(self):
        assert extract_json_text('{"name":"a","count":1}') == '{"name":"a","count":1}'

    def test_fenced_json_stripped(self):
        raw = '```json\n{"name":"a","count":1}\n```'
        assert extract_json_text(raw) == '{"name":"a","count":1}'

    def test_json_with_prefix_prose(self):
        raw = '好的，结果如下：\n{"name":"a","count":1}\n希望有帮助'
        assert extract_json_text(raw) == '{"name":"a","count":1}'

    def test_nested_braces_resolved(self):
        raw = '前缀 {"name":"a","count":1} 后缀'
        assert extract_json_text(raw) == '{"name":"a","count":1}'


class TestGenerateStructured:
    def test_first_pass_valid(self):
        model = ScriptedModel(['{"name":"a","count":1}'])
        obj, attempts = generate_structured(
            [{"role": "user", "content": "go"}], Item, model, max_retries=2
        )
        assert (obj.name, obj.count) == ("a", 1)
        assert attempts == 1
        assert len(model.calls) == 1

    def test_fenced_first_pass_counts_as_valid(self):
        model = ScriptedModel(['```json\n{"name":"a","count":1}\n```'])
        obj, attempts = generate_structured(
            [{"role": "user", "content": "go"}], Item, model, max_retries=2
        )
        assert (obj.name, obj.count) == ("a", 1)
        assert attempts == 1

    def test_retry_with_error_backfill_then_success(self):
        # 第 1 次：字段缺失（缺 count）→ 第 2 次：合法
        model = ScriptedModel([
            '{"name":"a"}',
            '{"name":"a","count":2}',
        ])
        obj, attempts = generate_structured(
            [{"role": "user", "content": "go"}], Item, model, max_retries=2
        )
        assert (obj.name, obj.count) == ("a", 2)
        assert attempts == 2
        assert len(model.calls) == 2
        # 第 2 次调用的 messages 里应含字段级回填
        backfill = model.calls[1]
        assert any("count" in m["content"] for m in backfill if m["role"] == "user")

    def test_exhausted_retries_raises_with_field_errors(self):
        # 一直缺 count → 1 首发 + 2 重试 = 3 次，然后抛
        model = ScriptedModel(['{"name":"a"}'] * 3)
        with pytest.raises(StructuredValidationError) as ei:
            generate_structured(
                [{"role": "user", "content": "go"}], Item, model, max_retries=2
            )
        assert len(model.calls) == 3
        assert ei.value.errors  # 携带字段级错误
        assert any("count" in str(e) for e in ei.value.errors)

    def test_bad_json_also_retries(self):
        # 非 JSON 文本 → 回填提示只输出 JSON → 第 2 次合法
        model = ScriptedModel(["这不是 JSON", '{"name":"a","count":1}'])
        obj, attempts = generate_structured(
            [{"role": "user", "content": "go"}], Item, model, max_retries=2
        )
        assert attempts == 2
        assert obj.count == 1

    def test_gateway_error_propagates_not_swallowed(self):
        # generate 抛非 structured 异常时应原样上抛
        def boom(messages):
            raise ValueError("传输层故障")

        with pytest.raises(ValueError):
            generate_structured(
                [{"role": "user", "content": "go"}], Item, boom, max_retries=2
            )
