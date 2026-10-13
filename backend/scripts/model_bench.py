"""S0-3b mini-bench：对 5 个候选模型跑连通性 + 3 任务基准。

任务（各 1 次）：
  probe       连通性探针（短回复；失败重试 3 次，含候选自带 fallback id）
  decompose   议题拆解 structured（四字段 JSON，Pydantic 首过校验）
  analyze     论证分析 structured（nodes/edges JSON，Pydantic 首过校验）
  probe_text  300 字追问生成（自由文本）

记录：连通性/错误类型、首字节延迟(ttfb)、总延迟、strict/lenient 合规率、
样本摘录。全量输出写 docs/model_bench_outputs.jsonl，紧凑摘要打印 stdout。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# 本机网关直连：屏蔽代理环境变量，防止 httpx 把 localhost 请求送进代理
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"

sys.path.insert(0, str(Path(__file__).resolve().parent))            # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))     # backend/
from fetch_models import load_env                                    # noqa: E402
from app.core.exceptions import ModelGatewayError                    # noqa: E402
from app.core.model_provider import OpenAICompatProvider             # noqa: E402
from pydantic import BaseModel, ValidationError                      # noqa: E402

DOCS = Path(__file__).resolve().parent.parent.parent / "docs"
OUT_JSONL = DOCS / "model_bench_outputs.jsonl"

CANDIDATES = [
    {"label": "mimo-free",        "id": "our-free-model/mimo-v2.6-flash-free", "fallback": None},
    {"label": "deepseek-v4-pro",  "id": "cline/deepseek/deepseek-v4-pro",      "fallback": None},
    {"label": "glm-5.3",          "id": "cline/z-ai/glm-5.3",                  "fallback": "lobsterai/glm-5.3"},
    {"label": "qwen3.8-max",      "id": "trae/qwen3.8-max",                    "fallback": "lobsterai/qwen3.8-max"},
    {"label": "claude-haiku-5.5", "id": "cline/anthropic/claude-haiku-5.5",    "fallback": None},
]

# ---------- structured 契约（S0-4 正式 schema 落地前的 bench 版） ----------
# 历史 bench 快照（S0-3b mini-bench），自带 schema 与
# prompt，勿随 app/stage_outputs.py 更新——改了会让
# docs/model_bench_outputs.jsonl 失去可比性。

class DecomposeOut(BaseModel):
    topic: str
    core_dispute: str
    pro_position: str
    con_position: str


class Node(BaseModel):
    id: str
    type: str
    text: str


class Edge(BaseModel):
    source: str
    target: str
    type: str


class AnalyzeOut(BaseModel):
    nodes: list[Node]
    edges: list[Edge]


DECOMPOSE_MESSAGES = [
    {"role": "system", "content": "你是严谨的辩论议题拆解助手，只输出 JSON。"},
    {"role": "user", "content": (
        "请把议题「人工智能进入中小学课堂的利弊」拆解为 JSON，字段："
        "topic(议题名)、core_dispute(核心争议，一句话)、pro_position(正方核心立场)、"
        "con_position(反方核心立场)。只输出 JSON，不要解释，不要 markdown 代码块。"
    )},
]

ANALYZE_MESSAGES = [
    {"role": "system", "content": "你是论证分析助手，只输出 JSON。"},
    {"role": "user", "content": (
        "阅读论证：「手机进校园会分散注意力并影响视力；但它也能查资料、紧急联系。"
        "禁令一刀切，剥夺了自律学生的学习工具。」\n"
        "输出 JSON：nodes 数组（id/type∈claim|evidence|rebuttal/text），"
        "edges 数组（source/target/type∈support|attack）。只输出 JSON，不要解释。"
    )},
]

PROBE_TEXT_MESSAGES = [
    {"role": "user", "content": (
        "学生观点：「AI 写作工具能提升写作效率，应该允许课堂使用」。\n"
        "请生成一段约 300 字的教师追问，引导学生思考 AI 依赖对独立思考能力的影响。直接输出文本。"
    )},
]

CONNECT_MESSAGES = [{"role": "user", "content": "请只回复两个字：就绪"}]


def strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()


def run_stream(provider: OpenAICompatProvider, model: str, messages: list,
               timeout: float) -> dict:
    """真实流式调用一次，返回 {ok,text,ttfb,total,err}。"""
    start = time.perf_counter()
    ttfb = None
    parts: list[str] = []
    try:
        for chunk in provider.generate_stream(
            model=model, messages=messages, timeout=timeout
        ):
            if ttfb is None:
                ttfb = time.perf_counter() - start
            parts.append(chunk)
        return {"ok": True, "text": "".join(parts), "ttfb": ttfb,
                "total": time.perf_counter() - start, "err": None}
    except ModelGatewayError as exc:
        return {"ok": False, "text": "".join(parts), "ttfb": ttfb,
                "total": time.perf_counter() - start, "err": f"{type(exc).__name__}: {exc}"}
    except Exception as exc:  # bench 兜底：任何意外也记录
        return {"ok": False, "text": "".join(parts), "ttfb": ttfb,
                "total": time.perf_counter() - start, "err": f"UNEXPECTED {type(exc).__name__}: {exc}"}


def bench_one(cand: dict, provider: OpenAICompatProvider) -> list[dict]:
    label, model_id, fallback = cand["label"], cand["id"], cand["fallback"]
    records: list[dict] = []

    # ---- 连通性探针：主 id 最多 3 次，全失败且有 fallback 时改用 fallback 再 3 次
    used_id = model_id
    probe = None
    attempts_log = []
    for mid in [model_id] + ([fallback] if fallback else []):
        for i in range(3):
            probe = run_stream(provider, mid, CONNECT_MESSAGES, timeout=60.0)
            attempts_log.append({"id": mid, "try": i + 1, "ok": probe["ok"], "err": probe["err"]})
            if probe["ok"]:
                used_id = mid
                break
        if probe and probe["ok"]:
            break
    records.append({
        "label": label, "task": "probe", "model_id": used_id, "fallback_used": used_id != model_id,
        "ok": bool(probe and probe["ok"]), "err": probe["err"] if probe else "no-attempt",
        "ttfb": probe["ttfb"] if probe else None, "total": probe["total"] if probe else None,
        "attempts": attempts_log, "sample": (probe["text"][:60] if probe else ""),
    })
    if not (probe and probe["ok"]):
        return records  # 连不通 → 跳过后续任务

    # ---- 三个任务各 1 次
    task_specs = [
        ("decompose", DECOMPOSE_MESSAGES, DecomposeOut, 180.0),
        ("analyze",   ANALYZE_MESSAGES,   AnalyzeOut,   180.0),
        ("probe_text", PROBE_TEXT_MESSAGES, None,       180.0),
    ]
    for name, messages, schema, timeout in task_specs:
        r = run_stream(provider, used_id, messages, timeout)
        rec = {
            "label": label, "task": name, "model_id": used_id,
            "ok": r["ok"], "err": r["err"], "ttfb": r["ttfb"], "total": r["total"],
            "strict_ok": None, "lenient_ok": None,
            "sample": r["text"][:200].replace("\n", " "),
        }
        if schema is not None and r["ok"]:
            try:
                schema.model_validate_json(r["text"])
                rec["strict_ok"] = True
            except ValidationError:
                rec["strict_ok"] = False
            try:
                schema.model_validate_json(strip_fences(r["text"]))
                rec["lenient_ok"] = True
            except ValidationError as exc:
                rec["lenient_ok"] = False
                rec["lenient_err"] = str(exc)[:200]
        records.append(rec)
        with OUT_JSONL.open("a", encoding="utf-8") as f:  # 全量落盘，便于事后复查
            f.write(json.dumps({**rec, "full_text": r["text"]}, ensure_ascii=False) + "\n")
    return records


def main() -> int:
    env = load_env()
    base_url = env.get("MODEL_BASE_URL", "").rstrip("/")
    api_key = env.get("MODEL_API_KEY", "")
    if not base_url or not api_key:
        print("FATAL: MODEL_BASE_URL / MODEL_API_KEY 未配置", file=sys.stderr)
        return 2
    provider = OpenAICompatProvider(base_url=base_url, api_key=api_key)

    DOCS.mkdir(parents=True, exist_ok=True)
    OUT_JSONL.write_text("", encoding="utf-8")  # 重跑清空

    all_records: list[dict] = []
    for cand in CANDIDATES:
        recs = bench_one(cand, provider)
        all_records.extend(recs)
        for r in recs:
            line = {
                "label": r["label"], "task": r["task"], "model": r["model_id"],
                "ok": r["ok"], "err": (r["err"] or "")[:120],
                "ttfb": round(r["ttfb"], 2) if r.get("ttfb") else None,
                "total": round(r["total"], 2) if r.get("total") else None,
                "strict": r.get("strict_ok"), "lenient": r.get("lenient_ok"),
                "sample": r.get("sample", "")[:80],
            }
            print(json.dumps(line, ensure_ascii=False), flush=True)
    print(f"BENCH DONE -> {OUT_JSONL}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
