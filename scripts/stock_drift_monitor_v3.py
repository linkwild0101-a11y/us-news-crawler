#!/usr/bin/env python3
"""Stock V3 漂移监控脚本（机会分布）。"""

from __future__ import annotations

import argparse
import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

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

DRIFT_THRESHOLDS = {
    "long_ratio": (0.18, 0.30),
    "horizon_a_ratio": (0.18, 0.30),
    "high_risk_ratio": (0.20, 0.35),
    "top1_ticker_share": (0.15, 0.25),
    "avg_confidence": (0.08, 0.16),
    "median_score": (8.0, 15.0),
}


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


def _load_window_rows(
    supabase,
    start_iso: str,
    end_iso: str,
    limit: int,
) -> List[Dict[str, Any]]:
    rows = (
        supabase.table("stock_opportunities_v2")
        .select("id,ticker,side,horizon,risk_level,opportunity_score,confidence,as_of")
        .gte("as_of", start_iso)
        .lte("as_of", end_iso)
        .order("as_of", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    return rows


def _median(values: List[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    center = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[center]
    return (ordered[center - 1] + ordered[center]) / 2.0


def _build_distribution(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    total = len(rows)
    if total <= 0:
        return {
            "sample_total": 0.0,
            "long_ratio": 0.0,
            "horizon_a_ratio": 0.0,
            "high_risk_ratio": 0.0,
            "top1_ticker_share": 0.0,
            "avg_confidence": 0.0,
            "median_score": 0.0,
        }

    long_count = sum(1 for row in rows if str(row.get("side") or "").upper() == "LONG")
    horizon_a_count = sum(1 for row in rows if str(row.get("horizon") or "").upper() == "A")
    high_risk_count = sum(
        1 for row in rows if str(row.get("risk_level") or "").upper() in ("L3", "L4")
    )
    ticker_counter = Counter(str(row.get("ticker") or "").upper() for row in rows if row.get("ticker"))
    top1_share = ticker_counter.most_common(1)[0][1] / total if ticker_counter else 0.0
    confidence_values = [_safe_float(row.get("confidence"), 0.0) for row in rows]
    score_values = [_safe_float(row.get("opportunity_score"), 0.0) for row in rows]

    return {
        "sample_total": float(total),
        "long_ratio": round(long_count / total, 6),
        "horizon_a_ratio": round(horizon_a_count / total, 6),
        "high_risk_ratio": round(high_risk_count / total, 6),
        "top1_ticker_share": round(top1_share, 6),
        "avg_confidence": round(sum(confidence_values) / total, 6),
        "median_score": round(_median(score_values), 6),
    }


def _compare_distributions(
    current: Dict[str, float],
    baseline: Dict[str, float],
    run_id: str,
    window_hours: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, float], str]:
    rows: List[Dict[str, Any]] = []
    warn_count = 0
    critical_count = 0
    max_drift = 0.0

    for metric_name, thresholds in DRIFT_THRESHOLDS.items():
        warn_threshold, critical_threshold = thresholds
        current_value = _safe_float(current.get(metric_name), 0.0)
        baseline_value = _safe_float(baseline.get(metric_name), 0.0)
        drift_value = abs(current_value - baseline_value)
        max_drift = max(max_drift, drift_value)

        status = "normal"
        if drift_value >= critical_threshold:
            status = "critical"
            critical_count += 1
        elif drift_value >= warn_threshold:
            status = "warn"
            warn_count += 1

        rows.append(
            {
                "run_id": run_id,
                "snapshot_date": _now_utc().date().isoformat(),
                "window_hours": window_hours,
                "metric_name": metric_name,
                "baseline_value": round(baseline_value, 6),
                "current_value": round(current_value, 6),
                "drift_value": round(drift_value, 6),
                "threshold_warn": warn_threshold,
                "threshold_critical": critical_threshold,
                "status": status,
                "details": {
                    "current_sample_total": int(_safe_float(current.get("sample_total"), 0.0)),
                    "baseline_sample_total": int(_safe_float(baseline.get("sample_total"), 0.0)),
                },
                "as_of": _now_utc().isoformat(),
            }
        )

    overall = "normal"
    if critical_count > 0:
        overall = "critical"
    elif warn_count > 0:
        overall = "warn"

    metrics = {
        "drift_metric_total": float(len(rows)),
        "drift_warn_count": float(warn_count),
        "drift_critical_count": float(critical_count),
        "drift_max_abs": round(max_drift, 6),
    }
    return rows, metrics, overall


def _sync_drift_incident(supabase, run_id: str, overall_status: str, rows: List[Dict[str, Any]]) -> None:
    source_id = "stock_signal_distribution"
    incident_type = "signal_drift"
    now_iso = _now_utc().isoformat()

    if overall_status == "normal":
        (
            supabase.table("source_health_incidents")
            .update({"is_active": False, "last_seen": now_iso, "updated_at": now_iso})
            .eq("source_id", source_id)
            .eq("incident_type", incident_type)
            .eq("is_active", True)
            .execute()
        )
        return

    severity = "critical" if overall_status == "critical" else "warning"
    top_rows = sorted(rows, key=lambda item: float(item.get("drift_value") or 0.0), reverse=True)[:3]
    context = {
        "overall_status": overall_status,
        "top_metrics": [
            {
                "metric": item.get("metric_name"),
                "drift": item.get("drift_value"),
                "status": item.get("status"),
            }
            for item in top_rows
        ],
    }

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
                        "message": f"stock drift status={overall_status}",
                        "context": context,
                        "last_seen": now_iso,
                        "run_id": run_id,
                        "updated_at": now_iso,
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
            "message": f"stock drift status={overall_status}",
            "context": context,
            "first_seen": now_iso,
            "last_seen": now_iso,
            "is_active": True,
            "run_id": run_id,
        }
    ).execute()


def _log_run_start(
    supabase,
    run_id: str,
    window_hours: int,
    baseline_days: int,
    limit: int,
) -> None:
    payload = {
        "run_id": run_id,
        "pipeline_name": "stock_v3_drift_monitor",
        "pipeline_version": os.getenv("GITHUB_SHA", "")[:12] or "local",
        "trigger_type": os.getenv("GITHUB_EVENT_NAME", "manual"),
        "status": "running",
        "started_at": _now_utc().isoformat(),
        "input_window": {
            "window_hours": window_hours,
            "baseline_days": baseline_days,
            "limit": limit,
        },
        "params_json": {
            "window_hours": window_hours,
            "baseline_days": baseline_days,
            "limit": limit,
        },
        "commit_sha": os.getenv("GITHUB_SHA", "")[:40],
        "as_of": _now_utc().isoformat(),
    }
    try:
        supabase.table("research_runs").upsert(payload, on_conflict="run_id").execute()
    except Exception as e:
        logger.warning(f"[DRIFT_V3_RUN_START_FAILED] error={str(e)[:120]}")


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
        logger.warning(f"[DRIFT_V3_RUN_FINISH_FAILED] error={str(e)[:120]}")


def _upsert_drift_rows(supabase, rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    supabase.table("signal_drift_snapshots").upsert(
        rows,
        on_conflict="run_id,metric_name",
    ).execute()
    return len(rows)


def _upsert_run_metrics(supabase, run_id: str, metrics: Dict[str, float]) -> int:
    rows = [
        {
            "run_id": run_id,
            "metric_name": key,
            "metric_value": float(value),
            "metric_unit": "ratio" if "rate" in key else "count",
        }
        for key, value in metrics.items()
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
        logger.warning(f"[DRIFT_V3_METRICS_UPSERT_FAILED] error={str(e)[:120]}")
        return 0


def run_drift_monitor(
    run_id: Optional[str],
    window_hours: int,
    baseline_days: int,
    limit: int,
) -> Dict[str, Any]:
    supabase = _init_supabase()
    final_run_id = run_id or f"drift-{_now_utc().strftime('%Y%m%d%H%M%S')}"
    _log_run_start(
        supabase=supabase,
        run_id=final_run_id,
        window_hours=window_hours,
        baseline_days=baseline_days,
        limit=limit,
    )

    now = _now_utc()
    current_start = now - timedelta(hours=window_hours)
    baseline_end = current_start
    baseline_start = baseline_end - timedelta(days=baseline_days)

    try:
        current_rows = _load_window_rows(
            supabase=supabase,
            start_iso=current_start.isoformat(),
            end_iso=now.isoformat(),
            limit=limit,
        )
        baseline_rows = _load_window_rows(
            supabase=supabase,
            start_iso=baseline_start.isoformat(),
            end_iso=baseline_end.isoformat(),
            limit=limit * 3,
        )
        current_dist = _build_distribution(current_rows)
        baseline_dist = _build_distribution(baseline_rows)
        drift_rows, metrics, overall = _compare_distributions(
            current=current_dist,
            baseline=baseline_dist,
            run_id=final_run_id,
            window_hours=window_hours,
        )

        upserted = _upsert_drift_rows(supabase=supabase, rows=drift_rows)
        _sync_drift_incident(
            supabase=supabase,
            run_id=final_run_id,
            overall_status=overall,
            rows=drift_rows,
        )
        _upsert_run_metrics(supabase=supabase, run_id=final_run_id, metrics=metrics)

        summary = {
            "run_id": final_run_id,
            "current_rows": len(current_rows),
            "baseline_rows": len(baseline_rows),
            "drift_rows_upserted": upserted,
            "overall_status": overall,
            **metrics,
        }
        _log_run_finish(
            supabase=supabase,
            run_id=final_run_id,
            status="degraded" if overall in ("warn", "critical") else "success",
            notes=f"overall_status={overall}, drift_rows={upserted}",
        )
        logger.info("[DRIFT_V3_DONE] " + ", ".join([f"{k}={v}" for k, v in summary.items()]))
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
    parser = argparse.ArgumentParser(description="Stock V3 drift monitor runner")
    parser.add_argument("--run-id", type=str, default=None, help="监控 run_id")
    parser.add_argument("--window-hours", type=int, default=24, help="当前窗口小时")
    parser.add_argument("--baseline-days", type=int, default=7, help="基线天数")
    parser.add_argument("--limit", type=int, default=4000, help="最大采样条数")
    args = parser.parse_args()

    summary = run_drift_monitor(
        run_id=args.run_id,
        window_hours=max(1, args.window_hours),
        baseline_days=max(1, args.baseline_days),
        limit=max(200, args.limit),
    )
    logger.info("[DRIFT_V3_METRICS] " + ", ".join([f"{k}={v}" for k, v in summary.items()]))


if __name__ == "__main__":
    main()
