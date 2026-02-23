#!/usr/bin/env python3
"""Stock V3 Paper Trading（旁路）脚本。"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from supabase import create_client

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.stock_portfolio_constraints_v3 import (
    ConstraintConfig,
    apply_constraints_to_opportunities,
)

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


def _fetch_stooq_price(ticker: str) -> Optional[float]:
    symbol = f"{ticker.lower()}.us"
    endpoint = f"https://stooq.com/q/l/?s={symbol}&i=d"
    try:
        response = requests.get(
            endpoint,
            timeout=12,
            headers={"User-Agent": "USMonitor/1.0 stock-paper-v3"},
        )
        response.raise_for_status()
        first_line = next((line.strip() for line in response.text.splitlines() if line.strip()), "")
        parts = [item.strip() for item in first_line.split(",")]
        if len(parts) < 7:
            return None
        close_value = parts[6]
        if close_value in ("N/D", ""):
            return None
        return round(float(close_value), 4)
    except Exception:
        return None


def _load_active_opportunities(supabase, topn: int) -> List[Dict[str, Any]]:
    rows = (
        supabase.table("stock_opportunities_v2")
        .select("id,ticker,side,horizon,opportunity_score,expires_at,as_of")
        .eq("is_active", True)
        .order("opportunity_score", desc=True)
        .limit(topn)
        .execute()
        .data
        or []
    )
    return rows


def _load_open_positions(supabase, limit: int = 300) -> List[Dict[str, Any]]:
    rows = (
        supabase.table("portfolio_paper_positions")
        .select(
            "id,position_key,ticker,side,horizon,status,entry_ts,entry_price,size,"
            "source_opportunity_id,as_of"
        )
        .eq("status", "OPEN")
        .order("entry_ts", desc=False)
        .limit(limit)
        .execute()
        .data
        or []
    )
    return rows


def _opportunity_map(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    mapping: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        horizon = str(row.get("horizon") or "A").upper()
        if not ticker:
            continue
        key = f"{ticker}:{horizon}"
        if key not in mapping:
            mapping[key] = row
    return mapping


def _update_open_positions(
    supabase,
    open_positions: List[Dict[str, Any]],
    opp_map: Dict[str, Dict[str, Any]],
) -> Dict[str, int]:
    now_iso = _now_utc().isoformat()
    closed = 0
    updated = 0

    for row in open_positions:
        position_id = int(row.get("id") or 0)
        ticker = str(row.get("ticker") or "").upper()
        side = str(row.get("side") or "LONG").upper()
        horizon = str(row.get("horizon") or "A").upper()
        if position_id <= 0 or not ticker:
            continue

        market_price = _fetch_stooq_price(ticker)
        if market_price is None:
            logger.warning(f"[PAPER_V3_PRICE_MISS] ticker={ticker}")
            continue

        entry_price = max(_safe_float(row.get("entry_price"), 0.0), 0.0001)
        size = max(_safe_float(row.get("size"), 1.0), 0.0001)
        direction = 1.0 if side == "LONG" else -1.0
        pnl = ((market_price - entry_price) / entry_price) * direction * size

        key = f"{ticker}:{horizon}"
        latest_opp = opp_map.get(key)
        latest_side = str(latest_opp.get("side") or "").upper() if latest_opp else ""

        close_reason = ""
        if latest_opp is None:
            close_reason = "opportunity_missing"
        elif latest_side and latest_side != side:
            close_reason = f"side_flip:{side}->{latest_side}"

        if close_reason:
            (
                supabase.table("portfolio_paper_positions")
                .update(
                    {
                        "status": "CLOSED",
                        "exit_ts": now_iso,
                        "exit_price": market_price,
                        "realized_pnl": round(pnl, 6),
                        "unrealized_pnl": 0,
                        "mark_price": market_price,
                        "notes": close_reason,
                        "as_of": now_iso,
                    }
                )
                .eq("id", position_id)
                .execute()
            )
            closed += 1
            continue

        (
            supabase.table("portfolio_paper_positions")
            .update(
                {
                    "mark_price": market_price,
                    "unrealized_pnl": round(pnl, 6),
                    "as_of": now_iso,
                }
            )
            .eq("id", position_id)
            .execute()
        )
        updated += 1

    return {"closed": closed, "updated": updated}


def _open_new_positions(
    supabase,
    opportunities: List[Dict[str, Any]],
    open_positions: List[Dict[str, Any]],
    run_id: str,
) -> int:
    now_iso = _now_utc().isoformat()
    existing = {
        f"{str(item.get('ticker') or '').upper()}:{str(item.get('horizon') or 'A').upper()}"
        for item in open_positions
    }

    opened = 0
    for row in opportunities:
        ticker = str(row.get("ticker") or "").upper()
        side = str(row.get("side") or "LONG").upper()
        horizon = str(row.get("horizon") or "A").upper()
        if not ticker or side not in ("LONG", "SHORT"):
            continue

        key = f"{ticker}:{horizon}"
        if key in existing:
            continue

        entry_price = _fetch_stooq_price(ticker)
        if entry_price is None:
            continue

        position_key = f"{run_id}:{ticker}:{horizon}:{side}"
        payload = {
            "position_key": position_key,
            "run_id": run_id,
            "source_opportunity_id": int(row.get("id") or 0) or None,
            "ticker": ticker,
            "side": side,
            "horizon": horizon,
            "status": "OPEN",
            "entry_ts": now_iso,
            "entry_price": entry_price,
            "entry_score": _safe_float(row.get("opportunity_score"), 0.0),
            "size": 1.0,
            "mark_price": entry_price,
            "unrealized_pnl": 0.0,
            "as_of": now_iso,
            "notes": "auto_open_topn",
        }
        supabase.table("portfolio_paper_positions").insert(payload).execute()
        existing.add(key)
        opened += 1

    return opened


def _write_metrics(supabase, run_id: str) -> Dict[str, float]:
    open_rows = (
        supabase.table("portfolio_paper_positions")
        .select("id,unrealized_pnl,size")
        .eq("status", "OPEN")
        .limit(1000)
        .execute()
        .data
        or []
    )
    closed_rows = (
        supabase.table("portfolio_paper_positions")
        .select("id,realized_pnl")
        .eq("status", "CLOSED")
        .order("exit_ts", desc=True)
        .limit(1000)
        .execute()
        .data
        or []
    )

    open_count = len(open_rows)
    closed_count = len(closed_rows)
    unrealized = round(sum(_safe_float(row.get("unrealized_pnl"), 0.0) for row in open_rows), 6)
    realized = round(sum(_safe_float(row.get("realized_pnl"), 0.0) for row in closed_rows), 6)
    wins = sum(1 for row in closed_rows if _safe_float(row.get("realized_pnl"), 0.0) > 0)
    win_rate = round(wins / closed_count, 4) if closed_count else 0.0
    gross_exposure = round(sum(max(_safe_float(row.get("size"), 0.0), 0.0) for row in open_rows), 6)

    metrics_payload = {
        "run_id": run_id,
        "as_of": _now_utc().isoformat(),
        "open_count": open_count,
        "closed_count": closed_count,
        "realized_pnl": realized,
        "unrealized_pnl": unrealized,
        "win_rate": win_rate,
        "gross_exposure": gross_exposure,
        "notes": "paper_v3_auto",
    }
    supabase.table("portfolio_paper_metrics").insert(metrics_payload).execute()

    return {
        "open_count": float(open_count),
        "closed_count": float(closed_count),
        "realized_pnl": realized,
        "unrealized_pnl": unrealized,
        "win_rate": win_rate,
        "gross_exposure": gross_exposure,
    }


def _upsert_research_metrics(supabase, run_id: str, metrics: Dict[str, float]) -> None:
    rows = []
    for key, value in metrics.items():
        rows.append(
            {
                "run_id": run_id,
                "metric_name": f"paper_{key}",
                "metric_value": float(value),
                "metric_unit": "ratio" if "rate" in key else "count",
            }
        )
    if not rows:
        return
    try:
        supabase.table("research_run_metrics").upsert(
            rows,
            on_conflict="run_id,metric_name",
        ).execute()
    except Exception as e:
        error_text = str(e)
        if "research_run_metrics_run_id_fkey" in error_text:
            _ensure_run_row(supabase=supabase, run_id=run_id, pipeline_name="stock_v3_paper_trading")
            try:
                supabase.table("research_run_metrics").upsert(
                    rows,
                    on_conflict="run_id,metric_name",
                ).execute()
                return
            except Exception as inner:
                logger.warning(f"[PAPER_V3_METRICS_RETRY_FAILED] error={str(inner)[:120]}")
                return
        logger.warning(f"[PAPER_V3_METRICS_UPSERT_FAILED] error={error_text[:120]}")


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
        logger.warning(f"[PAPER_V3_ENSURE_RUN_FAILED] error={str(e)[:120]}")


def _log_run_start(
    supabase,
    run_id: str,
    topn: int,
    apply_constraints: bool,
    constraint_config: ConstraintConfig,
) -> None:
    payload = {
        "run_id": run_id,
        "pipeline_name": "stock_v3_paper_trading",
        "pipeline_version": os.getenv("GITHUB_SHA", "")[:12] or "local",
        "trigger_type": os.getenv("GITHUB_EVENT_NAME", "manual"),
        "status": "running",
        "started_at": _now_utc().isoformat(),
        "input_window": {"topn": topn},
        "params_json": {
            "topn": topn,
            "apply_constraints": bool(apply_constraints),
            "max_positions": constraint_config.max_positions,
            "max_new_positions": constraint_config.max_new_positions,
            "max_single_ticker": constraint_config.max_single_ticker,
            "max_gross_exposure": constraint_config.max_gross_exposure,
            "max_long_ratio": constraint_config.max_long_ratio,
            "max_short_ratio": constraint_config.max_short_ratio,
            "min_opportunity_score": constraint_config.min_opportunity_score,
            "min_confidence": constraint_config.min_confidence,
        },
        "commit_sha": os.getenv("GITHUB_SHA", "")[:40],
        "as_of": _now_utc().isoformat(),
    }
    try:
        supabase.table("research_runs").upsert(payload, on_conflict="run_id").execute()
    except Exception as e:
        logger.warning(f"[PAPER_V3_RUN_START_FAILED] error={str(e)[:120]}")


def _log_run_finish(supabase, run_id: str, status: str, notes: str) -> None:
    _ensure_run_row(supabase=supabase, run_id=run_id, pipeline_name="stock_v3_paper_trading")
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
        logger.warning(f"[PAPER_V3_RUN_FINISH_FAILED] error={str(e)[:120]}")


def run_paper(
    run_id: Optional[str],
    topn: int,
    apply_constraints: bool,
    constraint_config: ConstraintConfig,
) -> Dict[str, Any]:
    supabase = _init_supabase()
    final_run_id = run_id or f"paper-{_now_utc().strftime('%Y%m%d%H%M%S')}"
    _log_run_start(
        supabase=supabase,
        run_id=final_run_id,
        topn=topn,
        apply_constraints=apply_constraints,
        constraint_config=constraint_config,
    )

    try:
        opportunities = _load_active_opportunities(supabase=supabase, topn=topn)
        opp_map = _opportunity_map(opportunities)
        open_positions = _load_open_positions(supabase=supabase)

        update_metrics = _update_open_positions(
            supabase=supabase,
            open_positions=open_positions,
            opp_map=opp_map,
        )
        refreshed_open_positions = _load_open_positions(supabase=supabase)
        filtered_opportunities = opportunities
        refreshed_open_exposure = sum(
            max(_safe_float(row.get("size"), 1.0), 0.0) for row in refreshed_open_positions
        )
        constraint_metrics: Dict[str, float] = {
            "constraint_accepted_count": float(len(opportunities)),
            "constraint_rejected_count": 0.0,
            "constraint_accept_rate": 1.0 if opportunities else 0.0,
            "constraint_after_total_positions": float(len(refreshed_open_positions) + len(opportunities)),
            "constraint_after_gross_exposure": float(refreshed_open_exposure + len(opportunities)),
        }
        if apply_constraints:
            accepted, rejected, metrics = apply_constraints_to_opportunities(
                opportunities=opportunities,
                open_positions=refreshed_open_positions,
                config=constraint_config,
            )
            accepted_id_set = {
                int(item.get("opportunity_id") or 0)
                for item in accepted
                if int(item.get("opportunity_id") or 0) > 0
            }
            filtered_opportunities = []
            for row in opportunities:
                row_id = int(row.get("id") or 0)
                if row_id > 0 and row_id in accepted_id_set:
                    filtered_opportunities.append(row)
            constraint_metrics = {
                "constraint_accepted_count": float(len(filtered_opportunities)),
                "constraint_rejected_count": float(len(rejected)),
                "constraint_accept_rate": float(metrics.get("constraint_accept_rate", 0.0)),
                "constraint_after_total_positions": float(
                    metrics.get("constraint_after_total_positions", 0.0)
                ),
                "constraint_after_gross_exposure": float(
                    metrics.get("constraint_after_gross_exposure", 0.0)
                ),
            }

        opened = _open_new_positions(
            supabase=supabase,
            opportunities=filtered_opportunities,
            open_positions=refreshed_open_positions,
            run_id=final_run_id,
        )

        metrics = _write_metrics(supabase=supabase, run_id=final_run_id)
        merged_metrics = {**metrics, **constraint_metrics}
        _upsert_research_metrics(supabase=supabase, run_id=final_run_id, metrics=merged_metrics)

        summary = {
            "run_id": final_run_id,
            "topn": topn,
            "candidates": len(opportunities),
            "constraint_candidates": len(filtered_opportunities),
            "opened": opened,
            "updated": update_metrics.get("updated", 0),
            "closed": update_metrics.get("closed", 0),
            **merged_metrics,
        }
        _log_run_finish(
            supabase=supabase,
            run_id=final_run_id,
            status="success",
            notes=f"opened={opened}, updated={update_metrics.get('updated', 0)}",
        )
        logger.info("[PAPER_V3_DONE] " + ", ".join([f"{k}={v}" for k, v in summary.items()]))
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
    parser = argparse.ArgumentParser(description="Stock V3 paper trading runner")
    parser.add_argument("--run-id", type=str, default=None, help="paper run_id")
    parser.add_argument("--topn", type=int, default=12, help="每轮最多处理机会数")
    parser.add_argument("--apply-constraints", action="store_true", help="启用组合约束引擎")
    parser.add_argument("--max-positions", type=int, default=12, help="组合总持仓上限")
    parser.add_argument("--max-new-positions", type=int, default=12, help="本轮最多新增仓位")
    parser.add_argument("--max-single-ticker", type=int, default=1, help="单票仓位上限")
    parser.add_argument("--max-gross-exposure", type=float, default=12.0, help="总敞口上限")
    parser.add_argument("--max-long-ratio", type=float, default=0.75, help="多头比例上限")
    parser.add_argument("--max-short-ratio", type=float, default=0.75, help="空头比例上限")
    parser.add_argument("--min-opportunity-score", type=float, default=70.0, help="最低机会分")
    parser.add_argument("--min-confidence", type=float, default=0.55, help="最低置信度")
    args = parser.parse_args()

    constraint_config = ConstraintConfig(
        max_positions=max(1, args.max_positions),
        max_new_positions=max(1, args.max_new_positions),
        max_single_ticker=max(1, args.max_single_ticker),
        max_gross_exposure=max(1.0, args.max_gross_exposure),
        max_long_ratio=max(0.0, min(1.0, args.max_long_ratio)),
        max_short_ratio=max(0.0, min(1.0, args.max_short_ratio)),
        min_opportunity_score=max(0.0, args.min_opportunity_score),
        min_confidence=max(0.0, min(1.0, args.min_confidence)),
    )
    summary = run_paper(
        run_id=args.run_id,
        topn=max(1, args.topn),
        apply_constraints=bool(args.apply_constraints),
        constraint_config=constraint_config,
    )
    logger.info("[PAPER_V3_METRICS] " + ", ".join([f"{k}={v}" for k, v in summary.items()]))


if __name__ == "__main__":
    main()
