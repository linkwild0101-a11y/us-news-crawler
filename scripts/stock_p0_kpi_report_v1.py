#!/usr/bin/env python3
"""StockOps P0 KPI 每日报告脚本。"""

from __future__ import annotations

import argparse
import csv
import logging
import os
from dataclasses import dataclass
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


@dataclass
class P0Gate:
    latency_p95_sec: float = 60.0
    alert_ctr: float = 0.18
    noise_ratio: float = 0.30
    retention_7d: float = 0.25


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _init_supabase():
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


def _load_daily_kpi(supabase: Any, days: int) -> List[Dict[str, Any]]:
    cutoff = (_now_utc() - timedelta(days=max(1, days))).date().isoformat()
    rows = (
        supabase.table("stock_alert_kpi_daily_v1")
        .select(
            "metric_date,alert_sent,alert_opened,feedback_total,feedback_noise,feedback_useful,"
            "latency_p95_sec,alert_ctr,noise_ratio"
        )
        .gte("metric_date", cutoff)
        .order("metric_date", desc=False)
        .limit(120)
        .execute()
        .data
        or []
    )
    return rows


def _load_retention_7d(supabase: Any) -> float:
    """用“近 7 日有二次及以上打开行为用户占比”近似留存。"""
    start = (_now_utc() - timedelta(days=7)).isoformat()
    rows = (
        supabase.table("stock_alert_open_events_v1")
        .select("user_id,opened_at")
        .gte("opened_at", start)
        .limit(8000)
        .execute()
        .data
        or []
    )
    if not rows:
        return 0.0

    user_days: Dict[str, set] = {}
    for row in rows:
        user_id = str(row.get("user_id") or "").strip()
        opened_at = str(row.get("opened_at") or "")
        if not user_id or not opened_at:
            continue
        day = opened_at[:10]
        if not day:
            continue
        user_days.setdefault(user_id, set()).add(day)

    if not user_days:
        return 0.0
    retained = sum(1 for days_set in user_days.values() if len(days_set) >= 2)
    return round(retained / len(user_days), 4)


def _aggregate(rows: List[Dict[str, Any]], retention_7d: float) -> Dict[str, Any]:
    sent_sum = sum(_safe_int(row.get("alert_sent"), 0) for row in rows)
    opened_sum = sum(_safe_int(row.get("alert_opened"), 0) for row in rows)
    feedback_sum = sum(_safe_int(row.get("feedback_total"), 0) for row in rows)
    noise_sum = sum(_safe_int(row.get("feedback_noise"), 0) for row in rows)

    latency_values = [
        _safe_float(row.get("latency_p95_sec"), 0.0)
        for row in rows
        if _safe_float(row.get("latency_p95_sec"), 0.0) > 0
    ]
    latency_p95 = round(max(latency_values), 3) if latency_values else 0.0

    alert_ctr = round(opened_sum / sent_sum, 4) if sent_sum > 0 else 0.0
    noise_ratio = round(noise_sum / feedback_sum, 4) if feedback_sum > 0 else 0.0

    return {
        "window_days": len(rows),
        "alert_sent": sent_sum,
        "alert_opened": opened_sum,
        "feedback_total": feedback_sum,
        "feedback_noise": noise_sum,
        "latency_p95_sec": latency_p95,
        "alert_ctr": alert_ctr,
        "noise_ratio": noise_ratio,
        "retention_7d": retention_7d,
    }


