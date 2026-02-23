#!/usr/bin/env python3
"""Stock V3 组合约束引擎（参数化）。"""

from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
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


@dataclass(frozen=True)
class ConstraintConfig:
    """组合约束配置。"""

    max_positions: int = 12
    max_new_positions: int = 12
    max_single_ticker: int = 1
    max_gross_exposure: float = 12.0
    max_long_ratio: float = 0.75
    max_short_ratio: float = 0.75
    min_opportunity_score: float = 70.0
    min_confidence: float = 0.55


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp(value: float, left: float, right: float) -> float:
    return max(left, min(right, value))


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


def load_active_opportunities(supabase, limit: int = 240) -> List[Dict[str, Any]]:
    """读取当前活跃机会池。"""
    rows = (
        supabase.table("stock_opportunities_v2")
        .select("id,ticker,side,horizon,opportunity_score,confidence,risk_level,as_of")
        .eq("is_active", True)
        .order("opportunity_score", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    return rows


def load_open_positions(supabase, limit: int = 500) -> List[Dict[str, Any]]:
    """读取当前纸上交易 OPEN 持仓。"""
    try:
        rows = (
            supabase.table("portfolio_paper_positions")
            .select("id,ticker,side,size,status")
            .eq("status", "OPEN")
            .order("entry_ts", desc=False)
            .limit(limit)
            .execute()
            .data
            or []
        )
    except Exception:
        rows = []
    return rows


def apply_constraints_to_opportunities(
    opportunities: List[Dict[str, Any]],
    open_positions: List[Dict[str, Any]],
    config: ConstraintConfig,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, float]]:
    """按组合约束过滤候选机会，返回 accepted/rejected 与指标。"""
    open_total = 0
    open_long = 0
    open_short = 0
    open_gross = 0.0
    ticker_open_count: Dict[str, int] = {}
    for row in open_positions:
        ticker = str(row.get("ticker") or "").upper()
        side = str(row.get("side") or "").upper()
        size = max(_safe_float(row.get("size"), 1.0), 0.0)
        if not ticker:
            continue
        open_total += 1
        open_gross += size
        ticker_open_count[ticker] = ticker_open_count.get(ticker, 0) + 1
        if side == "LONG":
            open_long += 1
        elif side == "SHORT":
            open_short += 1

    accepted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    accepted_long = 0
    accepted_short = 0
    accepted_gross = 0.0
    ticker_new_count: Dict[str, int] = {}

    sorted_rows = sorted(
        opportunities,
        key=lambda item: (
            -_safe_float(item.get("opportunity_score"), 0.0),
            -_safe_float(item.get("confidence"), 0.0),
        ),
    )
    for idx, row in enumerate(sorted_rows, start=1):
        ticker = str(row.get("ticker") or "").upper()
        side = str(row.get("side") or "").upper()
        score = _safe_float(row.get("opportunity_score"), 0.0)
        confidence = _safe_float(row.get("confidence"), 0.0)
        reason = ""

        if not ticker or side not in ("LONG", "SHORT"):
            reason = "invalid_row"
        elif score < config.min_opportunity_score:
            reason = "below_min_score"
        elif confidence < config.min_confidence:
            reason = "below_min_confidence"
        elif len(accepted) >= config.max_new_positions:
            reason = "max_new_positions"
        else:
            current_total = open_total + len(accepted)
            after_total = current_total + 1
            if after_total > config.max_positions:
                reason = "max_positions"

            ticker_after = (
                ticker_open_count.get(ticker, 0)
                + ticker_new_count.get(ticker, 0)
                + 1
            )
            if not reason and ticker_after > config.max_single_ticker:
                reason = "max_single_ticker"

            side_long_after = open_long + accepted_long + (1 if side == "LONG" else 0)
            side_short_after = open_short + accepted_short + (1 if side == "SHORT" else 0)
            long_ratio_after = side_long_after / max(1, after_total)
            short_ratio_after = side_short_after / max(1, after_total)
            if not reason and long_ratio_after > _clamp(config.max_long_ratio, 0.0, 1.0):
                reason = "max_long_ratio"
            if not reason and short_ratio_after > _clamp(config.max_short_ratio, 0.0, 1.0):
                reason = "max_short_ratio"

            gross_after = open_gross + accepted_gross + 1.0
            if not reason and gross_after > max(0.0, config.max_gross_exposure):
                reason = "max_gross_exposure"

        payload = {
            "rank": idx,
            "opportunity_id": int(row.get("id") or 0),
            "ticker": ticker,
            "side": side if side in ("LONG", "SHORT") else "LONG",
            "horizon": str(row.get("horizon") or "A").upper(),
            "opportunity_score": round(score, 4),
            "confidence": round(confidence, 6),
            "risk_level": str(row.get("risk_level") or "L1").upper(),
            "as_of": str(row.get("as_of") or ""),
            "decision_reason": reason or "accepted",
        }

        if reason:
            rejected.append(payload)
            continue

        accepted.append(payload)
        ticker_new_count[ticker] = ticker_new_count.get(ticker, 0) + 1
        accepted_gross += 1.0
        if side == "LONG":
            accepted_long += 1
        else:
            accepted_short += 1

    total = len(accepted) + len(rejected)
    metrics = {
        "constraint_candidates_total": float(total),
        "constraint_accepted_count": float(len(accepted)),
        "constraint_rejected_count": float(len(rejected)),
        "constraint_accept_rate": round(len(accepted) / total, 4) if total else 0.0,
        "constraint_after_total_positions": float(open_total + len(accepted)),
        "constraint_after_gross_exposure": round(open_gross + accepted_gross, 4),
    }
    return accepted, rejected, metrics


def _upsert_snapshot_rows(
    supabase,
    run_id: str,
    accepted: List[Dict[str, Any]],
    rejected: List[Dict[str, Any]],
    config: ConstraintConfig,
) -> int:
    rows: List[Dict[str, Any]] = []
    now_iso = _now_utc().isoformat()
    for row in accepted:
        rows.append(
            {
                "run_id": run_id,
                "opportunity_id": row["opportunity_id"] or None,
                "ticker": row["ticker"],
                "side": row["side"],
                "decision": "accepted",
                "decision_reason": row["decision_reason"],
                "rank": row["rank"],
                "opportunity_score": row["opportunity_score"],
                "confidence": row["confidence"],
                "constraint_payload": {
                    "max_positions": config.max_positions,
                    "max_new_positions": config.max_new_positions,
                    "max_single_ticker": config.max_single_ticker,
                    "max_gross_exposure": config.max_gross_exposure,
                    "max_long_ratio": config.max_long_ratio,
                    "max_short_ratio": config.max_short_ratio,
                    "min_opportunity_score": config.min_opportunity_score,
                    "min_confidence": config.min_confidence,
                },
                "as_of": now_iso,
            }
        )
    for row in rejected:
        rows.append(
            {
                "run_id": run_id,
                "opportunity_id": row["opportunity_id"] or None,
                "ticker": row["ticker"],
                "side": row["side"],
                "decision": "rejected",
                "decision_reason": row["decision_reason"],
                "rank": row["rank"],
                "opportunity_score": row["opportunity_score"],
                "confidence": row["confidence"],
                "constraint_payload": {
                    "max_positions": config.max_positions,
                    "max_new_positions": config.max_new_positions,
                    "max_single_ticker": config.max_single_ticker,
                    "max_gross_exposure": config.max_gross_exposure,
                    "max_long_ratio": config.max_long_ratio,
                    "max_short_ratio": config.max_short_ratio,
                    "min_opportunity_score": config.min_opportunity_score,
                    "min_confidence": config.min_confidence,
                },
                "as_of": now_iso,
            }
        )
    if not rows:
        return 0
    try:
        supabase.table("portfolio_constraint_snapshots").insert(rows).execute()
        return len(rows)
    except Exception as e:
        logger.warning(f"[CONSTRAINT_V3_SNAPSHOT_WRITE_FAILED] error={str(e)[:120]}")
        return 0


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
        error_text = str(e)
        if "research_run_metrics_run_id_fkey" in error_text:
            _ensure_run_row(
                supabase=supabase,
                run_id=run_id,
                pipeline_name="stock_v3_portfolio_constraints",
            )
            try:
                supabase.table("research_run_metrics").upsert(
                    rows,
                    on_conflict="run_id,metric_name",
                ).execute()
                return len(rows)
            except Exception as inner:
                logger.warning(f"[CONSTRAINT_V3_METRICS_RETRY_FAILED] error={str(inner)[:120]}")
                return 0
        logger.warning(f"[CONSTRAINT_V3_METRICS_UPSERT_FAILED] error={error_text[:120]}")
        return 0


def _ensure_run_row(supabase, run_id: str, pipeline_name: str) -> None:
    payload = {
        "run_id": run_id,
        "pipeline_name": pipeline_name,
        "pipeline_version": os.getenv("GITHUB_SHA", "")[:12] or "local",
        "trigger_type": os.getenv("GITHUB_EVENT_NAME", "manual"),
        "status": "running",
        "started_at": _now_utc().isoformat(),
        "input_window": {},
        "params_json": {},
        "commit_sha": os.getenv("GITHUB_SHA", "")[:40],
        "as_of": _now_utc().isoformat(),
    }
    try:
        supabase.table("research_runs").upsert(payload, on_conflict="run_id").execute()
    except Exception as e:
        logger.warning(f"[CONSTRAINT_V3_ENSURE_RUN_FAILED] error={str(e)[:120]}")


def _log_run_start(supabase, run_id: str, limit: int, config: ConstraintConfig) -> None:
    payload = {
        "run_id": run_id,
        "pipeline_name": "stock_v3_portfolio_constraints",
        "pipeline_version": os.getenv("GITHUB_SHA", "")[:12] or "local",
        "trigger_type": os.getenv("GITHUB_EVENT_NAME", "manual"),
        "status": "running",
        "started_at": _now_utc().isoformat(),
        "input_window": {"limit": limit},
        "params_json": {
            "limit": limit,
            "max_positions": config.max_positions,
            "max_new_positions": config.max_new_positions,
            "max_single_ticker": config.max_single_ticker,
            "max_gross_exposure": config.max_gross_exposure,
            "max_long_ratio": config.max_long_ratio,
            "max_short_ratio": config.max_short_ratio,
            "min_opportunity_score": config.min_opportunity_score,
            "min_confidence": config.min_confidence,
        },
        "commit_sha": os.getenv("GITHUB_SHA", "")[:40],
        "as_of": _now_utc().isoformat(),
    }
    try:
        supabase.table("research_runs").upsert(payload, on_conflict="run_id").execute()
    except Exception as e:
        logger.warning(f"[CONSTRAINT_V3_RUN_START_FAILED] error={str(e)[:120]}")


def _log_run_finish(supabase, run_id: str, status: str, notes: str) -> None:
    _ensure_run_row(supabase=supabase, run_id=run_id, pipeline_name="stock_v3_portfolio_constraints")
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
        logger.warning(f"[CONSTRAINT_V3_RUN_FINISH_FAILED] error={str(e)[:120]}")


def run_constraints(
    run_id: Optional[str],
    limit: int,
    config: ConstraintConfig,
) -> Dict[str, Any]:
    supabase = _init_supabase()
    final_run_id = run_id or f"constraint-{_now_utc().strftime('%Y%m%d%H%M%S')}"
    _log_run_start(supabase=supabase, run_id=final_run_id, limit=limit, config=config)
    try:
        opportunities = load_active_opportunities(supabase=supabase, limit=limit)
        open_positions = load_open_positions(
            supabase=supabase,
            limit=max(300, config.max_positions * 30),
        )
        accepted, rejected, metrics = apply_constraints_to_opportunities(
            opportunities=opportunities,
            open_positions=open_positions,
            config=config,
        )
        snapshot_written = _upsert_snapshot_rows(
            supabase=supabase,
            run_id=final_run_id,
            accepted=accepted,
            rejected=rejected,
            config=config,
        )
        _upsert_run_metrics(supabase=supabase, run_id=final_run_id, metrics=metrics)
        summary = {
            "run_id": final_run_id,
            "opportunities_loaded": len(opportunities),
            "accepted": len(accepted),
            "rejected": len(rejected),
            "snapshot_rows_written": snapshot_written,
            **metrics,
        }
        _log_run_finish(
            supabase=supabase,
            run_id=final_run_id,
            status="success",
            notes=f"accepted={len(accepted)}, rejected={len(rejected)}",
        )
        logger.info("[CONSTRAINT_V3_DONE] " + ", ".join([f"{k}={v}" for k, v in summary.items()]))
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
    parser = argparse.ArgumentParser(description="Stock V3 portfolio constraints runner")
    parser.add_argument("--run-id", type=str, default=None, help="run_id")
    parser.add_argument("--limit", type=int, default=220, help="候选机会读取上限")
    parser.add_argument("--max-positions", type=int, default=12, help="总持仓上限")
    parser.add_argument("--max-new-positions", type=int, default=12, help="本轮最多新开仓")
    parser.add_argument("--max-single-ticker", type=int, default=1, help="单票持仓上限")
    parser.add_argument("--max-gross-exposure", type=float, default=12.0, help="总敞口上限")
    parser.add_argument("--max-long-ratio", type=float, default=0.75, help="多头仓位比例上限")
    parser.add_argument("--max-short-ratio", type=float, default=0.75, help="空头仓位比例上限")
    parser.add_argument("--min-opportunity-score", type=float, default=70.0, help="入选最低机会分")
    parser.add_argument("--min-confidence", type=float, default=0.55, help="入选最低置信度")
    args = parser.parse_args()

    config = ConstraintConfig(
        max_positions=max(1, args.max_positions),
        max_new_positions=max(1, args.max_new_positions),
        max_single_ticker=max(1, args.max_single_ticker),
        max_gross_exposure=max(1.0, args.max_gross_exposure),
        max_long_ratio=_clamp(args.max_long_ratio, 0.0, 1.0),
        max_short_ratio=_clamp(args.max_short_ratio, 0.0, 1.0),
        min_opportunity_score=max(0.0, args.min_opportunity_score),
        min_confidence=_clamp(args.min_confidence, 0.0, 1.0),
    )
    summary = run_constraints(
        run_id=args.run_id,
        limit=max(20, args.limit),
        config=config,
    )
    logger.info("[CONSTRAINT_V3_METRICS] " + ", ".join([f"{k}={v}" for k, v in summary.items()]))


if __name__ == "__main__":
    main()
