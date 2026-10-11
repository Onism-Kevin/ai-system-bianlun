"""S0-3b 限速/延迟稳定性补测：对 MODEL_DEFAULT 跑 10×decompose + 10×analyze。

目的：确认 spike（20 议题 × 4 任务）期间主力模型是否撞 429 或延迟翻倍。
记录每次：延迟（首字节 + 总）、成功/失败、失败错误类型、序号。
产出：docs/model_bench.md 追加「限速与延迟稳定性」一节。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

for _k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fetch_models import load_env                                       # noqa: E402
from app.core.exceptions import ModelGatewayError                       # noqa: E402
from app.core.model_provider import OpenAICompatProvider                # noqa: E402
from model_bench import (DECOMPOSE_MESSAGES, ANALYZE_MESSAGES,          # noqa: E402
                         DecomposeOut, AnalyzeOut)

DOCS = Path(__file__).resolve().parent.parent.parent / "docs"
MODEL = "cline/deepseek/deepseek-v4-pro"
ROUNDS = 10


def run_once(provider, model, messages, schema, timeout=180.0):
    start = time.perf_counter()
    ttfb = None
    parts = []
    try:
        for chunk in provider.generate_stream(model=model, messages=messages, timeout=timeout):
            if ttfb is None:
                ttfb = time.perf_counter() - start
            parts.append(chunk)
        text = "".join(parts)
        ok = False
        err = None
        try:
            schema.model_validate_json(text)
            ok = True
        except Exception as exc:
            err = f"VALIDATE: {type(exc).__name__}: {str(exc)[:80]}"
        return {"ok": ok, "ttfb": ttfb, "total": time.perf_counter() - start, "err": err}
    except ModelGatewayError as exc:
        return {"ok": False, "ttfb": ttfb, "total": time.perf_counter() - start,
                "err": f"{type(exc).__name__}: {str(exc)[:80]}"}
    except Exception as exc:
        return {"ok": False, "ttfb": ttfb, "total": time.perf_counter() - start,
                "err": f"UNEXPECTED {type(exc).__name__}: {str(exc)[:80]}"}


def main() -> int:
    env = load_env()
    provider = OpenAICompatProvider(
        base_url=env.get("MODEL_BASE_URL", "").rstrip("/"),
        api_key=env.get("MODEL_API_KEY", ""),
    )
    DOCS.mkdir(parents=True, exist_ok=True)
    results = {"decompose": [], "analyze": []}

    for task, messages, schema in [("decompose", DECOMPOSE_MESSAGES, DecomposeOut),
                                   ("analyze", ANALYZE_MESSAGES, AnalyzeOut)]:
        for i in range(1, ROUNDS + 1):
            r = run_once(provider, MODEL, messages, schema)
            r["round"] = i
            results[task].append(r)
            line = {"task": task, "round": i, "ok": r["ok"],
                    "ttfb": round(r["ttfb"], 2) if r["ttfb"] else None,
                    "total": round(r["total"], 2),
                    "err": (r["err"] or "")[:60]}
            print(json.dumps(line, ensure_ascii=False), flush=True)

    (DOCS / "model_bench_stability.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"STABILITY DONE -> {DOCS / 'model_bench_stability.json'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
