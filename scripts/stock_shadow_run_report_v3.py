#!/usr/bin/env python3
"""Stock V3 7日 shadow run 报告生成脚本。"""

from __future__ import annotations

import argparse
import logging
import os
from collections import defaultdict
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

WATCH_METRICS = [
    "eval_hit_rate_proxy",
    "paper_realized_pnl",
    "cc_challenger_win_rate",
    "drift_critical_count",
    "lifecycle_active_count",
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


def _load_runs(supabase, days: int) -> List[Dict[str, Any]]:
    cutoff = (_now_utc() - timedelta(days=days)).isoformat()
    rows = (
        supabase.table("research_runs")
        .select("run_id,pipeline_name,status,started_at,ended_at,duration_sec")
        .gte("started_at", cutoff)
        .order("started_at", desc=True)
        .limit(5000)
        .execute()
        .data
        or []
    )
    return rows


def _load_metric_rows(supabase, days: int) -> List[Dict[str, Any]]:
    cutoff = (_now_utc() - timedelta(days=days)).isoformat()
    rows = (
        supabase.table("research_run_metrics")
        .select("run_id,metric_name,metric_value,created_at")
        .gte("created_at", cutoff)
        .order("created_at", desc=True)
        .limit(8000)
        .execute()
        .data
        or []
    )
    return rows


def _build_pipeline_summary(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "runs": 0,
            "success": 0,
            "failed": 0,
            "degraded": 0,
            "duration_sum": 0.0,
        }
    )
    for row in rows:
        pipeline = str(row.get("pipeline_name") or "unknown")
        status = str(row.get("status") or "")
        duration = float(row.get("duration_sec") or 0.0)
        payload = grouped[pipeline]
        payload["runs"] += 1
        payload["duration_sum"] += duration
        if status == "success":
            payload["success"] += 1
        elif status == "failed":
            payload["failed"] += 1
        elif status == "degraded":
            payload["degraded"] += 1

    for pipeline, payload in grouped.items():
        runs = payload["runs"] or 1
        payload["success_rate"] = round(payload["success"] / runs, 4)
        payload["avg_duration_sec"] = round(payload["duration_sum"] / runs, 2)
        grouped[pipeline] = payload
    return grouped


def _build_metric_summary(metric_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[float]] = defaultdict(list)
    latest: Dict[str, Dict[str, Any]] = {}
    for row in metric_rows:
        metric = str(row.get("metric_name") or "")
        if metric in WATCH_METRICS:
            grouped[metric].append(float(row.get("metric_value") or 0.0))
            if metric not in latest:
                latest[metric] = row

    summary: Dict[str, Dict[str, Any]] = {}
    for metric in WATCH_METRICS:
        values = grouped.get(metric, [])
        latest_row = latest.get(metric, {})
        summary[metric] = {
            "latest_value": latest_row.get("metric_value"),
            "latest_run_id": latest_row.get("run_id"),
            "latest_time": latest_row.get("created_at"),
            "avg_value": round(sum(values) / len(values), 6) if values else None,
            "samples": len(values),
        }
    return summary


def _write_report(
    days: int,
    pipeline_summary: Dict[str, Dict[str, Any]],
    metric_summary: Dict[str, Dict[str, Any]],
    output_path: Path,
) -> None:
    def as_text(value: Any) -> str:
        if value is None:
            return "-"
        return str(value)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Stock V3 Shadow Run Report",
        "",
        f"- 统计窗口: 最近 {days} 天",
        f"- 生成时间(UTC): {_now_utc().isoformat()}",
        "",
        "## Pipeline 稳定性",
        "",
        "| Pipeline | Runs | Success | Failed | Degraded | Success Rate | Avg Duration(s) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for pipeline, data in sorted(pipeline_summary.items(), key=lambda item: item[0]):
        lines.append(
            f"| {pipeline} | {data['runs']} | {data['success']} | {data['failed']} | "
            f"{data['degraded']} | {data['success_rate']} | {data['avg_duration_sec']} |"
        )

    lines.extend(
        [
            "",
            "## 核心指标快照",
            "",
            "| Metric | Latest | Avg | Samples | Latest Run | Latest Time |",
            "|---|---:|---:|---:|---|---|",
        ]
    )
    for metric in WATCH_METRICS:
        data = metric_summary.get(metric, {})
        lines.append(
            f"| {metric} | {as_text(data.get('latest_value'))} | {as_text(data.get('avg_value'))} | "
            f"{as_text(data.get('samples'))} | {as_text(data.get('latest_run_id'))} | "
            f"{as_text(data.get('latest_time'))} |"
        )
    lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def build_shadow_report(days: int, output: str) -> Dict[str, Any]:
    supabase = _init_supabase()
    runs = _load_runs(supabase=supabase, days=days)
    metrics = _load_metric_rows(supabase=supabase, days=days)
    pipeline_summary = _build_pipeline_summary(rows=runs)
    metric_summary = _build_metric_summary(metric_rows=metrics)
    output_path = Path(output)
    _write_report(
        days=days,
        pipeline_summary=pipeline_summary,
        metric_summary=metric_summary,
        output_path=output_path,
    )
    summary = {
        "days": days,
        "runs": len(runs),
        "metric_rows": len(metrics),
        "pipelines": len(pipeline_summary),
        "output": str(output_path),
    }
    logger.info("[SHADOW_REPORT_V3_DONE] " + ", ".join([f"{k}={v}" for k, v in summary.items()]))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock V3 shadow run report builder")
    parser.add_argument("--days", type=int, default=7, help="统计窗口天数")
    parser.add_argument(
        "--output",
        type=str,
        default="docs/reports/stock_v3_shadow_run_7d.md",
        help="输出 markdown 路径",
    )
    args = parser.parse_args()
    build_shadow_report(
        days=max(1, args.days),
        output=args.output.strip() or "docs/reports/stock_v3_shadow_run_7d.md",
    )


if __name__ == "__main__":
    main()
