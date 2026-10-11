"""S0-3a 单测：四类异常分类 + FakeProvider 离线行为。

完全离线、不依赖 MODEL_API_KEY / 网络 / MySQL，可直接
`pytest backend/tests/test_exceptions.py -v` 跑通。
"""

from __future__ import annotations

import pytest

from app.core.exceptions import (
    ModelConnectionError,
    ModelGatewayError,
    ModelServerError,
    ModelTimeoutError,
    StructuredValidationError,
)
from app.core.model_provider import FakeProvider


class TestExceptionHierarchy:
    """四类异常均继承 ModelGatewayError(RuntimeError)。"""

    def test_all_inherit_runtime_error(self):
        for cls in (
            ModelConnectionError,
            ModelTimeoutError,
            ModelServerError,
            StructuredValidationError,
        ):
            assert issubclass(cls, RuntimeError)

    def test_all_inherit_gateway_base(self):
        for cls in (
            ModelConnectionError,
            ModelTimeoutError,
            ModelServerError,
            StructuredValidationError,
        ):
            assert issubclass(cls, ModelGatewayError)

    def test_server_error_carries_http_status(self):
        err = ModelServerError("boom", http_status=502, response_body={"error": "upstream"})
        assert err.http_status == 502
        assert err.response_body == {"error": "upstream"}
        assert isinstance(err, RuntimeError)

    def test_structured_error_carries_raw_and_errors(self):
        err = StructuredValidationError(
            "bad json", raw_text="{oops", errors=[{"loc": ("a",)}]
        )
        assert err.raw_text == "{oops"
        assert err.errors == [{"loc": ("a",)}]


class TestFakeProvider:
    """FakeProvider 回放预设片段，用于离线驱动错误分类链路。"""

    def test_replays_chunks(self):
        provider = FakeProvider(chunks=["你好", "，", "世界"])
        out = "".join(
            provider.generate_stream(model="m", messages=[])
        )
        assert out == "你好，世界"

    def test_empty_by_default(self):
        provider = FakeProvider()
        assert list(provider.generate_stream(model="m", messages=[])) == []

    def test_raises_connection_error(self):
        provider = FakeProvider(
            chunks=[], error=ModelConnectionError("模拟连接失败")
        )
        with pytest.raises(ModelConnectionError):
            list(provider.generate_stream(model="m", messages=[]))

    def test_raises_timeout_error(self):
        provider = FakeProvider(
            chunks=["partial"], error=ModelTimeoutError("模拟读超时"), error_after=1
        )
        with pytest.raises(ModelTimeoutError):
            list(provider.generate_stream(model="m", messages=[]))

    def test_raises_server_error(self):
        provider = FakeProvider(
            chunks=[],
            error=ModelServerError("HTTP 500", http_status=500),
        )
        with pytest.raises(ModelServerError):
            list(provider.generate_stream(model="m", messages=[]))

    def test_raises_structured_validation_error(self):
        provider = FakeProvider(
            chunks=[],
            error=StructuredValidationError("schema 不符"),
        )
        with pytest.raises(StructuredValidationError):
            list(provider.generate_stream(model="m", messages=[]))

    def test_yields_prefix_then_raises(self):
        """error_after 之前正常产出，之后抛出——模拟流中断场景。"""
        provider = FakeProvider(
            chunks=["a", "b", "c"],
            error=ModelTimeoutError("中断"),
            error_after=2,
        )
        received = []
        with pytest.raises(ModelTimeoutError):
            for chunk in provider.generate_stream(model="m", messages=[]):
                received.append(chunk)
        assert received == ["a", "b"]
