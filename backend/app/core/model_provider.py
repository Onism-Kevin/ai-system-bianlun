"""模型网关 provider 抽象与实现（S0-3a，方案 A）。

设计目标：把「调用 OpenAI 兼容网关」这一传输细节从业务逻辑里隔离出来，
使五阶段 Agent 只依赖 generate_stream 这一个窄接口。两个实现：

- OpenAICompatProvider: 真实实现，走 httpx 打 POST {base_url}/chat/completions
  （stream=True），按四类异常契约分类错误。
- FakeProvider: 离线实现，回放预设的文本片段，用于单测与本地联调，
  完全不触网、不需要 MODEL_API_KEY。

传输层缺陷（连接/读超时/HTTP 错误）统一翻译成 core.exceptions 里的
四类异常；文本内容本身按 UTF-8 逐块 yield，供上层做流式渲染与截断。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Protocol

import httpx

from app.core.exceptions import (
    ModelConnectionError,
    ModelServerError,
    ModelTimeoutError,
)


class ModelProvider(Protocol):
    """五阶段 Agent 依赖的最窄接口：流式产出文本块。"""

    def generate_stream(
        self,
        *,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        timeout: float = 120.0,
    ) -> Iterator[str]:
        """返回一个文本块迭代器；错误以 core.exceptions 四类异常抛出。"""
        ...


class OpenAICompatProvider:
    """OpenAI 兼容网关的真实流式实现。

    错误映射：
    - httpx.ConnectError / ConnectTimeout -> ModelConnectionError
    - httpx.ReadTimeout                   -> ModelTimeoutError
    - 其余 httpx 传输错误                   -> ModelConnectionError
    - HTTP 4xx/5xx 且 JSON 体含 "error"     -> ModelServerError
    """

    def __init__(self, base_url: str, api_key: str) -> None:
        # 去掉尾部斜杠，拼接时统一加 /chat/completions
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def generate_stream(
        self,
        *,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        timeout: float = 120.0,
    ) -> Iterator[str]:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }

        try:
            with httpx.Client(timeout=timeout) as client:
                with client.stream(
                    "POST", url, headers=headers, json=payload
                ) as response:
                    # 非 2xx：读取完整响应体再判定是否为含 error 的服务端错误
                    if response.status_code >= 400:
                        body = response.read()
                        raise self._server_error_from_response(
                            response.status_code, body
                        )
                    yield from self._iter_content(response)
        except ModelServerError:
            # 已分类的服务端错误，直接上抛
            raise
        except httpx.ConnectError as exc:
            raise ModelConnectionError(
                f"无法连接模型网关 {url}: {exc}"
            ) from exc
        except httpx.ConnectTimeout as exc:
            raise ModelConnectionError(
                f"连接模型网关超时 {url}: {exc}"
            ) from exc
        except httpx.ReadTimeout as exc:
            raise ModelTimeoutError(
                f"读取模型网关响应超时 {url}: {exc}"
            ) from exc
        except httpx.HTTPError as exc:
            # 其余传输层错误（传输中断、协议错误等）归为连接类
            raise ModelConnectionError(
                f"模型网关传输错误 {url}: {exc}"
            ) from exc

    def _iter_content(self, response: httpx.Response) -> Iterator[str]:
        """解析 OpenAI 流式 SSE 响应，逐块产出 delta 文本。"""
        for line in response.iter_lines():
            if not line:
                continue
            # SSE 行形如 "data: {...}"，终止标记为 "data: [DONE]"
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                # 畸形分片：记录但不中断整条流
                continue
            choices = obj.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            text = delta.get("content")
            if text:
                yield text

    @staticmethod
    def _server_error_from_response(
        status_code: int, body: bytes
    ) -> ModelServerError:
        """把 HTTP 错误响应翻译成 ModelServerError，尽量解析出 error 字段。"""
        parsed: object = None
        try:
            parsed = body.decode("utf-8", errors="replace")
            parsed = json.loads(parsed)
        except json.JSONDecodeError:
            pass  # 保留原始文本
        return ModelServerError(
            f"模型网关返回 HTTP {status_code}",
            http_status=status_code,
            response_body=parsed,
        )


class FakeProvider:
    """离线假 provider：回放预设片段，供单测/联调使用，不触网。

    用法：
        provider = FakeProvider(chunks=["你好", "，世界"])
        text = "".join(provider.generate_stream(model="x", messages=[]))

    也可注入一个异常（在指定序号的分片处抛出），用于测试错误分类链路：
        provider = FakeProvider(chunks=["a"], error=ModelTimeoutError("模拟超时"))
    """

    def __init__(
        self,
        chunks: list[str] | None = None,
        error: Exception | None = None,
        error_after: int = 0,
    ) -> None:
        self._chunks = chunks if chunks is not None else []
        self._error = error
        self._error_after = error_after

    def generate_stream(
        self,
        *,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        timeout: float = 120.0,
    ) -> Iterator[str]:
        for index, chunk in enumerate(self._chunks):
            if self._error is not None and index >= self._error_after:
                raise self._error
            yield chunk
        # 分片出完后，若仍有未抛出的异常（error_after >= len(chunks)），此处抛出
        if self._error is not None and len(self._chunks) <= self._error_after:
            raise self._error
