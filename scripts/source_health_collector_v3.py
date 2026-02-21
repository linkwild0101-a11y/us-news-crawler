#!/usr/bin/env python3
"""Stock V3 数据源健康快照采集脚本。"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from supabase import create_client

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.refresh_market_digest import FRED_SERIES, STOOQ_SYMBOLS  # noqa: E402
from scripts.refresh_market_digest import _fetch_fred_latest, _fetch_stooq_close  # noqa: E402

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


def _p95_latency_ms(values: List[float]) -> int:
    """返回 p95 延迟（毫秒）。"""
    if not values:
        return 0
    sorted_values = sorted(values)
    idx = max(0, math.ceil(len(sorted_values) * 0.95) - 1)
    return int(round(sorted_values[idx] * 1000))


def _build_status(
    source_type: str,
    success_rate: float,
    freshness_sec: int,
    null_rate: float,
) -> str:
    """根据 source type 与阈值推导健康状态。"""
    if source_type == "market_price":
        if success_rate >= 0.99 and freshness_sec <= 86400 and null_rate <= 0.05:
            return "healthy"
        if success_rate >= 0.66 and freshness_sec <= 172800:
            return "degraded"
        return "critical"

    if source_type == "macro":
        if success_rate >= 0.985 and freshness_sec <= 172800 and null_rate <= 0.08:
            return "healthy"
        if success_rate >= 0.5 and freshness_sec <= 259200:
            return "degraded"
        return "critical"

    if source_type == "news":
        if success_rate >= 0.99 and freshness_sec <= 7200 and null_rate <= 0.03:
            return "healthy"
        if success_rate >= 0.5 and freshness_sec <= 21600:
            return "degraded"
        return "critical"

    return "healthy"


def _measure_market_source(
    fetcher,
    targets: Dict[str, str],
) -> Tuple[float, int, float, Dict[str, Any]]:
    """执行目标批量探测并返回成功率、延迟、空值率与明细。"""
    latencies: List[float] = []
    rows: List[Dict[str, Any]] = []
    success = 0
    total = len(targets)

    for field, target in targets.items():
        started = time.perf_counter()
        value = fetcher(target)
        duration = time.perf_counter() - started
        latencies.append(duration)
        ok = value is not None
        if ok:
            success += 1
        rows.append(
            {
                "field": field,
                "target": target,
                "ok": ok,
                "value": value,
                "latency_ms": int(round(duration * 1000)),
            }
        )

    success_rate = success / total if total > 0 else 0.0
    null_rate = 1.0 - success_rate
    p95_latency_ms = _p95_latency_ms(latencies)
    return success_rate, p95_latency_ms, null_rate, {"rows": rows}


def _collect_articles_health(supabase, hours: int, run_id: str) -> Dict[str, Any]:
    now = _now_utc()
    cutoff_iso = (now - timedelta(hours=hours)).isoformat()
    result = (
        supabase.table("articles")
        .select("id,fetched_at", count="exact")
        .gte("fetched_at", cutoff_iso)
        .order("fetched_at", desc=True)
        .limit(1)
        .execute()
    )
    latest_row = (result.data or [None])[0]
    latest_fetched = ""
    freshness_sec = 999999
    if latest_row and latest_row.get("fetched_at"):
        latest_fetched = str(latest_row.get("fetched_at"))
        try:
            fetched_dt = datetime.fromisoformat(latest_fetched.replace("Z", "+00:00"))
            freshness_sec = max(0, int((now - fetched_dt).total_seconds()))
        except Exception:
            freshness_sec = 999999

    count_24h = int(result.count or 0)
    success_rate = 1.0 if count_24h > 0 else 0.0
    null_rate = 0.0 if count_24h > 0 else 1.0
    status = _build_status("news", success_rate, freshness_sec, null_rate)

    return {
        "source_id": "articles_ingest",
        "health_date": now.date().isoformat(),
        "success_rate": round(success_rate, 4),
        "p95_latency_ms": 0,
        "freshness_sec": freshness_sec,
        "null_rate": round(null_rate, 4),
        "error_rate": round(1 - success_rate, 4),
        "status": status,
        "notes": f"window_hours={hours}, count={count_24h}",
        "source_payload": {
            "count": count_24h,
            "latest_fetched_at": latest_fetched,
            "window_hours": hours,
        },
        "run_id": run_id,
        "as_of": now.isoformat(),
    }


def _collect_stooq_health(run_id: str) -> Dict[str, Any]:
    now = _now_utc()
    success_rate, p95_latency_ms, null_rate, payload = _measure_market_source(
        fetcher=_fetch_stooq_close,
        targets=STOOQ_SYMBOLS,
    )
    freshness_sec = 0 if success_rate > 0 else 172800
    status = _build_status("market_price", success_rate, freshness_sec, null_rate)
    return {
        "source_id": "stooq_market_price",
        "health_date": now.date().isoformat(),
        "success_rate": round(success_rate, 4),
        "p95_latency_ms": p95_latency_ms,
        "freshness_sec": freshness_sec,
        "null_rate": round(null_rate, 4),
        "error_rate": round(1 - success_rate, 4),
        "status": status,
        "notes": f"targets={len(STOOQ_SYMBOLS)}",
        "source_payload": payload,
        "run_id": run_id,
        "as_of": now.isoformat(),
    }


def _collect_fred_health(run_id: str) -> Dict[str, Any]:
    now = _now_utc()
    success_rate, p95_latency_ms, null_rate, payload = _measure_market_source(
        fetcher=_fetch_fred_latest,
        targets=FRED_SERIES,
    )
    freshness_sec = 0 if success_rate > 0 else 259200
    status = _build_status("macro", success_rate, freshness_sec, null_rate)
    return {
        "source_id": "fred_macro_series",
        "health_date": now.date().isoformat(),
        "success_rate": round(success_rate, 4),
        "p95_latency_ms": p95_latency_ms,
        "freshness_sec": freshness_sec,
        "null_rate": round(null_rate, 4),
        "error_rate": round(1 - success_rate, 4),
        "status": status,
        "notes": f"targets={len(FRED_SERIES)}",
        "source_payload": payload,
        "run_id": run_id,
        "as_of": now.isoformat(),
    }


def _upsert_health_rows(supabase, rows: List[Dict[str, Any]]) -> None:
    supabase.table("source_health_daily").upsert(
        rows,
        on_conflict="source_id,health_date",
    ).execute()


def _sync_incident(supabase, row: Dict[str, Any]) -> None:
    source_id = str(row.get("source_id") or "")
    status = str(row.get("status") or "healthy")
    now_iso = _now_utc().isoformat()
    incident_type = "health_status"

    if status == "healthy":
        (
            supabase.table("source_health_incidents")
            .update({"is_active": False, "last_seen": now_iso, "updated_at": now_iso})
            .eq("source_id", source_id)
            .eq("incident_type", incident_type)
            .eq("is_active", True)
            .execute()
        )
        return

    severity = "critical" if status == "critical" else "warning"
    active_row = (
        supabase.table("source_health_incidents")
        .select("id")
        .eq("source_id", source_id)
        .eq("incident_type", incident_type)
        .eq("is_active", True)
        .order("last_seen", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )

    if active_row:
        incident_id = int(active_row[0].get("id") or 0)
        if incident_id > 0:
            (
                supabase.table("source_health_incidents")
                .update(
                    {
                        "severity": severity,
                        "message": f"{source_id} status={status}",
                        "context": row.get("source_payload") or {},
                        "last_seen": now_iso,
                        "run_id": row.get("run_id") or "",
                    }
                )
                .eq("id", incident_id)
                .execute()
            )
            return

    supabase.table("source_health_incidents").insert(
        {
            "source_id": source_id,
            "incident_type": incident_type,
            "severity": severity,
            "message": f"{source_id} status={status}",
            "context": row.get("source_payload") or {},
            "first_seen": now_iso,
            "last_seen": now_iso,
            "is_active": True,
            "run_id": row.get("run_id") or "",
        }
    ).execute()


def collect_source_health(
    run_id: Optional[str] = None,
    hours: int = 24,
) -> Dict[str, Any]:
    """采集并写入 source health 日快照。"""
    supabase = _init_supabase()
    final_run_id = run_id or f"health-{_now_utc().strftime('%Y%m%d%H%M%S')}"
    rows = [
        _collect_articles_health(supabase=supabase, hours=hours, run_id=final_run_id),
        _collect_stooq_health(run_id=final_run_id),
        _collect_fred_health(run_id=final_run_id),
    ]
    _upsert_health_rows(supabase, rows)
    for row in rows:
        _sync_incident(supabase, row)

    degraded = sum(1 for row in rows if str(row.get("status")) == "degraded")
    critical = sum(1 for row in rows if str(row.get("status")) == "critical")
    healthy = sum(1 for row in rows if str(row.get("status")) == "healthy")
    logger.info(
        f"[SOURCE_HEALTH_DONE] run_id={final_run_id} healthy={healthy} "
        f"degraded={degraded} critical={critical}"
    )
    return {
        "run_id": final_run_id,
        "healthy": healthy,
        "degraded": degraded,
        "critical": critical,
        "total": len(rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock V3 source health collector")
    parser.add_argument("--run-id", type=str, default=None, help="关联 run_id")
    parser.add_argument("--hours", type=int, default=24, help="articles 窗口小时")
    args = parser.parse_args()

    metrics = collect_source_health(run_id=args.run_id, hours=max(1, args.hours))
    parts = [f"{key}={value}" for key, value in metrics.items()]
    logger.info(
        "[SOURCE_HEALTH_METRICS] "
        + ", ".join(parts)
    )


if __name__ == "__main__":
    main()
