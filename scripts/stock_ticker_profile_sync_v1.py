#!/usr/bin/env python3
"""StockOps P1 股票基础信息字典同步脚本。"""

from __future__ import annotations

import argparse
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

TICKER_PROFILE_SEED: Dict[str, Dict[str, str]] = {
    "SPY": {
        "display_name": "SPDR S&P 500 ETF",
        "asset_type": "etf",
        "sector": "Index",
        "industry": "US Large Cap",
        "summary_cn": "跟踪标普500，适合观察美股整体风险偏好与市场趋势。",
    },
    "QQQ": {
        "display_name": "Invesco QQQ Trust",
        "asset_type": "etf",
        "sector": "Index",
        "industry": "Nasdaq 100",
        "summary_cn": "跟踪纳指100，科技权重高，对成长风格与利率更敏感。",
    },
    "DIA": {
        "display_name": "SPDR Dow Jones Industrial Average ETF",
        "asset_type": "etf",
        "sector": "Index",
        "industry": "Dow 30",
        "summary_cn": "跟踪道琼斯工业指数，偏大盘蓝筹，防御属性相对更强。",
    },
    "IWM": {
        "display_name": "iShares Russell 2000 ETF",
        "asset_type": "etf",
        "sector": "Index",
        "industry": "Small Cap",
        "summary_cn": "跟踪罗素2000小盘股，常用于衡量风险偏好与内需弹性。",
    },
    "XLF": {
        "display_name": "Financial Select Sector SPDR",
        "asset_type": "etf",
        "sector": "Financials",
        "industry": "Sector ETF",
        "summary_cn": "金融板块ETF，对利率曲线、信用环境与监管变化敏感。",
    },
    "XLK": {
        "display_name": "Technology Select Sector SPDR",
        "asset_type": "etf",
        "sector": "Technology",
        "industry": "Sector ETF",
        "summary_cn": "科技板块ETF，受AI资本开支、业绩预期和估值影响较大。",
    },
    "XLE": {
        "display_name": "Energy Select Sector SPDR",
        "asset_type": "etf",
        "sector": "Energy",
        "industry": "Sector ETF",
        "summary_cn": "能源板块ETF，与油价、地缘风险和供需周期关系紧密。",
    },
    "XLV": {
        "display_name": "Health Care Select Sector SPDR",
        "asset_type": "etf",
        "sector": "Healthcare",
        "industry": "Sector ETF",
        "summary_cn": "医疗板块ETF，兼具防御属性与政策监管敏感性。",
    },
    "SMH": {
        "display_name": "VanEck Semiconductor ETF",
        "asset_type": "etf",
        "sector": "Technology",
        "industry": "Semiconductors",
        "summary_cn": "半导体ETF，受AI算力周期、库存与资本开支影响显著。",
    },
    "TLT": {
        "display_name": "iShares 20+ Year Treasury Bond ETF",
        "asset_type": "etf",
        "sector": "Rates",
        "industry": "US Treasury",
        "summary_cn": "美债长久期ETF，反映利率预期与避险情绪变化。",
    },
    "AAPL": {
        "display_name": "Apple Inc.",
        "asset_type": "equity",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "summary_cn": "消费电子龙头，关注新品周期、服务收入与全球需求变化。",
    },
    "MSFT": {
        "display_name": "Microsoft Corporation",
        "asset_type": "equity",
        "sector": "Technology",
        "industry": "Software",
        "summary_cn": "软件与云计算龙头，关键变量是云增速、AI商业化与利润率。",
    },
    "NVDA": {
        "display_name": "NVIDIA Corporation",
        "asset_type": "equity",
        "sector": "Technology",
        "industry": "Semiconductors",
        "summary_cn": "AI芯片核心公司，关注数据中心需求、供给节奏与估值波动。",
    },
    "AMZN": {
        "display_name": "Amazon.com, Inc.",
        "asset_type": "equity",
        "sector": "Consumer Discretionary",
        "industry": "E-commerce & Cloud",
        "summary_cn": "电商与云双引擎公司，重点看AWS增速、消费强度与利润改善。",
    },
    "GOOGL": {
        "display_name": "Alphabet Inc.",
        "asset_type": "equity",
        "sector": "Technology",
        "industry": "Internet Services",
        "summary_cn": "搜索与广告平台龙头，关注广告景气、云业务与AI竞争格局。",
    },
    "META": {
        "display_name": "Meta Platforms, Inc.",
        "asset_type": "equity",
        "sector": "Technology",
        "industry": "Social Media",
        "summary_cn": "社交广告平台公司，核心变量为广告效率、用户增长和AI投入。",
    },
    "TSLA": {
        "display_name": "Tesla, Inc.",
        "asset_type": "equity",
        "sector": "Consumer Discretionary",
        "industry": "EV & Energy Storage",
        "summary_cn": "新能源车龙头，关注交付增速、价格策略与自动驾驶进展。",
    },
}

