#!/usr/bin/env python3
"""Stock V3 运行摘要输出脚本（标准化字段）。"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
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
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("缺少 SUPABASE_URL / SUPABASE_KEY")
    return create_client(url, key)


def _safe_count_rows(supabase: Any, table: str, **filters: Any) -> Optional[int]:
    try:
        query = supabase.table(table).select("id", count="exact")
        for key, value in filters.items():
            query = query.eq(key, value)
        result = query.limit(1).execute()
        return int(result.count or 0)
    except Exception as e:
        logger.warning(f"[RUN_SUMMARY_COUNT_FAILED] table={table} error={str(e)[:120]}")
        return None


def _load_latest_snapshot(supabase: Any) -> Dict[str, Any]:
    try:
        result = (
            supabase.table("stock_dashboard_snapshot_v2")
            .select("snapshot_time,risk_badge,data_health,run_id")
            .eq("is_active", True)
            .order("snapshot_time", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        return result.data or {}
    except Exception as e:
        logger.warning(f"[RUN_SUMMARY_SNAPSHOT_FAILED] error={str(e)[:120]}")
        return {}


def _load_source_health(
    supabase: Any,
    health_date: str,
    health_run_id: str,
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    resolved_date = health_date

    try:
        if health_run_id:
            by_run = (
                supabase.table("source_health_daily")
                .select("source_id,status,success_rate,null_rate,health_date,as_of,run_id")
                .eq("run_id", health_run_id)
                .order("as_of", desc=True)
                .limit(20)
                .execute()
            )
            rows = by_run.data or []
            if rows:
                resolved_date = str(rows[0].get("health_date") or health_date)
    except Exception as e:
        logger.warning(f"[RUN_SUMMARY_HEALTH_BY_RUN_FAILED] error={str(e)[:120]}")

    if not rows:
        try:
            by_date = (
                supabase.table("source_health_daily")
                .select("source_id,status,success_rate,null_rate,health_date,as_of,run_id")
                .eq("health_date", health_date)
                .order("as_of", desc=True)
                .limit(30)
                .execute()
            )
            rows = by_date.data or []
        except Exception as e:
            logger.warning(f"[RUN_SUMMARY_HEALTH_BY_DATE_FAILED] error={str(e)[:120]}")
            rows = []

    if not rows:
        return {
            "health_date": resolved_date,
            "source_health_total": 0,
            "source_health_healthy": 0,
            "source_health_degraded": 0,
            "source_health_critical": 0,
            "source_health_avg_success_rate": None,
            "source_health_non_null_rate": None,
        }

    latest_by_source: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        source_id = str(row.get("source_id") or "")
        if source_id and source_id not in latest_by_source:
            latest_by_source[source_id] = row

    statuses = {"healthy": 0, "degraded": 0, "critical": 0}
    success_values: List[float] = []
    non_null_values: List[float] = []

    for row in latest_by_source.values():
        status = str(row.get("status") or "healthy")
        if status in statuses:
            statuses[status] += 1
        try:
            success_values.append(float(row.get("success_rate")))
        except Exception:
            pass
        try:
            non_null_values.append(max(0.0, 1.0 - float(row.get("null_rate"))))
        except Exception:
            pass

    avg_success = (
        round(sum(success_values) / len(success_values), 4) if success_values else None
    )
    avg_non_null = (
        round(sum(non_null_values) / len(non_null_values), 4) if non_null_values else None
    )

    return {
        "health_date": resolved_date,
        "source_health_total": len(latest_by_source),
        "source_health_healthy": statuses["healthy"],
        "source_health_degraded": statuses["degraded"],
        "source_health_critical": statuses["critical"],
        "source_health_avg_success_rate": avg_success,
        "source_health_non_null_rate": avg_non_null,
    }


def build_run_summary(
    duration_sec: int,
    health_date: str,
    health_run_id: str,
) -> Dict[str, Any]:
    """构建固定结构的 run summary。"""
    supabase = _init_supabase()
    snapshot = _load_latest_snapshot(supabase)

    signals_total = _safe_count_rows(supabase, "stock_signals_v2", is_active=True)
    opportunities_total = _safe_count_rows(supabase, "stock_opportunities_v2", is_active=True)
    opportunities_long = _safe_count_rows(
        supabase,
        "stock_opportunities_v2",
        is_active=True,
        side="LONG",
    )
    opportunities_short = _safe_count_rows(
        supabase,
        "stock_opportunities_v2",
        is_active=True,
        side="SHORT",
    )

    health = _load_source_health(
        supabase=supabase,
        health_date=health_date,
        health_run_id=health_run_id,
    )

    summary = {
        "schema_version": "stock_run_summary_v1",
        "generated_at_utc": _now_utc().isoformat(),
        "pipeline_name": "stock_pipeline_v2_incremental",
        "pipeline_duration_sec": max(0, int(duration_sec)),
        "run_id": str(snapshot.get("run_id") or ""),
        "latest_snapshot_time": str(snapshot.get("snapshot_time") or ""),
        "risk_badge": str(snapshot.get("risk_badge") or ""),
        "signals_active": signals_total,
        "opportunities_active": opportunities_total,
        "opportunities_long_active": opportunities_long,
        "opportunities_short_active": opportunities_short,
        "source_health_date": health["health_date"],
        "source_health_total": health["source_health_total"],
        "source_health_healthy": health["source_health_healthy"],
        "source_health_degraded": health["source_health_degraded"],
        "source_health_critical": health["source_health_critical"],
        "source_health_avg_success_rate": health["source_health_avg_success_rate"],
        "source_health_non_null_rate": health["source_health_non_null_rate"],
    }
    return summary


def _append_step_summary(summary: Dict[str, Any]) -> None:
    path = os.getenv("GITHUB_STEP_SUMMARY", "")
    if not path:
        return

    with open(path, "a", encoding="utf-8") as fp:
        fp.write("## Stock V2 Run Summary (Standardized)\n")
        fp.write(f"- Run ID: `{summary['run_id']}`\n")
        fp.write(f"- Pipeline duration: **{summary['pipeline_duration_sec']}s**\n")
        fp.write(
            f"- Signals/Opportunities: **{summary['signals_active']} / "
            f"{summary['opportunities_active']}**\n"
        )
        fp.write(
            f"- LONG/SHORT: **{summary['opportunities_long_active']} / "
            f"{summary['opportunities_short_active']}**\n"
        )
        fp.write(
            f"- Source health (H/D/C): **{summary['source_health_healthy']} / "
            f"{summary['source_health_degraded']} / {summary['source_health_critical']}**\n"
        )
        fp.write(
            f"- Source non-null rate(avg): **{summary['source_health_non_null_rate']}**\n"
        )
        fp.write("```json\n")
        fp.write(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        fp.write("\n```\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock V3 standardized run summary")
    parser.add_argument("--duration-sec", type=int, default=0, help="本轮流水线时长（秒）")
    parser.add_argument(
        "--health-date",
        type=str,
        default=_now_utc().date().isoformat(),
        help="source health 日期（UTC, YYYY-MM-DD）",
    )
    parser.add_argument(
        "--health-run-id",
        type=str,
        default="",
        help="source health 的 run_id（可选）",
    )
    args = parser.parse_args()

    summary = build_run_summary(
        duration_sec=max(0, args.duration_sec),
        health_date=args.health_date,
        health_run_id=args.health_run_id.strip(),
    )
    _append_step_summary(summary)
    logger.info(
        "[STOCK_V2_RUN_SUMMARY] "
        + json.dumps(summary, ensure_ascii=False, sort_keys=True)
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"[STOCK_V2_RUN_SUMMARY_FAILED] error={str(e)}")
        raise
