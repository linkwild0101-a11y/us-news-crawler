#!/usr/bin/env python3
"""StockOps P0: 噪音反馈周报生成脚本。"""

from __future__ import annotations

import argparse
import csv
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

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


def _date_range(days: int) -> List[date]:
    today = _now_utc().date()
    return [today - timedelta(days=idx) for idx in range(days - 1, -1, -1)]


def _load_feedback_rows(supabase, days: int, limit: int) -> List[Dict[str, Any]]:
    cutoff = (_now_utc() - timedelta(days=max(1, days))).isoformat()
    return (
        supabase.table("stock_alert_feedback_v1")
        .select("alert_id,label,created_at")
        .gte("created_at", cutoff)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )


def _load_event_map(supabase, alert_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    if not alert_ids:
        return {}
    rows = (
        supabase.table("stock_alert_events_v1")
        .select("id,ticker,signal_type")
        .in_("id", alert_ids[:2000])
        .limit(2000)
        .execute()
        .data
        or []
    )
    result: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        alert_id = int(row.get("id") or 0)
        if alert_id <= 0:
            continue
        result[alert_id] = row
    return result


def _bucket_daily(
    rows: List[Dict[str, Any]],
    days: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    daily: Dict[str, Dict[str, Any]] = {
        item.isoformat(): {"date": item.isoformat(), "total": 0, "noise": 0, "useful": 0}
        for item in _date_range(days)
    }
    totals = {"total": 0, "noise": 0, "useful": 0}

    for row in rows:
        label = str(row.get("label") or "").strip().lower()
        created_at = str(row.get("created_at") or "")
        if label not in ("noise", "useful"):
            continue
        day = created_at[:10]
        if day not in daily:
            continue
        daily_item = daily[day]
        daily_item["total"] += 1
        totals["total"] += 1
        if label == "noise":
            daily_item["noise"] += 1
            totals["noise"] += 1
        else:
            daily_item["useful"] += 1
            totals["useful"] += 1

    rows_out: List[Dict[str, Any]] = []
    for key in sorted(daily.keys()):
        item = daily[key]
        total = int(item["total"])
        noise = int(item["noise"])
        useful = int(item["useful"])
        rows_out.append(
            {
                "date": key,
                "total": total,
                "noise": noise,
                "useful": useful,
                "noise_ratio": (noise / total) if total > 0 else 0.0,
                "useful_ratio": (useful / total) if total > 0 else 0.0,
            }
        )

    summary = {
        "feedback_total": totals["total"],
        "feedback_noise": totals["noise"],
        "feedback_useful": totals["useful"],
        "noise_ratio_7d": (totals["noise"] / totals["total"]) if totals["total"] > 0 else 0.0,
        "useful_ratio_7d": (totals["useful"] / totals["total"]) if totals["total"] > 0 else 0.0,
    }
    return rows_out, summary


def _bucket_noisy_tickers(
    rows: List[Dict[str, Any]],
    event_map: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    bucket: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        alert_id = int(row.get("alert_id") or 0)
        label = str(row.get("label") or "").strip().lower()
        if alert_id <= 0 or label not in ("noise", "useful"):
            continue
        event = event_map.get(alert_id) or {}
        ticker = str(event.get("ticker") or "UNKNOWN").upper()
        signal_type = str(event.get("signal_type") or "opportunity").lower()
        key = f"{ticker}|{signal_type}"
        if key not in bucket:
            bucket[key] = {
                "ticker": ticker,
                "signal_type": signal_type,
                "total": 0,
                "noise": 0,
                "useful": 0,
            }
        item = bucket[key]
        item["total"] += 1
        if label == "noise":
            item["noise"] += 1
        else:
            item["useful"] += 1

    out: List[Dict[str, Any]] = []
    for item in bucket.values():
        total = int(item["total"])
        if total <= 0:
            continue
        noise = int(item["noise"])
        useful = int(item["useful"])
        out.append(
            {
                **item,
                "noise_ratio": (noise / total) if total > 0 else 0.0,
                "useful_ratio": (useful / total) if total > 0 else 0.0,
            }
        )

    out.sort(
        key=lambda row: (
            row["noise_ratio"],
            row["total"],
            -row["useful_ratio"],
        ),
        reverse=True,
    )
    return out[:20]


def _write_markdown(
    report_date: str,
    summary: Dict[str, Any],
    daily_rows: List[Dict[str, Any]],
    noisy_rows: List[Dict[str, Any]],
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"stock-alert-noise-weekly-{report_date}.md"

    lines = [
        "# StockOps Alert Noise Weekly Report",
        "",
        f"- 日期(UTC): {report_date}",
        f"- 7日反馈总量: {summary['feedback_total']}",
        f"- 7日噪音反馈: {summary['feedback_noise']}",
        f"- 7日有用反馈: {summary['feedback_useful']}",
        f"- 7日噪音率: {summary['noise_ratio_7d']:.2%}",
        f"- 7日有用率: {summary['useful_ratio_7d']:.2%}",
        "",
        "## 每日趋势",
        "",
        "| Date | Total | Noise | Useful | Noise Ratio | Useful Ratio |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for row in daily_rows:
        lines.append(
            f"| {row['date']} | {row['total']} | {row['noise']} | {row['useful']} | "
            f"{row['noise_ratio']:.1%} | {row['useful_ratio']:.1%} |"
        )

    lines.extend(
        [
            "",
            "## 高噪音分组（Top 20）",
            "",
            "| Ticker | Signal Type | Total | Noise | Useful | Noise Ratio |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )

    for row in noisy_rows:
        lines.append(
            f"| {row['ticker']} | {row['signal_type']} | {row['total']} | {row['noise']} | "
            f"{row['useful']} | {row['noise_ratio']:.1%} |"
        )

    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_csv(report_date: str, rows: List[Dict[str, Any]], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"stock_alert_noise_weekly_{report_date}.csv"
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=[
                "ticker",
                "signal_type",
                "total",
                "noise",
                "useful",
                "noise_ratio",
                "useful_ratio",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def run_weekly_noise_report(days: int, limit: int, md_dir: str, csv_dir: str) -> Dict[str, Any]:
    started = _now_utc()
    report_date = started.date().isoformat()
    logger.info(f"[ALERT_NOISE_WEEKLY_START] days={days} limit={limit}")

    supabase = _init_supabase()
    feedback_rows = _load_feedback_rows(supabase=supabase, days=days, limit=limit)
    alert_ids = sorted(
        {
            int(row.get("alert_id") or 0)
            for row in feedback_rows
            if int(row.get("alert_id") or 0) > 0
        }
    )
    event_map = _load_event_map(supabase=supabase, alert_ids=alert_ids)

    daily_rows, summary = _bucket_daily(rows=feedback_rows, days=days)
    noisy_rows = _bucket_noisy_tickers(rows=feedback_rows, event_map=event_map)

    md_path = _write_markdown(
        report_date=report_date,
        summary=summary,
        daily_rows=daily_rows,
        noisy_rows=noisy_rows,
        output_dir=Path(md_dir),
    )
    csv_path = _write_csv(
        report_date=report_date,
        rows=noisy_rows,
        output_dir=Path(csv_dir),
    )

    elapsed = (_now_utc() - started).total_seconds()
    result = {
        "report_date": report_date,
        "feedback_total": summary["feedback_total"],
        "feedback_noise": summary["feedback_noise"],
        "noise_ratio_7d": round(summary["noise_ratio_7d"], 6),
        "groups": len(noisy_rows),
        "markdown": str(md_path),
        "csv": str(csv_path),
        "elapsed_sec": round(elapsed, 2),
    }
    logger.info("[ALERT_NOISE_WEEKLY_DONE] " + ", ".join([f"{k}={v}" for k, v in result.items()]))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="StockOps alert noise weekly report")
    parser.add_argument("--days", type=int, default=7, help="回看天数")
    parser.add_argument("--limit", type=int, default=8000, help="反馈读取上限")
    parser.add_argument("--md-dir", type=str, default="docs/reports", help="Markdown 输出目录")
    parser.add_argument("--csv-dir", type=str, default="data/reports", help="CSV 输出目录")
    args = parser.parse_args()

    run_weekly_noise_report(
        days=max(3, args.days),
        limit=max(500, args.limit),
        md_dir=args.md_dir.strip() or "docs/reports",
        csv_dir=args.csv_dir.strip() or "data/reports",
    )


if __name__ == "__main__":
    main()
