"""S0-6 断点续跑逻辑单测（不触网、不调模型）。

验证：
- append_row 立即写入且新建时带 header
- load_completed 正确解析已完成组合
- run_one 的 150s 熔断路径（用假 provider 触发超时异常）
"""
from __future__ import annotations

import csv
import threading
from pathlib import Path

from app.core.exceptions import ModelTimeoutError
from tests.spike.run_spike import (
    CSV_COLUMNS,
    append_row,
    load_completed,
)


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(r)


class TestResume:
    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert load_completed(tmp_path / "nope.csv") == set()

    def test_parses_existing_combinations(self, tmp_path: Path):
        p = tmp_path / "r.csv"
        _write_csv(p, [
            {"topic_id": 1, "topic": "a", "category": "c", "difficulty": "d",
             "stage": "decompose", "ok": True, "first_pass": True, "retries": 0,
             "ttfb": 1.0, "total": 2.0, "error_mode": ""},
            {"topic_id": 2, "topic": "b", "category": "c", "difficulty": "d",
             "stage": "analyze", "ok": False, "first_pass": False, "retries": 2,
             "ttfb": 1.0, "total": 2.0, "error_mode": "timeout"},
        ])
        done = load_completed(p)
        assert done == {(1, "decompose"), (2, "analyze")}

    def test_resume_skips_only_completed(self, tmp_path: Path):
        p = tmp_path / "r.csv"
        _write_csv(p, [
            {"topic_id": 1, "topic": "a", "category": "c", "difficulty": "d",
             "stage": "decompose", "ok": True, "first_pass": True, "retries": 0,
             "ttfb": 1.0, "total": 2.0, "error_mode": ""},
        ])
        done = load_completed(p)
        # 议题1只完成了 decompose，其余 3 个 stage 仍应跑
        pending = [s for s in ("decompose", "analyze", "coach", "report")
                   if (1, s) not in done]
        assert pending == ["analyze", "coach", "report"]


class TestAppendRow:
    def test_immediate_write_with_header(self, tmp_path: Path):
        p = tmp_path / "out.csv"
        lock = threading.Lock()
        append_row(p, {"topic_id": 1, "topic": "t", "category": "c",
                       "difficulty": "d", "stage": "decompose", "ok": True,
                       "first_pass": True, "retries": 0, "ttfb": 1.0,
                       "total": 2.0, "error_mode": ""}, lock)
        assert p.exists()
        with p.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        assert rows[0]["stage"] == "decompose"

    def test_appends_without_duplicating_header(self, tmp_path: Path):
        p = tmp_path / "out.csv"
        lock = threading.Lock()
        row = {"topic_id": 1, "topic": "t", "category": "c", "difficulty": "d",
               "stage": "decompose", "ok": True, "first_pass": True, "retries": 0,
               "ttfb": 1.0, "total": 2.0, "error_mode": ""}
        append_row(p, dict(row), lock)
        row2 = dict(row, topic_id=2, stage="analyze")
        append_row(p, row2, lock)
        with p.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2
        assert rows[0]["topic_id"] == "1" and rows[1]["topic_id"] == "2"


class TestCircuitBreakerPath:
    def test_timeout_maps_to_error_mode(self, tmp_path: Path):
        """假 provider 一律超时 → error_mode=timeout，不中断。"""
        from tests.spike import run_spike as rs

        class TimeoutProvider:
            def generate_stream(self, **kwargs):
                raise ModelTimeoutError("模拟读超时")

        provider, model = TimeoutProvider(), "fake/model"
        before = len(rs.load_completed.__doc__ or "")
        r = rs.run_one(provider, model, "decompose", [{"role": "user", "content": "x"}],
                       rs.STAGE_SCHEMAS["decompose"], rs.TIMEOUT_S)
        assert r["ok"] is False
        assert r["error_mode"] == "timeout"
        assert before > 0
