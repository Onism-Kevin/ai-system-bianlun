"""S0-3b 辅助：把网关模型清单聚合为选型报告，供生成 docs/model_selection.md。

复用 fetch_models 的取数逻辑，按渠道前缀分组，剔除 vision/batch/free/latest/
image/audio 变体，只保留可对话的文本模型，并给出代表性型号。
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_models import load_env  # noqa: E402

BASE = Path(__file__).resolve().parent.parent

# 剔除：视觉变体、批处理、免费、latest 别名、图像/音频模型
_DROP = re.compile(r"(?:-vision/|:batch$|:free$|-latest$|image|audio|lyria|tts|whisper|embedding|rerank)", re.I)


def channel_of(model_id: str) -> str:
    """取第一段作为渠道（如 cline/deepseek/deepseek-chat -> cline）。"""
    return model_id.split("/", 1)[0]


def base_of(model_id: str) -> str:
    """去掉渠道前缀后的型号名（如 cline/deepseek/deepseek-chat -> deepseek/deepseek-chat）。"""
    return model_id.split("/", 1)[1] if "/" in model_id else model_id


def pick_representative(names: list[str]) -> str:
    """挑一个代表性型号：优先最新旗舰，其次最短的通用名。"""
    # 常见旗舰关键词，按优先级
    for kw in ("opus", "gpt-6", "gpt-5.6", "gpt-5.5", "glm-5.3", "deepseek-v4-pro",
               "kimi-k3", "qwen3.8-max", "gemini-3.7-pro", "gemini-3.1-pro",
               "minimax-m3", "grok-4.7", "command-a-plus", "nova-premier"):
        for n in names:
            if kw in n.lower():
                return n
    # 否则取最短的（通常是通用别名，如 deepseek/deepseek-chat）
    return min(names, key=lambda s: (len(s), s))


def main() -> int:
    env = load_env()
    base_url = env.get("MODEL_BASE_URL", "").rstrip("/")
    api_key = env.get("MODEL_API_KEY", "")
    resp = httpx.get(
        f"{base_url}/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30.0,
        trust_env=False,
    )
    if resp.status_code >= 400:
        print(f"FATAL HTTP {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
        return 4
    models = sorted({m.get("id", "") for m in resp.json().get("data", [])} - {""})

    groups: dict[str, list[str]] = defaultdict(list)
    dropped = 0
    for mid in models:
        if _DROP.search(mid):
            dropped += 1
            continue
        groups[channel_of(mid)].append(base_of(mid))

    lines: list[str] = []
    lines.append(f"# 模型选型候选（网关共 {len(models)} 个，剔除视觉/批处理/免费/别名后 {sum(len(v) for v in groups.values())} 个文本模型）\n")
    lines.append(f"- 网关：`{base_url}`（GET /v1/models，HTTP {resp.status_code}）")
    lines.append(f"- 剔除规则：`-vision/`、`:batch`、`:free`、`-latest`、image/audio/lyria/tts/embedding/rerank 共 {dropped} 个\n")
    lines.append("| 渠道前缀 | 文本模型数 | 代表型号 |")
    lines.append("|---|---:|---|")
    for ch in sorted(groups, key=lambda c: -len(groups[c])):
        rep = pick_representative(groups[ch])
        lines.append(f"| `{ch}` | {len(groups[ch])} | `{rep}` |")
    out = BASE.parent / "docs" / "model_selection.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"WROTE {out} ({len(groups)} channels, {sum(len(v) for v in groups.values())} models)")
    # 同时落一份机器可读清单，供后续阶段选 MODEL_DEFAULT 时比对
    (BASE.parent / "docs" / "model_catalog.json").write_text(
        json.dumps({ch: groups[ch] for ch in groups}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