TICKER_TO_INDUSTRY: Dict[str, str] = {
    "SPY": "US Large Cap",
    "QQQ": "Nasdaq 100",
    "DIA": "Dow 30",
    "IWM": "Small Cap",
    "VTI": "US Total Market",
    "VOO": "US Large Cap",
    "XLF": "Financials",
    "XLK": "Technology",
    "XLE": "Energy",
    "XLV": "Healthcare",
    "XLI": "Industrials",
    "XLP": "Consumer Staples",
    "XLY": "Consumer Discretionary",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "SMH": "Semiconductors",
    "SOXX": "Semiconductors",
    "TLT": "US Treasury",
    "AAPL": "Consumer Electronics",
    "MSFT": "Software",
    "NVDA": "Semiconductors",
    "AMZN": "E-commerce & Cloud",
    "GOOGL": "Internet Services",
    "META": "Social Media",
    "TSLA": "EV & Energy Storage",
}

ETF_HINTS = {
    "SPY",
    "QQQ",
    "DIA",
    "IWM",
    "VTI",
    "VOO",
    "XLF",
    "XLK",
    "XLE",
    "XLV",
    "XLI",
    "XLP",
    "XLY",
    "XLU",
    "XLRE",
    "SMH",
    "SOXX",
    "TLT",
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


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


def _load_recent_opportunities(
    supabase,
    lookback_hours: int,
    limit: int,
) -> Dict[str, Dict[str, Any]]:
    cutoff = (_now_utc() - timedelta(hours=lookback_hours)).isoformat()
    rows = (
        supabase.table("stock_opportunities_v2")
        .select("ticker,why_now,catalysts,side,opportunity_score,confidence,as_of")
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
        ticker = str(row.get("ticker") or "").upper().strip()
        if not ticker:
            continue
        if ticker not in by_ticker:
            by_ticker[ticker] = row
    return by_ticker


def _load_holdings_tickers(supabase, limit: int) -> List[str]:
    rows = (
        supabase.table("stock_portfolio_holdings_v1")
        .select("ticker")
        .eq("is_active", True)
        .order("updated_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    result: List[str] = []
    for row in rows:
        ticker = str(row.get("ticker") or "").upper().strip()
        if ticker:
            result.append(ticker)
    return result


def _load_screener_tickers(supabase, limit: int) -> List[str]:
    rows = (
        supabase.table("stock_screener_candidates_v1")
        .select("ticker")
        .order("as_of", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    result: List[str] = []
    for row in rows:
        ticker = str(row.get("ticker") or "").upper().strip()
        if ticker:
            result.append(ticker)
    return result


def _guess_asset_type(ticker: str) -> str:
    if ticker in ETF_HINTS:
        return "etf"
    if ticker in {"DXY", "VIX", "US10Y"}:
        return "macro"
    return "equity"


def _fallback_summary(ticker: str, opp: Optional[Dict[str, Any]]) -> str:
    if opp:
        why_now = str(opp.get("why_now") or "").strip()
        score = float(opp.get("opportunity_score") or 0)
        confidence = float(opp.get("confidence") or 0)
        if why_now:
            return (
                f"近期机会分约 {score:.1f}/100，置信度 {confidence:.2f}。"
                f"核心线索：{why_now[:70]}"
            )
    return "美股观察标的，建议结合原文证据、行业景气与仓位风险二次判断。"


def _build_profile_row(
    ticker: str,
    opp: Optional[Dict[str, Any]],
    run_id: str,
) -> Dict[str, Any]:
    seeded = TICKER_PROFILE_SEED.get(ticker)
    now_iso = _now_utc().isoformat()
    if seeded:
        return {
            "ticker": ticker,
            "display_name": seeded["display_name"],
            "asset_type": seeded["asset_type"],
            "sector": seeded["sector"],
            "industry": seeded["industry"],
            "summary_cn": seeded["summary_cn"],
            "metadata": {"seeded": True},
            "source": "seed",
            "run_id": run_id,
            "as_of": now_iso,
            "is_active": True,
        }

    industry = TICKER_TO_INDUSTRY.get(ticker, "Unknown")
    asset_type = _guess_asset_type(ticker)
    sector = "Index" if asset_type == "etf" and ticker in {"SPY", "QQQ", "DIA", "IWM"} else industry
    display_name = ticker
    return {
        "ticker": ticker,
        "display_name": display_name,
        "asset_type": asset_type,
        "sector": sector,
        "industry": industry,
        "summary_cn": _fallback_summary(ticker, opp),
        "metadata": {
            "seeded": False,
            "from_opportunity": bool(opp),
        },
        "source": "pipeline_v2",
        "run_id": run_id,
        "as_of": now_iso,
        "is_active": True,
    }


def _check_profile_schema(supabase) -> bool:
    """检查表是否已创建，未创建时返回 False。"""
    try:
        supabase.table("stock_ticker_profiles_v1").select("ticker").limit(1).execute()
        return True
    except Exception as exc:
        logger.warning("[TICKER_PROFILE_SCHEMA_MISSING] %s", str(exc)[:220])
        return False


def run_sync(
    run_id: str,
    lookback_hours: int,
    opp_limit: int,
    holding_limit: int,
    screener_limit: int,
) -> Dict[str, Any]:
    supabase = _init_supabase()
    if not _check_profile_schema(supabase):
        return {
            "run_id": run_id,
            "profiles_upserted": 0,
            "tickers_total": 0,
            "status": "schema_missing",
        }

    opp_map = _load_recent_opportunities(supabase, lookback_hours=lookback_hours, limit=opp_limit)
    holding_tickers = _load_holdings_tickers(supabase, holding_limit)
    screener_tickers = _load_screener_tickers(supabase, screener_limit)

    merged_tickers = set(TICKER_PROFILE_SEED.keys())
    merged_tickers.update(opp_map.keys())
    merged_tickers.update(holding_tickers)
    merged_tickers.update(screener_tickers)

    rows: List[Dict[str, Any]] = []
    for ticker in sorted(merged_tickers):
        row = _build_profile_row(ticker=ticker, opp=opp_map.get(ticker), run_id=run_id)
        rows.append(row)

    chunk_size = 200
    written = 0
    for idx in range(0, len(rows), chunk_size):
        batch = rows[idx: idx + chunk_size]
        if not batch:
            continue
        result = (
            supabase.table("stock_ticker_profiles_v1")
            .upsert(batch, on_conflict="ticker")
            .execute()
        )
        written += len(result.data or batch)

    logger.info(
        "[TICKER_PROFILE_SYNC_DONE] run_id=%s tickers=%s upserted=%s opp=%s holdings=%s screener=%s",
        run_id,
        len(rows),
        written,
        len(opp_map),
        len(holding_tickers),
        len(screener_tickers),
    )

    return {
        "run_id": run_id,
        "profiles_upserted": written,
        "tickers_total": len(rows),
        "from_opportunities": len(opp_map),
        "from_holdings": len(holding_tickers),
        "from_screener": len(screener_tickers),
        "status": "ok",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StockOps P1 ticker profile sync")
    parser.add_argument("--run-id", type=str, default="")
    parser.add_argument("--lookback-hours", type=int, default=240)
    parser.add_argument("--opp-limit", type=int, default=5000)
    parser.add_argument("--holding-limit", type=int, default=2000)
    parser.add_argument("--screener-limit", type=int, default=2000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_id = args.run_id.strip() or "ticker-profile-" + _now_utc().strftime("%Y%m%d%H%M%S")
    logger.info(
        "[TICKER_PROFILE_SYNC_START] run_id=%s lookback=%sh opp_limit=%s",
        run_id,
        args.lookback_hours,
        args.opp_limit,
    )
    result = run_sync(
        run_id=run_id,
        lookback_hours=args.lookback_hours,
        opp_limit=args.opp_limit,
        holding_limit=args.holding_limit,
        screener_limit=args.screener_limit,
    )
    logger.info("[TICKER_PROFILE_SYNC_RESULT] %s", result)


if __name__ == "__main__":
    main()
