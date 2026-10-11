"""S0-4：structured 输出链路 — JSON 提取 + Pydantic 校验 + 错误回填重试。

职责：把模型产出的自由文本（可能带 ```json 围栏、前缀说明、多余空白）解析成
Pydantic 对象。解析/校验失败时，把字段级错误信息回填进对话再重试，最多重试
`max_retries` 次；仍失败则抛 StructuredValidationError（携带最后一次字段级错误）。

该模块不关心模型如何被调用：`generate` 是一个可注入的协发函数
`(messages) -> str`，便于单测用假模型驱动全链路。
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.core.exceptions import StructuredValidationError

T = TypeVar("T", bound=BaseModel)

JSON_FENCE = "```json"


def extract_json_text(raw: str) -> str:
    """从模型输出中提取 JSON 主体。

    依次尝试：整体解析 → 剥掉 ```json 围栏 → 截取首个 '{' 到末个 '}'。
    都失败时返回去除围栏后的原文（交由 json.loads 报错）。
    """
    text = raw.strip()
    if not text:
        return text
    # 1) 直接可解析
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass
    # 2) 剥围栏
    if text.startswith("```"):
        body = text.split("\n", 1)[1] if "\n" in text else text
        body = body.rsplit("```", 1)[0].strip()
        try:
            json.loads(body)
            return body
        except json.JSONDecodeError:
            text = body
    # 3) 截取首 '{' 到末 '}'
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass
    return text


def _format_validation_error(exc: ValidationError) -> str:
    """把 Pydantic 错误压成可回填给模型的字段级说明。"""
    lines = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        lines.append(f"- {loc}: {err['msg']}")
    return "\n".join(lines)


def generate_structured(
    messages: list[dict],
    schema: type[T],
    generate: Callable[[list[dict]], str],
    *,
    max_retries: int = 2,
) -> tuple[T, int]:
    """驱动一次 structured 生成，返回 (解析后的对象, 实际尝试次数)。

    流程：
      1. 调 generate(messages) 取文本
      2. extract_json_text 提取 JSON → schema.model_validate_json 校验
      3. 失败则把字段级错误作为 user 消息回填进 messages，重试
      4. 重试 max_retries 次后仍失败 → StructuredValidationError

    generate 抛出的非 structured 异常（如四类网关异常）原样上抛，不在此处吞掉。
    """
    transcript = list(messages)
    last_error: str = "unknown"
    attempts = 0
    for attempt in range(1, max_retries + 2):  # 1 次首发 + max_retries 次重试
        attempts = attempt
        raw = generate(transcript)
        if not raw or not raw.strip():
            last_error = "模型返回空文本"
        else:
            json_text = extract_json_text(raw)
            try:
                obj = schema.model_validate_json(json_text)
                return obj, attempts
            except json.JSONDecodeError as exc:
                last_error = f"JSON 解析失败: {exc}"
            except ValidationError as exc:
                last_error = _format_validation_error(exc)
                # 字段级错误回填，指导下一次生成
                transcript = transcript + [
                    {"role": "user", "content":
                        f"上一次输出未通过校验，字段级错误如下：\n{last_error}\n"
                        f"请修正后只输出合法 JSON。"}
                ]
                continue
        # JSON 解析失败（非字段级）也回填，提示只输出 JSON
        transcript = transcript + [
            {"role": "user", "content":
                f"上一次输出无法解析为 JSON（{last_error}）。"
                f"请只输出合法 JSON，不要任何解释或围栏。"}
        ]
    raise StructuredValidationError(
        f"structured 输出在 {attempts} 次尝试后仍未通过校验",
        raw_text=None,
        errors=[last_error],
    )
