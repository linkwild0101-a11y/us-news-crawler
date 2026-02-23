#!/usr/bin/env python3
"""Stock V3 机会生命周期复盘报表脚本。"""

from __future__ import annotations

import argparse
import csv
import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _extract_event_type(text: str) -> str:
    normalized = (text or "").strip()
    if not normalized:
        return "unknown"
    if " x" in normalized:
        normalized = normalized.split(" x", 1)[0]
    return normalized[:32]


def _load_opportunities(supabase, limit: int) -> List[Dict[str, Any]]:
    rows = (
        supabase.table("stock_opportunities_v2")
        .select(
            "id,ticker,side,is_active,expires_at,as_of,catalysts,opportunity_score,confidence,risk_level"
        )
        .order("as_of", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    return rows


def _load_closed_positions_24h(supabase, cutoff_iso: str) -> List[Dict[str, Any]]:
    try:
        rows = (
            supabase.table("portfolio_paper_positions")
            .select("id,ticker,realized_pnl,exit_ts")
            .eq("status", "CLOSED")
            .gte("exit_ts", cutoff_iso)
            .order("exit_ts", desc=True)
            .limit(500)
            .execute()
            .data
            or []
        )
    except Exception:
        rows = []
    return rows


def _count_rows(
    rows: List[Dict[str, Any]],
    now: datetime,
    window_hours: int,
) -> Dict[str, Any]:
    cutoff = now - timedelta(hours=window_hours)
    cutoff_iso = cutoff.isoformat()
    expiring_upper = now + timedelta(hours=24)

    generated_count = 0
    active_count = 0
    long_count = 0
    short_count = 0
    expiring_count = 0
    expired_24h = 0
    event_counter: Counter[str] = Counter()

    for row in rows:
        as_of = str(row.get("as_of") or "")
        expires_at = str(row.get("expires_at") or "")
        is_active = bool(row.get("is_active"))
        side = str(row.get("side") or "").upper()
        catalysts = row.get("catalysts") if isinstance(row.get("catalysts"), list) else []

        if as_of >= cutoff_iso:
            generated_count += 1
        if is_active:
            active_count += 1
            if side == "LONG":
                long_count += 1
            elif side == "SHORT":
                short_count += 1
            if expires_at and now.isoformat() <= expires_at <= expiring_upper.isoformat():
                expiring_count += 1
        else:
            if expires_at and cutoff_iso <= expires_at <= now.isoformat():
                expired_24h += 1

        for catalyst in catalysts:
            event_type = _extract_event_type(str(catalyst))
            event_counter[event_type] += 1

    top_event_types = [
        {"event_type": name, "count": count} for name, count in event_counter.most_common(6)
    ]
    return {
        "generated_count": generated_count,
        "active_count": active_count,
        "long_count": long_count,
        "short_count": short_count,
        "expiring_24h_count": expiring_count,
        "expired_24h_count": expired_24h,
        "top_event_types": top_event_types,
    }


def _build_paper_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(rows)
    if total <= 0:
        return {
            "paper_closed_24h_count": 0,
            "paper_win_rate_24h": 0.0,
            "paper_realized_pnl_24h": 0.0,
        }
    wins = sum(1 for row in rows if _safe_float(row.get("realized_pnl"), 0.0) > 0)
    realized = round(sum(_safe_float(row.get("realized_pnl"), 0.0) for row in rows), 6)
    return {
        "paper_closed_24h_count": total,
        "paper_win_rate_24h": round(wins / total, 4),
        "paper_realized_pnl_24h": realized,
    }


def _write_markdown_report(
    run_id: str,
    report_date: str,
    metrics: Dict[str, Any],
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"stock_v3_lifecycle_{report_date}.md"
    lines = [
        "# Stock V3 机会生命周期复盘日报",
        "",
        f"- 日期(UTC): {report_date}",
        f"- run_id: {run_id}",
        "",
        "## 核心统计",
        "",
        f"- 新生成机会(窗口内): {metrics['generated_count']}",
        f"- 当前活跃机会: {metrics['active_count']}",
        f"- LONG/SHORT: {metrics['long_count']}/{metrics['short_count']}",
        f"- 24h 内临近到期: {metrics['expiring_24h_count']}",
        f"- 24h 内失效机会: {metrics['expired_24h_count']}",
        f"- 24h 已平仓(纸上): {metrics['paper_closed_24h_count']}",
        f"- 24h 纸上胜率: {metrics['paper_win_rate_24h']}",
        f"- 24h 纸上已实现PnL: {metrics['paper_realized_pnl_24h']}",
        "",
        "## 事件类型贡献 Top",
        "",
    ]
    top_event_types = metrics.get("top_event_types") or []
    if top_event_types:
        for item in top_event_types:
            lines.append(f"- {item.get('event_type')}: {item.get('count')}")
    else:
        lines.append("- 暂无")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_csv_report(
    run_id: str,
    report_date: str,
    metrics: Dict[str, Any],
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"stock_v3_lifecycle_{report_date}.csv"
    rows = [
        ("run_id", run_id),
        ("report_date", report_date),
        ("generated_count", metrics["generated_count"]),
        ("active_count", metrics["active_count"]),
        ("long_count", metrics["long_count"]),
        ("short_count", metrics["short_count"]),
        ("expiring_24h_count", metrics["expiring_24h_count"]),
        ("expired_24h_count", metrics["expired_24h_count"]),
        ("paper_closed_24h_count", metrics["paper_closed_24h_count"]),
        ("paper_win_rate_24h", metrics["paper_win_rate_24h"]),
        ("paper_realized_pnl_24h", metrics["paper_realized_pnl_24h"]),
    ]
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(["metric_name", "metric_value"])
        writer.writerows(rows)
    return path


def _upsert_lifecycle_snapshot(
    supabase,
    run_id: str,
    window_hours: int,
    metrics: Dict[str, Any],
) -> None:
    payload = {
        "run_id": run_id,
        "snapshot_date": _now_utc().date().isoformat(),
        "window_hours": window_hours,
        "generated_count": int(metrics["generated_count"]),
        "active_count": int(metrics["active_count"]),
        "long_count": int(metrics["long_count"]),
        "short_count": int(metrics["short_count"]),
        "expiring_24h_count": int(metrics["expiring_24h_count"]),
        "expired_24h_count": int(metrics["expired_24h_count"]),
        "paper_closed_24h_count": int(metrics["paper_closed_24h_count"]),
        "paper_win_rate_24h": _safe_float(metrics["paper_win_rate_24h"], 0.0),
        "top_event_types": metrics["top_event_types"],
        "notes": "daily_lifecycle_report",
        "as_of": _now_utc().isoformat(),
    }
    supabase.table("opportunity_lifecycle_snapshots").upsert(
        payload,
        on_conflict="run_id",
    ).execute()


def _upsert_run_metrics(supabase, run_id: str, metrics: Dict[str, Any]) -> int:
    numeric_keys = [
        "generated_count",
        "active_count",
        "long_count",
        "short_count",
        "expiring_24h_count",
        "expired_24h_count",
        "paper_closed_24h_count",
        "paper_win_rate_24h",
        "paper_realized_pnl_24h",
    ]
    rows = [
        {
            "run_id": run_id,
            "metric_name": f"lifecycle_{key}",
            "metric_value": float(metrics[key]),
            "metric_unit": "ratio" if "rate" in key else "count",
        }
        for key in numeric_keys
    ]
    if not rows:
        return 0
    try:
        supabase.table("research_run_metrics").upsert(
            rows,
            on_conflict="run_id,metric_name",
        ).execute()
        return len(rows)
    except Exception as e:
        logger.warning(f"[LIFECYCLE_V3_METRICS_UPSERT_FAILED] error={str(e)[:120]}")
        return 0


def _insert_artifacts(supabase, run_id: str, artifacts: List[Path]) -> int:
    rows = []
    for artifact in artifacts:
        rows.append(
            {
                "run_id": run_id,
                "artifact_type": "lifecycle_report",
                "artifact_ref": str(artifact),
                "checksum": "",
            }
        )
    if not rows:
        return 0
    try:
        supabase.table("research_run_artifacts").insert(rows).execute()
        return len(rows)
    except Exception:
        return 0


def _log_run_start(supabase, run_id: str, window_hours: int, limit: int) -> None:
    payload = {
        "run_id": run_id,
        "pipeline_name": "stock_v3_lifecycle_report",
        "pipeline_version": os.getenv("GITHUB_SHA", "")[:12] or "local",
        "trigger_type": os.getenv("GITHUB_EVENT_NAME", "manual"),
        "status": "running",
        "started_at": _now_utc().isoformat(),
        "input_window": {
            "window_hours": window_hours,
            "limit": limit,
        },
        "params_json": {
            "window_hours": window_hours,
            "limit": limit,
        },
        "commit_sha": os.getenv("GITHUB_SHA", "")[:40],
        "as_of": _now_utc().isoformat(),
    }
    try:
        supabase.table("research_runs").upsert(payload, on_conflict="run_id").execute()
    except Exception as e:
        logger.warning(f"[LIFECYCLE_V3_RUN_START_FAILED] error={str(e)[:120]}")


def _log_run_finish(supabase, run_id: str, status: str, notes: str) -> None:
    try:
        (
            supabase.table("research_runs")
            .update(
                {
                    "status": status,
                    "ended_at": _now_utc().isoformat(),
                    "notes": notes[:1000],
                    "as_of": _now_utc().isoformat(),
                }
            )
            .eq("run_id", run_id)
            .execute()
        )
    except Exception as e:
        logger.warning(f"[LIFECYCLE_V3_RUN_FINISH_FAILED] error={str(e)[:120]}")


def run_lifecycle_report(
    run_id: Optional[str],
    window_hours: int,
    limit: int,
    report_dir: str,
    csv_dir: str,
) -> Dict[str, Any]:
    supabase = _init_supabase()
    final_run_id = run_id or f"lifecycle-{_now_utc().strftime('%Y%m%d%H%M%S')}"
    _log_run_start(supabase=supabase, run_id=final_run_id, window_hours=window_hours, limit=limit)

    now = _now_utc()
    cutoff_iso = (now - timedelta(hours=window_hours)).isoformat()
    report_date = now.date().isoformat()

    try:
        rows = _load_opportunities(supabase=supabase, limit=limit)
        lifecycle = _count_rows(rows=rows, now=now, window_hours=window_hours)
        paper = _build_paper_metrics(_load_closed_positions_24h(supabase=supabase, cutoff_iso=cutoff_iso))
        merged = {**lifecycle, **paper}

        markdown_path = _write_markdown_report(
            run_id=final_run_id,
            report_date=report_date,
            metrics=merged,
            output_dir=Path(report_dir),
        )
        csv_path = _write_csv_report(
            run_id=final_run_id,
            report_date=report_date,
            metrics=merged,
            output_dir=Path(csv_dir),
        )

        _upsert_lifecycle_snapshot(
            supabase=supabase,
            run_id=final_run_id,
            window_hours=window_hours,
            metrics=merged,
        )
        _upsert_run_metrics(supabase=supabase, run_id=final_run_id, metrics=merged)
        _insert_artifacts(supabase=supabase, run_id=final_run_id, artifacts=[markdown_path, csv_path])

        summary = {
            "run_id": final_run_id,
            "opportunities_loaded": len(rows),
            "report_markdown": str(markdown_path),
            "report_csv": str(csv_path),
            **merged,
        }
        _log_run_finish(
            supabase=supabase,
            run_id=final_run_id,
            status="success",
            notes=f"report={markdown_path.name}",
        )
        logger.info("[LIFECYCLE_V3_DONE] " + ", ".join([f"{k}={v}" for k, v in summary.items()]))
        return summary
    except Exception as e:
        _log_run_finish(
            supabase=supabase,
            run_id=final_run_id,
            status="failed",
            notes=f"error={str(e)[:300]}",
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock V3 lifecycle report runner")
    parser.add_argument("--run-id", type=str, default=None, help="报表 run_id")
    parser.add_argument("--window-hours", type=int, default=24, help="统计窗口小时")
    parser.add_argument("--limit", type=int, default=8000, help="样本上限")
    parser.add_argument(
        "--report-dir",
        type=str,
        default="docs/reports",
        help="Markdown 报表输出目录",
    )
    parser.add_argument(
        "--csv-dir",
        type=str,
        default="data/reports",
        help="CSV 报表输出目录",
    )
    args = parser.parse_args()

    summary = run_lifecycle_report(
        run_id=args.run_id,
        window_hours=max(1, args.window_hours),
        limit=max(1000, args.limit),
        report_dir=args.report_dir.strip() or "docs/reports",
        csv_dir=args.csv_dir.strip() or "data/reports",
    )
    logger.info("[LIFECYCLE_V3_METRICS] " + ", ".join([f"{k}={v}" for k, v in summary.items()]))


if __name__ == "__main__":
    main()