def _evaluate_gate(summary: Dict[str, Any], gate: P0Gate) -> Dict[str, bool]:
    return {
        "latency_p95_ok": (
            summary["latency_p95_sec"] > 0
            and summary["latency_p95_sec"] <= gate.latency_p95_sec
        ),
        "alert_ctr_ok": summary["alert_ctr"] >= gate.alert_ctr,
        "noise_ratio_ok": (
            summary["feedback_total"] > 0
            and summary["noise_ratio"] <= gate.noise_ratio
        ),
        "retention_7d_ok": summary["retention_7d"] >= gate.retention_7d,
    }


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "metric_date",
        "alert_sent",
        "alert_opened",
        "feedback_total",
        "feedback_noise",
        "feedback_useful",
        "latency_p95_sec",
        "alert_ctr",
        "noise_ratio",
    ]
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _write_markdown(
    path: Path,
    rows: List[Dict[str, Any]],
    summary: Dict[str, Any],
    gate: Dict[str, bool],
    rule: P0Gate,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    lines.append("# StockOps P0 KPI Daily Report")
    lines.append("")
    lines.append(f"- 日期(UTC): {_now_utc().date().isoformat()}")
    lines.append(f"- 覆盖天数: {len(rows)}")
    lines.append(f"- alert_sent: {summary['alert_sent']}")
    lines.append(f"- alert_opened: {summary['alert_opened']}")
    lines.append(f"- feedback_total: {summary['feedback_total']}")
    lines.append(f"- latency_p95_sec: {summary['latency_p95_sec']}")
    lines.append(f"- alert_ctr: {summary['alert_ctr']:.2%}")
    lines.append(f"- noise_ratio: {summary['noise_ratio']:.2%}")
    lines.append(f"- retention_7d(proxy): {summary['retention_7d']:.2%}")
    lines.append("")
    lines.append("## Gate Check")
    lines.append("")
    lines.append("| KPI | Threshold | Value | Pass |")
    lines.append("|---|---:|---:|:---:|")
    latency_pass = "✅" if gate["latency_p95_ok"] else "❌"
    ctr_pass = "✅" if gate["alert_ctr_ok"] else "❌"
    noise_pass = "✅" if gate["noise_ratio_ok"] else "❌"
    retention_pass = "✅" if gate["retention_7d_ok"] else "❌"
    lines.append(
        f"| latency_p95_sec | <= {rule.latency_p95_sec:.0f} | "
        f"{summary['latency_p95_sec']:.3f} | {latency_pass} |"
    )
    lines.append(
        f"| alert_ctr | >= {rule.alert_ctr:.2%} | "
        f"{summary['alert_ctr']:.2%} | {ctr_pass} |"
    )
    lines.append(
        f"| noise_ratio | <= {rule.noise_ratio:.2%} | "
        f"{summary['noise_ratio']:.2%} | {noise_pass} |"
    )
    lines.append(
        f"| retention_7d(proxy) | >= {rule.retention_7d:.2%} | "
        f"{summary['retention_7d']:.2%} | {retention_pass} |"
    )
    lines.append("")
    lines.append("## Daily Detail")
    lines.append("")
    lines.append("| Date | Sent | Opened | Feedback | Noise | latency_p95(s) | CTR | Noise Ratio |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    detail_fmt = (
        "| {date} | {sent} | {opened} | {fb} | {noise} | "
        "{lat:.3f} | {ctr:.2%} | {nr:.2%} |"
    )
    for row in rows:
        lines.append(
            detail_fmt.format(
                date=str(row.get("metric_date") or ""),
                sent=_safe_int(row.get("alert_sent"), 0),
                opened=_safe_int(row.get("alert_opened"), 0),
                fb=_safe_int(row.get("feedback_total"), 0),
                noise=_safe_int(row.get("feedback_noise"), 0),
                lat=_safe_float(row.get("latency_p95_sec"), 0.0),
                ctr=_safe_float(row.get("alert_ctr"), 0.0),
                nr=_safe_float(row.get("noise_ratio"), 0.0),
            )
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append_summary(summary: Dict[str, Any], gate: Dict[str, bool]) -> None:
    output = os.getenv("GITHUB_STEP_SUMMARY", "").strip()
    if not output:
        return
    with open(output, "a", encoding="utf-8") as fp:
        fp.write("## StockOps P0 KPI Gate\n")
        fp.write(
            f"- Sent/Opened: **{summary['alert_sent']} / {summary['alert_opened']}**"
            f" (CTR **{summary['alert_ctr']:.2%}**)\n"
        )
        fp.write(
            f"- latency_p95: **{summary['latency_p95_sec']:.3f}s**, "
            f"noise_ratio: **{summary['noise_ratio']:.2%}**, "
            f"retention_7d(proxy): **{summary['retention_7d']:.2%}**\n"
        )
        fp.write(
            "- Gate: "
            f"latency {'✅' if gate['latency_p95_ok'] else '❌'}, "
            f"ctr {'✅' if gate['alert_ctr_ok'] else '❌'}, "
            f"noise {'✅' if gate['noise_ratio_ok'] else '❌'}, "
            f"retention {'✅' if gate['retention_7d_ok'] else '❌'}\n"
        )


def run_report(days: int, md_dir: str, csv_dir: str) -> Dict[str, Any]:
    supabase = _init_supabase()
    rows = _load_daily_kpi(supabase, days)
    retention = _load_retention_7d(supabase)
    summary = _aggregate(rows, retention)
    gate_rule = P0Gate()
    gate_result = _evaluate_gate(summary, gate_rule)

    report_date = _now_utc().date().isoformat()
    md_path = Path(md_dir) / f"stock-p0-kpi-daily-{report_date}.md"
    csv_path = Path(csv_dir) / f"stock_p0_kpi_daily_{report_date}.csv"

    _write_markdown(md_path, rows, summary, gate_result, gate_rule)
    _write_csv(csv_path, rows)
    _append_summary(summary, gate_result)

    logger.info(
        (
            "[P0_KPI_REPORT_DONE] days=%s sent=%s opened=%s ctr=%.4f "
            "noise=%.4f latency=%.3f md=%s csv=%s"
        ),
        days,
        summary["alert_sent"],
        summary["alert_opened"],
        summary["alert_ctr"],
        summary["noise_ratio"],
        summary["latency_p95_sec"],
        str(md_path),
        str(csv_path),
    )
    return {
        **summary,
        **gate_result,
        "markdown": str(md_path),
        "csv": str(csv_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="StockOps P0 KPI daily report")
    parser.add_argument("--days", type=int, default=7, help="回看天数")
    parser.add_argument("--md-dir", type=str, default="docs/reports", help="Markdown 输出目录")
    parser.add_argument("--csv-dir", type=str, default="data/reports", help="CSV 输出目录")
    args = parser.parse_args()

    logger.info(
        "[P0_KPI_REPORT_START] days=%s md_dir=%s csv_dir=%s",
        args.days,
        args.md_dir,
        args.csv_dir,
    )
    try:
        metrics = run_report(args.days, args.md_dir, args.csv_dir)
    except Exception as exc:
        message = str(exc)
        if "stock_alert_kpi_daily_v1" in message or "stock_alert_open_events_v1" in message:
            logger.error(
                "[P0_KPI_REPORT_MISSING_SCHEMA] error=%s; "
                "请先执行 sql/2026-02-24_stock_alert_open_events_and_kpi_view.sql",
                message[:200],
            )
            return
        logger.error("[P0_KPI_REPORT_FAILED] error=%s", message[:200])
        raise
    logger.info("[P0_KPI_REPORT_METRICS] %s", metrics)


if __name__ == "__main__":
    main()
