"""S0-3b：生成逐条「模型 × 渠道」明细，跨渠道按型号去重，供勾选 MODEL_DEFAULT。

读取网关 /v1/models，剔除视觉/批处理/免费/别名变体，把同一型号在多个渠道的
出现合并为一行（列出全部可用渠道），按厂商/家族排序写入 docs/model_catalog.md。
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_models import load_env  # noqa: E402

BASE = Path(__file__).resolve().parent.parent          # backend/
DOCS = BASE.parent / "docs"                             # 项目根/docs

_DROP = re.compile(
    r"(?:-vision/|:(?:batch|free)(?=:|$)|-latest$|image|audio|lyria|tts|whisper|embedding|rerank)",
    re.I,
)

# 按厂商关键词归类到家族，仅用于排序分组
_FAMILIES = [
    ("Anthropic", re.compile(r"anthropic|claude", re.I)),
    ("OpenAI", re.compile(r"openai|gpt-|^o[134]|o3-mini|o4-mini", re.I)),
    ("Google", re.compile(r"google|gemini|gemma", re.I)),
    ("DeepSeek", re.compile(r"deepseek", re.I)),
    ("Qwen", re.compile(r"qwen", re.I)),
    ("GLM", re.compile(r"glm|z-ai", re.I)),
    ("Kimi", re.compile(r"kimi|moonshot", re.I)),
    ("Meta", re.compile(r"meta|llama", re.I)),
    ("Mistral", re.compile(r"mistral|mixtral|codestral|ministral", re.I)),
    ("MiniMax", re.compile(r"minimax", re.I)),
    ("Grok", re.compile(r"x-ai|grok", re.I)),
    ("Cohere", re.compile(r"cohere|command", re.I)),
    ("Amazon", re.compile(r"amazon|nova", re.I)),
    ("ByteDance", re.compile(r"bytedance|seed", re.I)),
    ("Tencent", re.compile(r"tencent|hunyuan|hy3|hy4", re.I)),
    ("Xiaomi", re.compile(r"xiaomi|mimo", re.I)),
    ("StepFun", re.compile(r"stepfun|step-", re.I)),
]


def channel_of(mid: str) -> str:
    return mid.split("/", 1)[0]


def base_of(mid: str) -> str:
    return mid.split("/", 1)[1] if "/" in mid else mid


def family_of(name: str) -> str:
    for fam, pat in _FAMILIES:
        if pat.search(name):
            return fam
    return "其他"


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
    # 型号 -> 渠道集合（已剔除变体）
    catalog: dict[str, set[str]] = defaultdict(set)
    for mid in models:
        if _DROP.search(mid):
            continue
        catalog[base_of(mid)].add(channel_of(mid))

    grouped: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
    for name, chans in catalog.items():
        grouped[family_of(name)].append((name, sorted(chans)))

    lines: list[str] = []
    lines.append(f"# 模型明细（型号 × 渠道，跨渠道去重共 {len(catalog)} 个型号）\n")
    lines.append(f"- 来源：`{base_url}/models`（HTTP {resp.status_code}，原始 {len(models)} 项）")
    lines.append("- 已剔除：`-vision/`、`:batch`、`:free`、`-latest`、image/audio/lyria/tts/embedding/rerank")
    lines.append("- 「渠道」列为该型号可用的渠道前缀；写入 backend/.env 的 MODEL_DEFAULT 时用**完整 id**（`渠道/型号`）\n")

    fam_order = [f for f, _ in _FAMILIES] + ["其他"]
    for fam in fam_order:
        entries = grouped.get(fam)
        if not entries:
            continue
        lines.append(f"\n## {fam}（{len(entries)}）\n")
        lines.append("| 型号 | 可用渠道（完整 id = 渠道/型号） |")
        lines.append("|---|---|")
        for name, chans in sorted(entries):
            lines.append(f"| `{name}` | {', '.join('`'+c+'`' for c in chans)} |")

    DOCS.mkdir(parents=True, exist_ok=True)
    out = DOCS / "model_catalog.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"WROTE {out}  ({len(catalog)} unique models, {len(models)} raw)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
