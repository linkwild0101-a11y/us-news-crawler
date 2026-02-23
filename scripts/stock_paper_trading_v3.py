#!/usr/bin/env python3
"""Stock V3 Paper Trading（旁路）脚本。"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
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
        logger.warning(f"[PAPER_V3_METRICS_UPSERT_FAILED] error={str(e)[:120]}")


def run_paper(
    run_id: Optional[str],
    topn: int,
) -> Dict[str, Any]:
    supabase = _init_supabase()
    final_run_id = run_id or f"paper-{_now_utc().strftime('%Y%m%d%H%M%S')}"

    opportunities = _load_active_opportunities(supabase=supabase, topn=topn)
    opp_map = _opportunity_map(opportunities)
    open_positions = _load_open_positions(supabase=supabase)

    update_metrics = _update_open_positions(
        supabase=supabase,
        open_positions=open_positions,
        opp_map=opp_map,
    )

    refreshed_open_positions = _load_open_positions(supabase=supabase)
    opened = _open_new_positions(
        supabase=supabase,
        opportunities=opportunities,
        open_positions=refreshed_open_positions,
        run_id=final_run_id,
    )

    metrics = _write_metrics(supabase=supabase, run_id=final_run_id)
    _upsert_research_metrics(supabase=supabase, run_id=final_run_id, metrics=metrics)

    summary = {
        "run_id": final_run_id,
        "topn": topn,
        "candidates": len(opportunities),
        "opened": opened,
        "updated": update_metrics.get("updated", 0),
        "closed": update_metrics.get("closed", 0),
        **metrics,
    }
    logger.info("[PAPER_V3_DONE] " + ", ".join([f"{k}={v}" for k, v in summary.items()]))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock V3 paper trading runner")
    parser.add_argument("--run-id", type=str, default=None, help="paper run_id")
    parser.add_argument("--topn", type=int, default=12, help="每轮最多处理机会数")
    args = parser.parse_args()

    summary = run_paper(
        run_id=args.run_id,
        topn=max(1, args.topn),
    )
    logger.info("[PAPER_V3_METRICS] " + ", ".join([f"{k}={v}" for k, v in summary.items()]))


if __name__ == "__main__":
    main()
