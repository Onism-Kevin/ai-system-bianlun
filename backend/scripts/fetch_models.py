"""S0-3b 临时脚本：从 backend/.env 读配置，调网关 GET /v1/models 拉全量模型列表。

只输出模型 id 与所属渠道（从 id 前缀推断），绝不打印 API key。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parent.parent
ENV_PATH = BACKEND / ".env"


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if not ENV_PATH.exists():
        return env
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def main() -> int:
    env = load_env()
    base_url = env.get("MODEL_BASE_URL", "").rstrip("/")
    api_key = env.get("MODEL_API_KEY", "")
    if not base_url or not api_key:
        print("FATAL: MODEL_BASE_URL 或 MODEL_API_KEY 未在 backend/.env 配置", file=sys.stderr)
        return 2
    url = f"{base_url}/models"
    try:
        resp = httpx.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
            trust_env=False,  # 直连本机网关，不走代理
        )
    except httpx.HTTPError as exc:
        print(f"FATAL: 请求失败 {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    print(f"HTTP {resp.status_code}", file=sys.stderr)
    if resp.status_code >= 400:
        # 401/其他错误：输出原始响应体供卡住协议汇报，不含 key
        print(f"RAW BODY: {resp.text[:2000]}", file=sys.stderr)
        return 4
    try:
        data = resp.json()
    except json.JSONDecodeError:
        print(f"FATAL: 响应不是 JSON: {resp.text[:500]}", file=sys.stderr)
        return 5
    models = [m.get("id", "") for m in data.get("data", []) if isinstance(m, dict)]
    models = sorted(x for x in models if x)
    print(json.dumps({"count": len(models), "models": models}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
