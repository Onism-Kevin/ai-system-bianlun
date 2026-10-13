"""S0-6 spike runner 骨架：20 议题 × 4 stage 真实调用 MODEL_DEFAULT，落 CSV。

设计要点（用户 S0-6a 明确要求）：
- **断点续跑**（最重要）：每次调用后立即追加写 CSV，绝不攒到最后。
  `--resume` 跳过 CSV 中已存在 (topic_id, stage) 组合，从断点继续。
- **150s 超时熔断**：analyze p95≈79s，150s ≈ 2 倍 p95 余量，避免误杀。
  超时记为失败行（error_mode=timeout）并继续，不中断整个 spike。
- stage 用 S0-5 的 prompt + schema，通过 S0-4 的 generate_structured 驱动，
  记录首过合规（first_pass）与重试次数（retries）。

CSV 列：topic_id, topic, category, difficulty, stage, ok, first_pass, retries,
        ttfb, total, error_mode

S0-6a 只交付骨架 + 单测（不真跑模型）；S0-6b 议题确认后执行真跑。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import threading
import time
from pathlib import Path

# 本机网关直连：屏蔽代理（同 model_bench）
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"

ROOT = Path(__file__).resolve().parent.parent.parent  # backend/
sys.path.insert(0, str(ROOT))

from app.core.exceptions import (                       # noqa: E402
    ModelGatewayError,
    StructuredValidationError,
)
from app.core.model_provider import OpenAICompatProvider  # noqa: E402
from app.core.structured import generate_structured     # noqa: E402
from app.prompts import analyze as analyze_prompt        # noqa: E402
from app.prompts import coach as coach_prompt            # noqa: E402
from app.prompts import explore as explore_prompt        # noqa: E402
from app.prompts import report as report_prompt          # noqa: E402
from app.schemas.stage_outputs import (                  # noqa: E402
    ArgumentMap,
    CoachTurn,
    DecomposeOut,
    ReviewReport,
)
from scripts.fetch_models import load_env                # noqa: E402

SPIKE_DIR = Path(__file__).resolve().parent
TOPICS_FILE = SPIKE_DIR / "topics.json"
RESULTS_CSV = SPIKE_DIR / "spike_results.csv"

STAGES = ("decompose", "analyze", "coach", "report")
TIMEOUT_S = 150.0

CSV_COLUMNS = [
    "topic_id", "topic", "category", "difficulty", "stage",
    "ok", "first_pass", "retries", "ttfb", "total", "error_mode",
]


def build_stage_messages(stage: str, topic: str) -> list[dict]:
    """按 stage 构造 prompt 消息。coach/report 需要额外上下文，spike 里用占位。

    E-11（2026-10-13）：analyze/coach 入参改为带 seq 的训练消息列表
    （{seq, role, agent_role?, content}，对齐 messages 表出参），spike 用
    假消息构造。重跑请指定新 --csv，勿覆盖 spike_results.csv（历史归档，
    与本 prompt 版本不可比）。
    """
    fake_messages = [
        {"seq": 1, "role": "user", "content": f"我支持议题「{topic}」。"},
        {"seq": 2, "role": "assistant", "agent_role": "coach",
         "content": "你给出这个结论的依据是什么？"},
    ]
    if stage == "decompose":
        return explore_prompt.build_messages(topic)
    if stage == "analyze":
        return analyze_prompt.build_messages(fake_messages)
    if stage == "coach":
        return coach_prompt.build_messages(fake_messages)
    if stage == "report":
        return report_prompt.build_messages(topic, f"支持议题「{topic}」", "（spike 占位记录）")
    raise ValueError(f"未知 stage: {stage}")


STAGE_SCHEMAS = {
    "decompose": DecomposeOut,
    "analyze": ArgumentMap,
    "coach": CoachTurn,
    "report": ReviewReport,
}


def load_completed(csv_path: Path) -> set[tuple[int, str]]:
    """读取 CSV 中已完成的 (topic_id, stage)，供 --resume 跳过。"""
    done: set[tuple[int, str]] = set()
    if not csv_path.exists():
        return done
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                done.add((int(row["topic_id"]), row["stage"]))
            except (KeyError, ValueError):
                continue
    return done


def append_row(csv_path: Path, row: dict, lock: threading.Lock) -> None:
    """立即追加一行到 CSV。带锁防并发写坏文件（S0-6b 可能并发跑议题）。"""
    new_file = not csv_path.exists()
    with lock:
        with csv_path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            if new_file:
                writer.writeheader()
            writer.writerow(row)
            f.flush()
            os.fsync(f.fileno())  # 立即落盘：崩了也不丢已完成的行


def run_one(provider: OpenAICompatProvider, model: str, stage: str,
            messages: list[dict], schema, timeout: float) -> dict:
    """跑单个 (topic, stage) 一次，返回结果行所需字段。"""
    start = time.perf_counter()
    first_pass: bool | None = None
    retries: int | None = None
    try:
        obj, attempts = generate_structured(
            messages, schema,
            lambda msgs: _collect_stream(provider, model, msgs, timeout, start),
            max_retries=2,
        )
        total = time.perf_counter() - start
        return {"ok": True, "first_pass": attempts == 1, "retries": attempts - 1,
                "ttfb": _last_ttfb(), "total": round(total, 2), "error_mode": ""}
    except StructuredValidationError as exc:
        return {"ok": False, "first_pass": False, "retries": 2,
                "ttfb": _last_ttfb(), "total": round(time.perf_counter() - start, 2),
                "error_mode": "validation"}
    except ModelGatewayError as exc:
        mode = "timeout" if "Timeout" in type(exc).__name__ else "gateway"
        return {"ok": False, "first_pass": False, "retries": 0,
                "ttfb": _last_ttfb(), "total": round(time.perf_counter() - start, 2),
                "error_mode": mode}


_TTFB = {"v": None}


def _last_ttfb() -> float | None:
    return _TTFB["v"]


def _collect_stream(provider, model, messages, timeout, _start) -> str:
    """供 generate_structured 的 generate 回调：流式收集并记录首字节。"""
    _TTFB["v"] = None
    t0 = time.perf_counter()
    parts: list[str] = []
    for chunk in provider.generate_stream(model=model, messages=messages, timeout=timeout):
        if _TTFB["v"] is None:
            _TTFB["v"] = round(time.perf_counter() - t0, 2)
        parts.append(chunk)
    return "".join(parts)


def load_provider() -> tuple[OpenAICompatProvider, str]:
    env = load_env()
    base_url = env.get("MODEL_BASE_URL", "").rstrip("/")
    api_key = env.get("MODEL_API_KEY", "")
    model = env.get("MODEL_DEFAULT", "").strip()
    if not base_url or not api_key or not model:
        raise SystemExit("FATAL: MODEL_BASE_URL / MODEL_API_KEY / MODEL_DEFAULT 未配置")
    return OpenAICompatProvider(base_url=base_url, api_key=api_key), model


def main() -> int:
    ap = argparse.ArgumentParser(description="Spike runner（S0-6）")
    ap.add_argument("--topic-limit", type=int, default=0, help="只跑前 N 个议题（0=全部）")
    ap.add_argument("--resume", action="store_true", help="跳过 CSV 中已完成的 (topic_id, stage)")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不调用模型")
    ap.add_argument("--csv", type=Path, default=RESULTS_CSV)
    args = ap.parse_args()

    topics = json.loads(TOPICS_FILE.read_text(encoding="utf-8"))
    if args.topic_limit > 0:
        topics = topics[: args.topic_limit]

    done = load_completed(args.csv) if args.resume else set()
    lock = threading.Lock()

    if args.dry_run:
        plan = [(t["id"], s) for t in topics for s in STAGES if (t["id"], s) not in done]
        print(f"dry-run: {len(plan)} 个待跑组合（已跳过 {len(done)} 个），不调用模型")
        return 0

    provider, model = load_provider()
    total_runs = 0
    for t in topics:
        for stage in STAGES:
            if (t["id"], stage) in done:
                continue
            r = run_one(provider, model, stage, build_stage_messages(stage, t["topic"]),
                        STAGE_SCHEMAS[stage], TIMEOUT_S)
            row = {"topic_id": t["id"], "topic": t["topic"], "category": t["category"],
                   "difficulty": t["difficulty"], "stage": stage, **r}
            append_row(args.csv, row, lock)  # 立即落盘
            total_runs += 1
            print(json.dumps({k: row[k] for k in
                              ("topic_id", "stage", "ok", "first_pass", "retries",
                               "ttfb", "total", "error_mode")},
                             ensure_ascii=False), flush=True)
    print(f"SPIKE RUN DONE: {total_runs} 个组合 -> {args.csv}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
