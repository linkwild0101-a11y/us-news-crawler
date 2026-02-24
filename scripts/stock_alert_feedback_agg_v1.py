#!/usr/bin/env python3
"""StockOps P0: 告警反馈聚合与阈值建议报告。"""

from __future__ import annotations

import argparse
import csv
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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


@dataclass
class FeedbackAggregate:
    """反馈聚合指标。"""

    ticker: str
    signal_type: str
    total: int
    useful: int
    noise: int
    useful_ratio: float
    noise_ratio: float
    avg_score: float
    last_feedback_at: str
    recommendation: str


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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _load_feedback_rows(supabase, days: int, limit: int) -> List[Dict[str, Any]]:
    cutoff = (_now_utc() - timedelta(days=max(1, days))).isoformat()
    rows = (
        supabase.table("stock_alert_feedback_v1")
        .select("alert_id,label,created_at")
        .gte("created_at", cutoff)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    return rows


def _load_event_map(supabase, alert_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    if not alert_ids:
        return {}

    rows = (
        supabase.table("stock_alert_events_v1")
        .select("id,ticker,signal_type,alert_score")
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


def _recommendation(total: int, useful_ratio: float, noise_ratio: float) -> str:
    if total < 5:
        return "样本不足，保持观察"
    if noise_ratio >= 0.60:
        return "噪音偏高：建议 min_score +5，cooldown +30m"
    if useful_ratio >= 0.70:
        return "质量较好：可适度放宽阈值或扩大覆盖"
    return "维持当前阈值，继续收集反馈"


def _aggregate(rows: List[Dict[str, Any]], event_map: Dict[int, Dict[str, Any]]) -> Tuple[List[FeedbackAggregate], Dict[str, Any]]:
    bucket: Dict[str, Dict[str, Any]] = {}
    totals = {
        "feedback_total": 0,
        "feedback_useful": 0,
        "feedback_noise": 0,
    }

    for row in rows:
        alert_id = int(row.get("alert_id") or 0)
        label = str(row.get("label") or "").strip().lower()
        created_at = str(row.get("created_at") or "")
        if alert_id <= 0 or label not in ("useful", "noise"):
            continue

        event = event_map.get(alert_id) or {}
        ticker = str(event.get("ticker") or "UNKNOWN").upper()
        signal_type = str(event.get("signal_type") or "opportunity").strip().lower()
        score = _safe_float(event.get("alert_score"), 0.0)

        key = f"{ticker}|{signal_type}"
        if key not in bucket:
            bucket[key] = {
                "ticker": ticker,
                "signal_type": signal_type,
                "total": 0,
                "useful": 0,
                "noise": 0,
                "score_sum": 0.0,
                "last_feedback_at": created_at,
            }

        item = bucket[key]
        item["total"] += 1
        item["score_sum"] += score
        if label == "useful":
            item["useful"] += 1
            totals["feedback_useful"] += 1
        else:
            item["noise"] += 1
            totals["feedback_noise"] += 1

        if created_at > str(item.get("last_feedback_at") or ""):
            item["last_feedback_at"] = created_at

        totals["feedback_total"] += 1

    aggregates: List[FeedbackAggregate] = []
    for item in bucket.values():
        total = int(item["total"])
        useful = int(item["useful"])
        noise = int(item["noise"])
        useful_ratio = useful / total if total > 0 else 0.0
        noise_ratio = noise / total if total > 0 else 0.0
        avg_score = float(item["score_sum"]) / total if total > 0 else 0.0
        aggregates.append(
            FeedbackAggregate(
                ticker=str(item["ticker"]),
                signal_type=str(item["signal_type"]),
                total=total,
                useful=useful,
                noise=noise,
                useful_ratio=useful_ratio,
                noise_ratio=noise_ratio,
                avg_score=avg_score,
                last_feedback_at=str(item["last_feedback_at"]),
                recommendation=_recommendation(total=total, useful_ratio=useful_ratio, noise_ratio=noise_ratio),
            )
        )

    aggregates.sort(key=lambda x: (x.total, x.noise_ratio, x.useful_ratio), reverse=True)

    summary = {
        **totals,
        "noise_ratio": (totals["feedback_noise"] / totals["feedback_total"]) if totals["feedback_total"] > 0 else 0.0,
        "group_count": len(aggregates),
    }
    return aggregates, summary


def _write_markdown(report_date: str, days: int, summary: Dict[str, Any], rows: List[FeedbackAggregate], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"stock-alert-feedback-daily-{report_date}.md"

    lines = [
        "# StockOps Alert Feedback Daily Report",
        "",
        f"- 日期(UTC): {report_date}",
        f"- 回看窗口: {days} 天",
        f"- 反馈总量: {summary['feedback_total']}",
        f"- useful: {summary['feedback_useful']}",
        f"- noise: {summary['feedback_noise']}",
        f"- noise_ratio: {summary['noise_ratio']:.2%}",
        "",
        "## 调优建议（Top 10）",
        "",
        "| Ticker | Signal Type | Total | Useful | Noise | Noise Ratio | Avg Score | Recommendation |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]

    for item in rows[:10]:
        lines.append(
            f"| {item.ticker} | {item.signal_type} | {item.total} | {item.useful} | {item.noise} | "
            f"{item.noise_ratio:.1%} | {item.avg_score:.1f} | {item.recommendation} |"
        )

    lines.extend(
        [
            "",
            "## 全量明细",
            "",
            "| Ticker | Signal Type | Total | Useful Ratio | Noise Ratio | Last Feedback At |",
            "|---|---|---:|---:|---:|---|",
        ]
    )

    for item in rows:
        lines.append(
            f"| {item.ticker} | {item.signal_type} | {item.total} | {item.useful_ratio:.1%} | "
            f"{item.noise_ratio:.1%} | {item.last_feedback_at or '-'} |"
        )

    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_csv(report_date: str, rows: List[FeedbackAggregate], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"stock_alert_feedback_daily_{report_date}.csv"
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=[
                "ticker",
                "signal_type",
                "total",
                "useful",
                "noise",
                "useful_ratio",
                "noise_ratio",
                "avg_score",
                "last_feedback_at",
                "recommendation",
            ],
        )
        writer.writeheader()
        for item in rows:
            writer.writerow(
                {
                    "ticker": item.ticker,
                    "signal_type": item.signal_type,
                    "total": item.total,
                    "useful": item.useful,
                    "noise": item.noise,
                    "useful_ratio": round(item.useful_ratio, 6),
                    "noise_ratio": round(item.noise_ratio, 6),
                    "avg_score": round(item.avg_score, 4),
                    "last_feedback_at": item.last_feedback_at,
                    "recommendation": item.recommendation,
                }
            )
    return path


def run_feedback_agg(days: int, limit: int, md_dir: str, csv_dir: str) -> Dict[str, Any]:
    """聚合反馈并生成日报。"""
    started = _now_utc()
    report_date = started.date().isoformat()
    logger.info(
        f"[ALERT_FEEDBACK_AGG_START] days={days} limit={limit} md_dir={md_dir} csv_dir={csv_dir}"
    )

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

    aggregates, summary = _aggregate(rows=feedback_rows, event_map=event_map)
    md_path = _write_markdown(
        report_date=report_date,
        days=days,
        summary=summary,
        rows=aggregates,
        output_dir=Path(md_dir),
    )
    csv_path = _write_csv(
        report_date=report_date,
        rows=aggregates,
        output_dir=Path(csv_dir),
    )

    elapsed = (_now_utc() - started).total_seconds()
    result = {
        "report_date": report_date,
        "feedback_total": summary["feedback_total"],
        "feedback_useful": summary["feedback_useful"],
        "feedback_noise": summary["feedback_noise"],
        "noise_ratio": round(summary["noise_ratio"], 6),
        "group_count": summary["group_count"],
        "markdown": str(md_path),
        "csv": str(csv_path),
        "elapsed_sec": round(elapsed, 2),
    }
    logger.info("[ALERT_FEEDBACK_AGG_DONE] " + ", ".join([f"{k}={v}" for k, v in result.items()]))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="StockOps alert feedback daily aggregator")
    parser.add_argument("--days", type=int, default=7, help="回看天数")
    parser.add_argument("--limit", type=int, default=5000, help="反馈读取上限")
    parser.add_argument("--md-dir", type=str, default="docs/reports", help="Markdown 输出目录")
    parser.add_argument("--csv-dir", type=str, default="data/reports", help="CSV 输出目录")
    args = parser.parse_args()

    run_feedback_agg(
        days=max(1, args.days),
        limit=max(100, args.limit),
        md_dir=args.md_dir.strip() or "docs/reports",
        csv_dir=args.csv_dir.strip() or "data/reports",
    )


if __name__ == "__main__":
    main()
