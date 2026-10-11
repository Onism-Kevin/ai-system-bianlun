"""模型网关异常分类（S0-3a）。

按计划书 5.4 节契约，网关调用失败被归为四类，便于 API 层区分对待：
- ModelConnectionError: 连不上网关（拒绝连接/连接超时/主机不可达）
- ModelTimeoutError:     连上了但响应超时（读超时）
- ModelServerError:      网关返回 4xx/5xx 且响应体含 error 字段
- StructuredValidationError: 模型输出无法通过 Pydantic schema 校验

前三类都是传输层故障，均继承 RuntimeError，保证与桌面版（把网关调用
包在 RuntimeError 里）的调用约定兼容——调用方既可按 RuntimeError 兜底，
也可按具体子类精细处理。
"""

from __future__ import annotations


class ModelGatewayError(RuntimeError):
    """所有网关相关错误的基类（继承 RuntimeError，兼容桌面版兜底逻辑）。"""

    def __init__(self, message: str, *, detail: object = None) -> None:
        super().__init__(message)
        self.detail = detail


class ModelConnectionError(ModelGatewayError):
    """无法建立连接：网关未启动、地址错误、连接被拒或连接阶段超时。"""


class ModelTimeoutError(ModelGatewayError):
    """连接已建立但读取响应超时：模型推理过慢或网关挂起。"""


class ModelServerError(ModelGatewayError):
    """网关返回 4xx/5xx 且响应体含 error 字段。

    携带 http_status 与响应体（response_body）便于上层定位具体故障。
    """

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        response_body: object = None,
        detail: object = None,
    ) -> None:
        super().__init__(message, detail=detail)
        self.http_status = http_status
        self.response_body = response_body


class StructuredValidationError(ModelGatewayError):
    """模型输出不符合预期 schema：Pydantic 校验失败。

    携带原始文本（raw_text）与 Pydantic 错误列表（errors）供重试/日志使用。
    """

    def __init__(
        self,
        message: str,
        *,
        raw_text: str | None = None,
        errors: object = None,
        detail: object = None,
    ) -> None:
        super().__init__(message, detail=detail)
        self.raw_text = raw_text
        self.errors = errors
