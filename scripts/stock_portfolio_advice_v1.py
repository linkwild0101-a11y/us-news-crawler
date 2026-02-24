#!/usr/bin/env python3
"""StockOps P1 持仓建议生成脚本。"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
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


def _clamp(value: float, left: float, right: float) -> float:
    return max(left, min(right, value))


def _to_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _init_supabase():
    """初始化 Supabase 客户端。"""
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


def _load_active_portfolios(supabase, limit: int) -> List[Dict[str, Any]]:
    rows = (
        supabase.table("stock_portfolios_v1")
        .select(
            "id,user_id,portfolio_key,display_name,risk_profile,"
            "max_position_weight,max_single_name_risk"
        )
        .eq("is_active", True)
        .order("updated_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    return rows


def _load_holdings(supabase, portfolio_ids: List[int], limit: int) -> List[Dict[str, Any]]:
    if not portfolio_ids:
        return []

    rows = (
        supabase.table("stock_portfolio_holdings_v1")
        .select(
            "id,portfolio_id,user_id,ticker,side,quantity,avg_cost,market_value,"
            "weight,tags,notes"
        )
        .in_("portfolio_id", portfolio_ids[:500])
        .eq("is_active", True)
        .order("weight", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    return rows


def _load_opportunities(supabase, lookback_hours: int, limit: int) -> Dict[str, Dict[str, Any]]:
    cutoff = (_now_utc() - timedelta(hours=lookback_hours)).isoformat()
    rows = (
        supabase.table("stock_opportunities_v2")
        .select(
            "id,ticker,side,horizon,risk_level,opportunity_score,confidence,catalysts,"
            "source_signal_ids,source_event_ids,why_now,invalid_if,as_of"
        )
        .eq("is_active", True)
        .gte("as_of", cutoff)
        .order("opportunity_score", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )

    by_ticker: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        best = by_ticker.get(ticker)
        if not best:
            by_ticker[ticker] = row
            continue
        if _safe_float(row.get("opportunity_score")) > _safe_float(
            best.get("opportunity_score")
        ):
            by_ticker[ticker] = row
    return by_ticker


def _build_trigger_points(holding: Dict[str, Any], opp: Optional[Dict[str, Any]]) -> List[str]:
    """生成建议依据，保证 2~3 条可解释信息。"""
    points: List[str] = []
    ticker = str(holding.get("ticker") or "").upper()
    weight = _safe_float(holding.get("weight"), 0.0)
    side = str(holding.get("side") or "LONG").upper()

    points.append(f"当前持仓 {ticker} {side}，权重 {weight:.2%}。")

    if opp:
        score = _safe_float(opp.get("opportunity_score"), 0.0)
        conf = _safe_float(opp.get("confidence"), 0.0)
        opp_side = str(opp.get("side") or "LONG").upper()
        horizon = str(opp.get("horizon") or "B").upper()
        risk_level = str(opp.get("risk_level") or "L2").upper()
        points.append(
            f"最新机会分数 {score:.1f}/100，置信度 {conf:.2f}，方向 {opp_side}，周期 {horizon}，风险 {risk_level}。"
        )
        catalysts = _to_str_list(opp.get("catalysts"))
        if catalysts:
            snippet = "；".join(catalysts[:2])
            points.append(f"核心催化：{snippet}。")
        else:
            summary = str(opp.get("why_now") or "")
            if summary:
                points.append(f"摘要线索：{summary[:80]}。")
    else:
        points.append("近 72 小时未命中高质量机会，建议以仓位风控与观察为主。")

    return points[:3]


def _decide_advice(
    holding: Dict[str, Any],
    opp: Optional[Dict[str, Any]],
    min_score: float,
    default_valid_hours: int,
) -> Dict[str, Any]:
    user_id = str(holding.get("user_id") or "system")[:64]
    ticker = str(holding.get("ticker") or "").upper()
    holding_side = str(holding.get("side") or "LONG").upper()
    portfolio_id = _safe_int(holding.get("portfolio_id"), 0)
    if not ticker or portfolio_id <= 0:
        raise ValueError("holding 缺少 portfolio_id 或 ticker")

    advice_type = "hold"
    action_side = "NEUTRAL"
    priority_score = 35.0
    confidence = 0.40
    risk_level = "L2"
    invalid_if = "若后续无新增催化且仓位风险抬升，建议重新评估。"
    opportunity_id: Optional[int] = None
    source_signal_ids: List[str] = []
    source_event_ids: List[str] = []

    if opp:
        opportunity_id = _safe_int(opp.get("id"), 0) or None
        opp_score = _safe_float(opp.get("opportunity_score"), 0.0)
        opp_conf = _clamp(_safe_float(opp.get("confidence"), 0.0), 0.0, 1.0)
        opp_side = str(opp.get("side") or "LONG").upper()
        risk_level = str(opp.get("risk_level") or "L2").upper()
        source_signal_ids = _to_str_list(opp.get("source_signal_ids"))
        source_event_ids = _to_str_list(opp.get("source_event_ids"))

        confidence = round(opp_conf, 4)
        priority_score = round(_clamp(opp_score * 0.7 + opp_conf * 30.0, 0.0, 100.0), 2)

        if opp_score >= min_score:
            if holding_side == "LONG" and opp_side == "LONG":
                advice_type = "add" if opp_score >= min_score + 12 else "hold"
                action_side = "LONG"
                invalid_if = f"若机会分数跌破 {max(min_score - 5, 50):.0f} 或置信度 < 0.45 则失效。"
            elif holding_side == "SHORT" and opp_side == "SHORT":
                advice_type = "add" if opp_score >= min_score + 12 else "hold"
                action_side = "SHORT"
                invalid_if = f"若机会分数跌破 {max(min_score - 5, 50):.0f} 或置信度 < 0.45 则失效。"
            elif holding_side == "LONG" and opp_side == "SHORT":
                advice_type = "reduce"
                action_side = "SHORT"
                priority_score = min(100.0, priority_score + 8.0)
                invalid_if = "若负面催化被证伪或风险级别回落至 L1/L2，可取消减仓。"
            elif holding_side == "SHORT" and opp_side == "LONG":
                advice_type = "reduce"
                action_side = "LONG"
                priority_score = min(100.0, priority_score + 8.0)
                invalid_if = "若反向催化被证伪或风险级别回落至 L1/L2，可取消减仓。"
        else:
            advice_type = "watch"
            action_side = "NEUTRAL"
            priority_score = max(25.0, priority_score - 15.0)
            invalid_if = "若 24 小时内分数未提升至阈值以上，继续观察即可。"
    else:
        advice_type = "review"
        action_side = "NEUTRAL"
        priority_score = 30.0
        confidence = 0.35
        risk_level = "L2"
        invalid_if = "若无新信号，可维持原策略并按周复盘。"

    trigger_points = _build_trigger_points(holding, opp)
    digest_source = (
        f"{user_id}:{portfolio_id}:{ticker}:{holding_side}:"
        f"{advice_type}:{_now_utc().date().isoformat()}"
    )
    digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:18]
    advice_key = f"p1-{digest}"

    valid_until = (_now_utc() + timedelta(hours=default_valid_hours)).isoformat()
    return {
        "advice_key": advice_key,
        "user_id": user_id,
        "portfolio_id": portfolio_id,
        "ticker": ticker,
        "holding_side": holding_side,
        "advice_type": advice_type,
        "action_side": action_side,
        "priority_score": priority_score,
        "confidence": confidence,
        "risk_level": risk_level,
        "trigger_points": trigger_points,
        "invalid_if": invalid_if,
        "opportunity_id": opportunity_id,
        "source_signal_ids": source_signal_ids,
        "source_event_ids": source_event_ids,
        "payload": {
            "holding": {
                "quantity": _safe_float(holding.get("quantity"), 0.0),
                "avg_cost": _safe_float(holding.get("avg_cost"), 0.0),
                "weight": _safe_float(holding.get("weight"), 0.0),
                "tags": _to_str_list(holding.get("tags")),
            },
            "opportunity": {
                "id": opportunity_id,
                "score": _safe_float((opp or {}).get("opportunity_score"), 0.0),
                "confidence": _safe_float((opp or {}).get("confidence"), 0.0),
                "side": str((opp or {}).get("side") or ""),
                "horizon": str((opp or {}).get("horizon") or ""),
            },
        },
        "status": "pending",
        "is_active": True,
        "valid_until": valid_until,
        "as_of": _now_utc().isoformat(),
    }


def run_portfolio_advice(
    run_id: str,
    lookback_hours: int,
    portfolio_limit: int,
    holding_limit: int,
    opportunity_limit: int,
    min_score: float,
    valid_hours: int,
) -> Dict[str, int]:
    """生成并写入持仓建议。"""
    supabase = _init_supabase()
    portfolios = _load_active_portfolios(supabase, portfolio_limit)
    portfolio_ids = [
        _safe_int(item.get("id"), 0)
        for item in portfolios
        if _safe_int(item.get("id"), 0) > 0
    ]
    holdings = _load_holdings(supabase, portfolio_ids, holding_limit)
    opp_map = _load_opportunities(supabase, lookback_hours, opportunity_limit)

    logger.info(
        "[P1_ADVICE_INPUT] portfolios=%s holdings=%s opportunities=%s",
        len(portfolios),
        len(holdings),
        len(opp_map),
    )

    payloads: List[Dict[str, Any]] = []
    for holding in holdings:
        ticker = str(holding.get("ticker") or "").upper()
        opp = opp_map.get(ticker)
        try:
            row = _decide_advice(
                holding,
                opp,
                min_score=min_score,
                default_valid_hours=valid_hours,
            )
            row["run_id"] = run_id
            payloads.append(row)
        except Exception as exc:
            logger.warning("[P1_ADVICE_BUILD_SKIP] ticker=%s error=%s", ticker, str(exc)[:120])

    written = 0
    if payloads:
        for idx in range(0, len(payloads), 200):
            batch = payloads[idx : idx + 200]
            (
                supabase.table("stock_portfolio_advice_v1")
                .upsert(batch, on_conflict="advice_key")
                .execute()
            )
            written += len(batch)

    action_dist: Dict[str, int] = {}
    for row in payloads:
        key = str(row.get("advice_type") or "unknown")
        action_dist[key] = action_dist.get(key, 0) + 1

    logger.info(
        "[P1_ADVICE_DONE] run_id=%s holdings=%s advice=%s dist=%s",
        run_id,
        len(holdings),
        written,
        action_dist,
    )

    return {
        "portfolios": len(portfolios),
        "holdings": len(holdings),
        "opportunities": len(opp_map),
        "advice_written": written,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StockOps P1 portfolio advice generator")
    parser.add_argument("--run-id", type=str, default="", help="外部 run id")
    parser.add_argument("--lookback-hours", type=int, default=72, help="机会读取回看小时")
    parser.add_argument("--portfolio-limit", type=int, default=200, help="组合读取上限")
    parser.add_argument("--holding-limit", type=int, default=1200, help="持仓读取上限")
    parser.add_argument("--opportunity-limit", type=int, default=3000, help="机会读取上限")
    parser.add_argument("--min-score", type=float, default=68.0, help="建议触发分数阈值")
    parser.add_argument("--valid-hours", type=int, default=48, help="建议有效期小时")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    run_id = args.run_id.strip() or f"p1-advice-{_now_utc().strftime('%Y%m%d%H%M%S')}"
    logger.info(
        "[P1_ADVICE_START] run_id=%s lookback=%s min_score=%.1f",
        run_id,
        args.lookback_hours,
        args.min_score,
    )
    try:
        metrics = run_portfolio_advice(
            run_id=run_id,
            lookback_hours=args.lookback_hours,
            portfolio_limit=args.portfolio_limit,
            holding_limit=args.holding_limit,
            opportunity_limit=args.opportunity_limit,
            min_score=args.min_score,
            valid_hours=args.valid_hours,
        )
    except Exception as exc:
        message = str(exc)
        if "PGRST205" in message or "stock_portfolios_v1" in message:
            logger.error(
                "[P1_ADVICE_MISSING_SCHEMA] error=%s; "
                "请先执行 sql/2026-02-24_stock_p1_portfolio_screener_schema.sql",
                message[:200],
            )
            return
        logger.error("[P1_ADVICE_FAILED] error=%s", message[:200])
        raise
    logger.info("[P1_ADVICE_METRICS] %s", metrics)


if __name__ == "__main__":
    main()
