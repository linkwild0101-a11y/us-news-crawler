#!/usr/bin/env python3
"""Stock V3 每日评分卡汇总脚本。"""

from __future__ import annotations

import argparse
import csv
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from supabase import create_client

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

SCORECARD_KEYS = [
    "eval_hit_rate_proxy",
    "eval_avg_return_proxy",
    "paper_realized_pnl",
    "paper_unrealized_pnl",
    "paper_win_rate",
    "cc_challenger_win_rate",
    "cc_promote_candidate_count",
    "drift_critical_count",
    "drift_warn_count",
    "lifecycle_active_count",
    "lifecycle_generated_count",
    "subscription_sent_total",
    "subscription_failed_total",
]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _init_supabase():
    # 本地存在 SOCKS 代理配置时会导致 supabase/httpx 初始化失败，这里显式清理。
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        os.environ.pop(key, None)
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("缺少 SUPABASE_URL / SUPABASE_KEY")
    return create_client(url, key)


def _load_metrics(supabase, days: int) -> Dict[str, Dict[str, Any]]:
    cutoff = (_now_utc() - timedelta(days=days)).isoformat()
    rows = (
        supabase.table("research_run_metrics")
        .select("run_id,metric_name,metric_value,created_at")
        .gte("created_at", cutoff)
        .order("created_at", desc=True)
        .limit(5000)
        .execute()
        .data
        or []
    )
    latest: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        metric_name = str(row.get("metric_name") or "")
        if not metric_name:
            continue
        if metric_name in latest:
            continue
        latest[metric_name] = row
    return latest


def _build_scorecard_rows(metrics: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for key in SCORECARD_KEYS:
        source = metrics.get(key) or {}
        rows.append(
            {
                "metric_name": key,
                "metric_value": source.get("metric_value"),
                "run_id": source.get("run_id"),
                "created_at": source.get("created_at"),
            }
        )
    return rows


def _write_markdown(report_date: str, rows: List[Dict[str, Any]], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"stock_v3_daily_scorecard_{report_date}.md"
    lines = [
        "# Stock V3 Daily Scorecard",
        "",
        f"- 日期(UTC): {report_date}",
        "",
        "| Metric | Value | Run ID | Time |",
        "|---|---:|---|---|",
    ]
    for row in rows:
        value = row.get("metric_value")
        run_id = row.get("run_id")
        created_at = row.get("created_at")
        lines.append(
            f"| {row['metric_name']} | {'-' if value is None else value} | "
            f"{'-' if run_id is None else run_id} | {'-' if created_at is None else created_at} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_csv(report_date: str, rows: List[Dict[str, Any]], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"stock_v3_daily_scorecard_{report_date}.csv"
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=["metric_name", "metric_value", "run_id", "created_at"])
        writer.writeheader()
        writer.writerows(rows)
    return path


def build_daily_scorecard(days: int, md_dir: str, csv_dir: str) -> Dict[str, Any]:
    supabase = _init_supabase()
    report_date = _now_utc().date().isoformat()
    metrics = _load_metrics(supabase=supabase, days=days)
    rows = _build_scorecard_rows(metrics=metrics)
    md_path = _write_markdown(
        report_date=report_date,
        rows=rows,
        output_dir=Path(md_dir),
    )
    csv_path = _write_csv(
        report_date=report_date,
        rows=rows,
        output_dir=Path(csv_dir),
    )
    summary = {
        "report_date": report_date,
        "metrics_filled": sum(1 for row in rows if row.get("metric_value") is not None),
        "metrics_total": len(rows),
        "markdown": str(md_path),
        "csv": str(csv_path),
    }
    logger.info("[DAILY_SCORECARD_V3_DONE] " + ", ".join([f"{k}={v}" for k, v in summary.items()]))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock V3 daily scorecard builder")
    parser.add_argument("--days", type=int, default=1, help="回看天数")
    parser.add_argument("--md-dir", type=str, default="docs/reports", help="Markdown 输出目录")
    parser.add_argument("--csv-dir", type=str, default="data/reports", help="CSV 输出目录")
    args = parser.parse_args()
    build_daily_scorecard(
        days=max(1, args.days),
        md_dir=args.md_dir.strip() or "docs/reports",
        csv_dir=args.csv_dir.strip() or "data/reports",
    )


if __name__ == "__main__":
    main()
