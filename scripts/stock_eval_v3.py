#!/usr/bin/env python3
"""Stock V3 离线评估（代理口径）脚本。"""

from __future__ import annotations

import argparse
import logging
import os
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


def _to_iso(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return ""


def _calibration_bin(confidence: float) -> int:
    bounded = max(0.0, min(1.0, confidence))
    return int(round(bounded * 10))


def _load_active_opportunity_map(supabase) -> Dict[str, Dict[str, Any]]:
    rows = (
        supabase.table("stock_opportunities_v2")
        .select("id,ticker,side,horizon,opportunity_score,run_id,as_of")
        .eq("is_active", True)
        .order("opportunity_score", desc=True)
        .limit(500)
        .execute()
        .data
        or []
    )
    result: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        horizon = str(row.get("horizon") or "A").upper()
        if not ticker:
            continue
        key = f"{ticker}:{horizon}"
        if key not in result:
            result[key] = row
    return result


def _load_eval_candidates(
    supabase,
    window_hours: int,
    max_age_days: int,
    limit: int,
) -> List[Dict[str, Any]]:
    now = _now_utc()
    older_than = (now - timedelta(hours=window_hours)).isoformat()
    newer_than = (now - timedelta(days=max_age_days)).isoformat()

    rows = (
        supabase.table("stock_opportunities_v2")
        .select("id,ticker,side,horizon,opportunity_score,confidence,run_id,as_of")
        .lte("as_of", older_than)
        .gte("as_of", newer_than)
        .order("as_of", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    return rows


def _evaluate_rows(
    candidates: List[Dict[str, Any]],
    active_map: Dict[str, Dict[str, Any]],
    eval_run_id: str,
    window_hours: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    rows: List[Dict[str, Any]] = []
    now_iso = _now_utc().isoformat()

    total = 0
    hit = 0
    long_total = 0
    long_hit = 0
    short_total = 0
    short_hit = 0
    avg_ret_sum = 0.0

    for row in candidates:
        signal_id = int(row.get("id") or 0)
        ticker = str(row.get("ticker") or "").upper()
        side = str(row.get("side") or "LONG").upper()
        horizon = str(row.get("horizon") or "A").upper()
        if signal_id <= 0 or not ticker or side not in ("LONG", "SHORT"):
            continue

        key = f"{ticker}:{horizon}"
        current = active_map.get(key)
        old_score = _safe_float(row.get("opportunity_score"), 0.0)
        current_score = (
            _safe_float(current.get("opportunity_score"), old_score)
            if current
            else old_score
        )
        score_delta = (current_score - old_score) / 100.0
        direction_sign = 1.0 if side == "LONG" else -1.0
        realized_return = round(score_delta * direction_sign, 6)

        direction_match = bool(current and str(current.get("side") or "").upper() == side)
        hit_flag = direction_match and realized_return >= -0.05

        confidence = _safe_float(row.get("confidence"), 0.0)
        rows.append(
            {
                "signal_id": signal_id,
                "ticker": ticker,
                "side": side,
                "label_window": f"{window_hours}h_stability_proxy",
                "realized_return": realized_return,
                "hit_flag": hit_flag,
                "calibration_bin": _calibration_bin(confidence),
                "source_run_id": str(row.get("run_id") or ""),
                "eval_run_id": eval_run_id,
                "details": {
                    "current_exists": bool(current),
                    "current_side": str(current.get("side") or "") if current else "",
                    "old_score": old_score,
                    "current_score": current_score,
                    "score_delta": round(score_delta, 6),
                    "as_of": _to_iso(row.get("as_of")),
                },
                "as_of": now_iso,
            }
        )

        total += 1
        avg_ret_sum += realized_return
        if hit_flag:
            hit += 1
        if side == "LONG":
            long_total += 1
            if hit_flag:
                long_hit += 1
        elif side == "SHORT":
            short_total += 1
            if hit_flag:
                short_hit += 1

    metrics = {
        "eval_total": float(total),
        "eval_hit_rate_proxy": round(hit / total, 4) if total else 0.0,
        "eval_long_hit_rate_proxy": round(long_hit / long_total, 4) if long_total else 0.0,
        "eval_short_hit_rate_proxy": round(short_hit / short_total, 4) if short_total else 0.0,
        "eval_avg_return_proxy": round(avg_ret_sum / total, 6) if total else 0.0,
    }
    return rows, metrics


def _upsert_eval_rows(supabase, rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    supabase.table("signal_eval_snapshots").upsert(
        rows,
        on_conflict="signal_id,label_window",
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
        logger.warning(f"[EVAL_V3_METRICS_UPSERT_FAILED] error={str(e)[:120]}")
        return 0


def _log_run_start(supabase, run_id: str, window_hours: int, limit: int, max_age_days: int) -> None:
    payload = {
        "run_id": run_id,
        "pipeline_name": "stock_v3_eval_proxy",
        "pipeline_version": os.getenv("GITHUB_SHA", "")[:12] or "local",
        "trigger_type": os.getenv("GITHUB_EVENT_NAME", "manual"),
        "status": "running",
        "started_at": _now_utc().isoformat(),
        "input_window": {
            "window_hours": window_hours,
            "max_age_days": max_age_days,
            "limit": limit,
        },
        "params_json": {
            "window_hours": window_hours,
            "max_age_days": max_age_days,
            "limit": limit,
            "eval_mode": "stability_proxy",
        },
        "commit_sha": os.getenv("GITHUB_SHA", "")[:40],
        "as_of": _now_utc().isoformat(),
    }
    try:
        supabase.table("research_runs").upsert(payload, on_conflict="run_id").execute()
    except Exception as e:
        logger.warning(f"[EVAL_V3_RUN_START_FAILED] error={str(e)[:120]}")


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
        logger.warning(f"[EVAL_V3_RUN_FINISH_FAILED] error={str(e)[:120]}")


def run_eval(
    run_id: Optional[str],
    window_hours: int,
    max_age_days: int,
    limit: int,
) -> Dict[str, Any]:
    supabase = _init_supabase()
    final_run_id = run_id or f"eval-{_now_utc().strftime('%Y%m%d%H%M%S')}"
    _log_run_start(
        supabase=supabase,
        run_id=final_run_id,
        window_hours=window_hours,
        limit=limit,
        max_age_days=max_age_days,
    )

    try:
        candidates = _load_eval_candidates(
            supabase=supabase,
            window_hours=window_hours,
            max_age_days=max_age_days,
            limit=limit,
        )
        active_map = _load_active_opportunity_map(supabase=supabase)
        rows, metrics = _evaluate_rows(
            candidates=candidates,
            active_map=active_map,
            eval_run_id=final_run_id,
            window_hours=window_hours,
        )
        upserted = _upsert_eval_rows(supabase=supabase, rows=rows)
        _upsert_run_metrics(supabase=supabase, run_id=final_run_id, metrics=metrics)

        summary = {
            "run_id": final_run_id,
            "candidates": len(candidates),
            "rows_upserted": upserted,
            **metrics,
        }
        _log_run_finish(
            supabase=supabase,
            run_id=final_run_id,
            status="success",
            notes=f"rows_upserted={upserted}",
        )
        logger.info("[EVAL_V3_DONE] " + ", ".join([f"{k}={v}" for k, v in summary.items()]))
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
    parser = argparse.ArgumentParser(description="Stock V3 offline eval proxy runner")
    parser.add_argument("--run-id", type=str, default=None, help="评估 run_id")
    parser.add_argument("--window-hours", type=int, default=24, help="评估窗口（小时）")
    parser.add_argument("--max-age-days", type=int, default=14, help="样本最远回看天数")
    parser.add_argument("--limit", type=int, default=2500, help="最多评估样本数")
    args = parser.parse_args()

    metrics = run_eval(
        run_id=args.run_id,
        window_hours=max(1, args.window_hours),
        max_age_days=max(1, args.max_age_days),
        limit=max(1, args.limit),
    )
    logger.info("[EVAL_V3_METRICS] " + ", ".join([f"{k}={v}" for k, v in metrics.items()]))


if __name__ == "__main__":
    main()
