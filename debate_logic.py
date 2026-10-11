# debate_logic.py
import json
import logging

import requests

from debate_config import ROLES, PHASE_INSTRUCTIONS, OLLAMA_URL

logger = logging.getLogger(__name__)

# 单条历史记录进入 prompt 的最大字数
_HISTORY_ENTRY_LIMIT = 300
# 辩论阶段保留的历史条数
_DEBATE_HISTORY_LIMIT = 6
# 总结陈词保留的本方记录条数
_SUMMARY_HISTORY_LIMIT = 8


def _truncate(text, limit=_HISTORY_ENTRY_LIMIT):
    """截断超长文本，超出部分以省略号代替"""
    if len(text) > limit:
        return text[:limit] + "……"
    return text


def build_user_prompt(role, phase, topic, debate_history):
    """构建用户提示词

    带上下文窗口控制，避免小模型上下文溢出导致越到后期越慢越差：
    - 辩论阶段：只保留最近 6 条历史，每条内容截断到 300 字
    - 总结陈词：只保留本方最多 8 条记录，每条同样截断
    - 开场陈词：不带历史
    """
    stance = "支持" if role == "正方" else "反对"
    parts = [
        f"辩题: {topic}",
        f"你的角色: {role}",
        f"你的立场: {stance}（绝不可更改）",
        f"阶段任务: {phase}",
    ]
    if phase in PHASE_INSTRUCTIONS:
        parts.append(PHASE_INSTRUCTIONS[phase])

    if debate_history:
        if phase == "总结陈词":
            own_entries = [
                entry for entry in debate_history if entry['role'] == role
            ][-_SUMMARY_HISTORY_LIMIT:]
            if own_entries:
                parts.append("\n你方之前的辩论要点：")
                for entry in own_entries:
                    parts.append(f"\n【{entry['role']}·{entry['phase']}】")
                    parts.append(_truncate(entry['content']))
        elif phase == "辩论阶段":
            recent_entries = list(debate_history)[-_DEBATE_HISTORY_LIMIT:]
            if recent_entries:
                parts.append("\n之前的辩论内容：")
                for entry in recent_entries:
                    parts.append(f"\n【{entry['role']}·{entry['phase']}】")
                    parts.append(_truncate(entry['content']))

    return "\n".join(parts)


def stream_chat(model, messages, temperature=0.7, timeout=120):
    """健壮的流式对话，yield 文本块

    与 stream_speech 使用同一套流式实现，但接受完整的 messages 列表，
    供人机对话等自定义 system prompt 的场景复用。

    Args:
        model: 模型名称
        messages: 完整的 OpenAI/Ollama 风格消息列表
        temperature: 温度参数
        timeout: 请求超时秒数

    Raises:
        RuntimeError: 无法连接 Ollama，或 Ollama 返回错误
    """
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {"temperature": temperature},
    }

    try:
        response = requests.post(
            OLLAMA_URL, json=payload, stream=True, timeout=timeout
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            f"无法连接 Ollama，请确认 ollama serve 已启动且地址正确: {exc}"
        ) from exc

    for line in response.iter_lines():
        if not line:
            continue
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError as exc:
            logger.warning("跳过畸形的流式数据行: %r (%s)", line[:200], exc)
            continue
        if not isinstance(chunk, dict):
            logger.warning("跳过非对象的流式数据行: %r", line[:200])
            continue
        if "error" in chunk:
            raise RuntimeError(f"Ollama 返回错误: {chunk['error']}")
        content = (chunk.get("message") or {}).get("content", "")
        if content:
            yield content


def stream_speech(debate_history, role, phase, topic, temperature=None, model_name=None):
    """
    流式生成发言

    Args:
        debate_history: 辩论历史
        role: 角色（正方/反方/裁判）
        phase: 阶段
        topic: 辩题
        temperature: 温度参数（如果为None则使用角色默认值）
        model_name: 模型名称（如果为None则使用该角色配置的模型）
    """
    cfg = ROLES[role]
    temp = temperature if temperature is not None else cfg["temperature"]
    model = model_name if model_name else cfg["model"]

    messages = [
        {"role": "system", "content": cfg["system"]},
        {"role": "user", "content": build_user_prompt(role, phase, topic, debate_history)}
    ]

    yield from stream_chat(model, messages, temperature=temp, timeout=120)
