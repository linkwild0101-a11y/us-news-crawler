#!/usr/bin/env python3
"""StockOps P1 股票基础信息字典同步脚本。"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import requests
from bs4 import BeautifulSoup
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

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ100_WIKI_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"
OVERRIDE_FILE_DEFAULT = "config/stock_ticker_profile_overrides.tsv"

SOURCE_SP500 = "sp500"
SOURCE_NASDAQ100 = "nasdaq100"
SOURCE_PORTFOLIO = "portfolio"
SOURCE_WATCHLIST = "watchlist"
SOURCE_RECENT = "recent_signal"

PROFILE_SEED: Dict[str, Dict[str, str]] = {
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
}

ETF_PREFIXES = (
    "X",
    "SPY",
    "QQQ",
    "DIA",
    "IWM",
    "VTI",
    "VOO",
    "SOXX",
    "SMH",
    "TLT",
    "ARK",
)

SECTOR_TEMPLATE: Dict[str, str] = {
    "Technology": "科技板块，关注业绩兑现、资本开支与估值波动。",
    "Financials": "金融板块，关注利率曲线、信用环境与监管变化。",
    "Healthcare": "医疗板块，关注政策边际变化与产品管线兑现。",
    "Energy": "能源板块，关注油价、供需结构与地缘风险。",
    "Index": "指数型标的，用于观察美股风险偏好和市场趋势。",
    "Consumer Discretionary": "可选消费板块，关注需求强弱与利润弹性。",
    "Communication Services": "通信服务板块，关注广告景气与用户增长。",
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _normalize_ticker(text: str) -> str:
    raw = str(text or "").upper().strip()
    if not raw:
        return ""
    raw = raw.replace(".", "-")
    if "/" in raw:
        raw = raw.split("/", 1)[0]
    if " " in raw:
        raw = raw.split(" ", 1)[0]
    return "".join(ch for ch in raw if ch.isalnum() or ch == "-")


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


def _http_get_text(url: str, timeout: int = 20) -> str:
    headers = {
        "User-Agent": (
            "US-Monitor/1.0 (stock profile sync; "
            "contact: us-monitor@example.com)"
        )
    }
    response = requests.get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    return response.text


def _extract_symbols_from_wiki(
    html_text: str,
    symbol_headers: Sequence[str],
) -> Set[str]:
    soup = BeautifulSoup(html_text, "lxml")
    symbols: Set[str] = set()
    for table in soup.select("table.wikitable"):
        header_cells = table.select("tr th")
        headers = [cell.get_text(" ", strip=True).lower() for cell in header_cells]
        if not headers:
            continue
        symbol_idx = -1
        for candidate in symbol_headers:
            candidate_lower = candidate.lower()
            if candidate_lower in headers:
                symbol_idx = headers.index(candidate_lower)
                break
        if symbol_idx < 0:
            continue
        for row in table.select("tr"):
            tds = row.select("td")
            if len(tds) <= symbol_idx:
                continue
            ticker = _normalize_ticker(tds[symbol_idx].get_text(" ", strip=True))
            if 1 <= len(ticker) <= 16:
                symbols.add(ticker)
        if symbols:
            return symbols
    return symbols


def _fetch_sp500_symbols() -> Set[str]:
    """抓取 S&P500 代码集合。"""
    try:
        html_text = _http_get_text(SP500_WIKI_URL)
        symbols = _extract_symbols_from_wiki(
            html_text,
            symbol_headers=("symbol", "ticker symbol", "ticker"),
        )
        logger.info("[PROFILE_SP500_FETCH] count=%s", len(symbols))
        return symbols
    except Exception as exc:
        logger.warning("[PROFILE_SP500_FETCH_FAILED] %s", str(exc)[:180])
        return set()


def _fetch_nasdaq100_symbols() -> Set[str]:
    """抓取 Nasdaq100 代码集合。"""
    try:
        html_text = _http_get_text(NASDAQ100_WIKI_URL)
        symbols = _extract_symbols_from_wiki(
            html_text,
            symbol_headers=("ticker", "ticker symbol", "symbol"),
        )
        logger.info("[PROFILE_NASDAQ100_FETCH] count=%s", len(symbols))
        return symbols
    except Exception as exc:
        logger.warning("[PROFILE_NASDAQ100_FETCH_FAILED] %s", str(exc)[:180])
        return set()


def _fetch_sec_company_map() -> Dict[str, Dict[str, str]]:
    """抓取 SEC 公司代码映射（名称+交易所）。"""
    try:
        text = _http_get_text(SEC_TICKERS_URL)
        payload = json.loads(text)
        fields = payload.get("fields") or []
        rows = payload.get("data") or []
        idx_ticker = fields.index("ticker") if "ticker" in fields else -1
        idx_name = fields.index("name") if "name" in fields else -1
        idx_exchange = fields.index("exchange") if "exchange" in fields else -1
        if idx_ticker < 0:
            return {}
        result: Dict[str, Dict[str, str]] = {}
        for row in rows:
            if not isinstance(row, list):
                continue
            ticker = _normalize_ticker(row[idx_ticker] if idx_ticker < len(row) else "")
            if not ticker:
                continue
            name = str(row[idx_name] if 0 <= idx_name < len(row) else "").strip()
            exchange = str(row[idx_exchange] if 0 <= idx_exchange < len(row) else "").strip()
            result[ticker] = {
                "display_name": name,
                "exchange": exchange,
            }
        logger.info("[PROFILE_SEC_FETCH] count=%s", len(result))
        return result
    except Exception as exc:
        logger.warning("[PROFILE_SEC_FETCH_FAILED] %s", str(exc)[:180])
        return {}


def _load_overrides(path: str) -> Dict[str, Dict[str, str]]:
    """加载手工覆盖配置。"""
    if not os.path.exists(path):
        logger.info("[PROFILE_OVERRIDE_MISS] path=%s", path)
        return {}
    result: Dict[str, Dict[str, str]] = {}
    with open(path, "r", encoding="utf-8") as fp:
        reader = csv.DictReader(fp, delimiter="\t")
        for row in reader:
            ticker = _normalize_ticker(row.get("ticker") or "")
            if not ticker:
                continue
            result[ticker] = {
                "display_name": str(row.get("display_name") or "").strip(),
                "asset_type": str(row.get("asset_type") or "").strip().lower(),
                "sector": str(row.get("sector") or "").strip(),
                "industry": str(row.get("industry") or "").strip(),
                "summary_cn": str(row.get("summary_cn") or "").strip(),
            }
    logger.info("[PROFILE_OVERRIDE_LOAD] path=%s count=%s", path, len(result))
    return result


def _table_available(supabase, table_name: str, probe: str = "id") -> bool:
    try:
        supabase.table(table_name).select(probe).limit(1).execute()
        return True
    except Exception as exc:
        logger.warning("[PROFILE_TABLE_MISSING] table=%s error=%s", table_name, str(exc)[:140])
        return False


def _load_portfolio_tickers(supabase, limit: int) -> Set[str]:
    try:
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
    except Exception as exc:
        logger.warning("[PROFILE_PORTFOLIO_LOAD_FAILED] %s", str(exc)[:160])
        return set()
    return {
        _normalize_ticker(row.get("ticker") or "")
        for row in rows
        if _normalize_ticker(row.get("ticker") or "")
    }


def _load_watchlist_tickers(supabase, limit: int) -> Set[str]:
    try:
        rows = (
            supabase.table("stock_alert_user_prefs_v1")
            .select("watch_tickers")
            .eq("is_active", True)
            .eq("user_id", "system")
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        logger.warning("[PROFILE_WATCHLIST_LOAD_FAILED] %s", str(exc)[:160])
        return set()
    result: Set[str] = set()
    for row in rows:
        raw = row.get("watch_tickers") or []
        if not isinstance(raw, list):
            continue
        for item in raw:
            ticker = _normalize_ticker(item)
            if ticker:
                result.add(ticker)
    return result


def _load_recent_signal_tickers(
    supabase,
    lookback_hours: int,
    event_limit: int,
    opp_limit: int,
) -> Set[str]:
    cutoff = (_now_utc() - timedelta(hours=lookback_hours)).isoformat()
    result: Set[str] = set()

    try:
        opp_rows = (
            supabase.table("stock_opportunities_v2")
            .select("ticker")
            .eq("is_active", True)
            .gte("as_of", cutoff)
            .order("as_of", desc=True)
            .limit(opp_limit)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        logger.warning("[PROFILE_RECENT_OPP_LOAD_FAILED] %s", str(exc)[:160])
        opp_rows = []
    for row in opp_rows:
        ticker = _normalize_ticker(row.get("ticker") or "")
        if ticker:
            result.add(ticker)

    try:
        event_rows = (
            supabase.table("stock_alert_events_v1")
            .select("ticker")
            .eq("is_active", True)
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(event_limit)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        logger.warning("[PROFILE_RECENT_ALERT_LOAD_FAILED] %s", str(exc)[:160])
        event_rows = []
    for row in event_rows:
        ticker = _normalize_ticker(row.get("ticker") or "")
        if ticker:
            result.add(ticker)

    return result


def _build_universe(
    sp500: Set[str],
    nasdaq100: Set[str],
    portfolio: Set[str],
    watchlist: Set[str],
    recent_signal: Set[str],
    overrides: Dict[str, Dict[str, str]],
) -> Dict[str, Set[str]]:
    """构建 ticker 覆盖池及来源标签。"""
    universe: Dict[str, Set[str]] = {}

    def _add_many(tickers: Set[str], source: str) -> None:
        for ticker in tickers:
            if not ticker:
                continue
            bucket = universe.get(ticker) or set()
            bucket.add(source)
            universe[ticker] = bucket

    _add_many(sp500, SOURCE_SP500)
    _add_many(nasdaq100, SOURCE_NASDAQ100)
    _add_many(portfolio, SOURCE_PORTFOLIO)
    _add_many(watchlist, SOURCE_WATCHLIST)
    _add_many(recent_signal, SOURCE_RECENT)
    _add_many(set(overrides.keys()), SOURCE_WATCHLIST)
    _add_many(set(PROFILE_SEED.keys()), SOURCE_RECENT)

    return universe


def _load_existing_profiles(
    supabase,
    tickers: Sequence[str],
) -> Dict[str, Dict[str, Any]]:
    if not tickers:
        return {}
    try:
        rows = (
            supabase.table("stock_ticker_profiles_v1")
            .select("ticker,summary_cn,quality_score,summary_source")
            .in_("ticker", list(tickers[:5000]))
            .limit(6000)
            .execute()
            .data
            or []
        )
    except Exception:
        rows = (
            supabase.table("stock_ticker_profiles_v1")
            .select("ticker,summary_cn")
            .in_("ticker", list(tickers[:5000]))
            .limit(6000)
            .execute()
            .data
            or []
        )

    result: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        ticker = _normalize_ticker(row.get("ticker") or "")
        if not ticker:
            continue
        result[ticker] = row
    return result


def _guess_asset_type(ticker: str, sec_exchange: str) -> str:
    if ticker in PROFILE_SEED:
        return PROFILE_SEED[ticker].get("asset_type", "etf")
    if ticker in ("DXY", "VIX", "US10Y"):
        return "macro"
    if sec_exchange.upper() in {"NYSE ARCA", "BATS", "CBOE"}:
        return "etf"
    if ticker.startswith(ETF_PREFIXES):
        return "etf"
    return "equity"


def _guess_sector(asset_type: str, industry: str) -> str:
    if asset_type == "etf" and industry in ("US Large Cap", "Nasdaq 100", "Dow 30", "Small Cap"):
        return "Index"
    if industry in SECTOR_TEMPLATE:
        return industry
    if asset_type == "etf":
        return "ETF"
    return industry or "Unknown"


def _template_summary(
    ticker: str,
    asset_type: str,
    sector: str,
    industry: str,
) -> str:
    sector_hint = SECTOR_TEMPLATE.get(sector)
    if sector_hint:
        return sector_hint
    if asset_type == "etf":
        return f"{ticker} 为 ETF 标的，建议关注对应行业景气与资金流向变化。"
    if industry and industry != "Unknown":
        return f"{ticker} 属于 {industry} 相关标的，需关注行业景气和业绩兑现。"
    return f"{ticker} 为美股观察标的，建议结合原文证据和仓位风险二次判断。"


def _build_profile_row(
    ticker: str,
    source_tags: Set[str],
    sec_map: Dict[str, Dict[str, str]],
    overrides: Dict[str, Dict[str, str]],
    existing_map: Dict[str, Dict[str, Any]],
    run_id: str,
) -> Tuple[Dict[str, Any], Optional[str]]:
    sec_info = sec_map.get(ticker) or {}
    override = overrides.get(ticker) or {}
    seed = PROFILE_SEED.get(ticker) or {}
    existing = existing_map.get(ticker) or {}

    exchange = str(sec_info.get("exchange") or "").strip()
    display_name = (
        str(override.get("display_name") or "").strip()
        or str(seed.get("display_name") or "").strip()
        or str(sec_info.get("display_name") or "").strip()
        or ticker
    )
    asset_type = (
        str(override.get("asset_type") or "").strip().lower()
        or str(seed.get("asset_type") or "").strip().lower()
        or _guess_asset_type(ticker, exchange)
    )
    if asset_type not in {"equity", "etf", "index", "macro", "unknown"}:
        asset_type = "unknown"

    industry = (
        str(override.get("industry") or "").strip()
        or str(seed.get("industry") or "").strip()
        or "Unknown"
    )
    sector = (
        str(override.get("sector") or "").strip()
        or str(seed.get("sector") or "").strip()
        or _guess_sector(asset_type, industry)
    )

    summary_cn = (
        str(override.get("summary_cn") or "").strip()
        or str(seed.get("summary_cn") or "").strip()
        or _template_summary(ticker=ticker, asset_type=asset_type, sector=sector, industry=industry)
    )

    summary_source = "template"
    quality_score = 0.70
    if override:
        summary_source = "manual"
        quality_score = 0.95
    elif seed:
        summary_source = "seed"
        quality_score = 0.88

    reason: Optional[str] = None
    prev_exists = bool(existing)
    prev_quality = _safe_float(existing.get("quality_score"), 0.0)
    prev_summary = str(existing.get("summary_cn") or "").strip()
    if not prev_exists:
        reason = "new_symbol"
    elif not summary_cn and not prev_summary:
        reason = "missing_summary"
    elif prev_quality < 0.65:
        reason = "low_quality"

    now_iso = _now_utc().isoformat()
    row = {
        "ticker": ticker,
        "display_name": display_name[:128],
        "exchange": exchange[:24],
        "asset_type": asset_type,
        "sector": sector[:64],
        "industry": industry[:64],
        "summary_cn": summary_cn[:300],
        "summary_source": summary_source,
        "quality_score": min(1.0, max(0.0, quality_score)),
        "metadata": {
            "sources": sorted(source_tags),
            "from_override": bool(override),
            "from_seed": bool(seed),
            "sec_hit": bool(sec_info),
        },
        "source": "profile_sync",
        "run_id": run_id,
        "as_of": now_iso,
        "is_active": True,
    }
    return row, reason


def _upsert_profile_rows(supabase, rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    chunk = 200
    written = 0
    for idx in range(0, len(rows), chunk):
        batch = rows[idx : idx + chunk]
        try:
            result = (
                supabase.table("stock_ticker_profiles_v1")
                .upsert(batch, on_conflict="ticker")
                .execute()
            )
            written += len(result.data or batch)
        except Exception as exc:
            # 兼容旧 schema：去掉新增列重试
            logger.warning("[PROFILE_UPSERT_FALLBACK] %s", str(exc)[:180])
            fallback_batch = []
            for row in batch:
                fallback = dict(row)
                fallback.pop("exchange", None)
                fallback.pop("summary_source", None)
                fallback.pop("quality_score", None)
                fallback_batch.append(fallback)
            result = (
                supabase.table("stock_ticker_profiles_v1")
                .upsert(fallback_batch, on_conflict="ticker")
                .execute()
            )
            written += len(result.data or fallback_batch)
    return written


def _upsert_universe_members(
    supabase,
    run_id: str,
    universe: Dict[str, Set[str]],
) -> int:
    if not universe:
        return 0
    if not _table_available(supabase, "stock_universe_members_v1"):
        return 0
    rows: List[Dict[str, Any]] = []
    now_iso = _now_utc().isoformat()
    for ticker, tags in universe.items():
        for source in sorted(tags):
            rows.append(
                {
                    "ticker": ticker,
                    "source_type": source,
                    "source_ref": "ticker_profile_sync",
                    "payload": {"source_type": source},
                    "run_id": run_id,
                    "as_of": now_iso,
                    "is_active": True,
                }
            )
    if not rows:
        return 0
    chunk = 300
    written = 0
    for idx in range(0, len(rows), chunk):
        batch = rows[idx : idx + chunk]
        result = (
            supabase.table("stock_universe_members_v1")
            .upsert(batch, on_conflict="ticker,source_type")
            .execute()
        )
        written += len(result.data or batch)
    return written


def _upsert_queue_rows(
    supabase,
    run_id: str,
    reasons: Dict[str, str],
) -> int:
    if not reasons:
        return 0
    if not _table_available(supabase, "stock_ticker_profile_enrich_queue_v1"):
        return 0
    now_iso = _now_utc().isoformat()
    rows = [
        {
            "ticker": ticker,
            "reason": reason,
            "status": "pending",
            "retry_count": 0,
            "last_error": "",
            "next_retry_at": None,
            "payload": {"reason": reason},
            "run_id": run_id,
            "as_of": now_iso,
            "is_active": True,
        }
        for ticker, reason in reasons.items()
    ]
    if not rows:
        return 0
    chunk = 300
    written = 0
    for idx in range(0, len(rows), chunk):
        batch = rows[idx : idx + chunk]
        result = (
            supabase.table("stock_ticker_profile_enrich_queue_v1")
            .upsert(batch, on_conflict="ticker")
            .execute()
        )
        written += len(result.data or batch)
    return written


def _insert_run_log(
    supabase,
    run_id: str,
    payload: Dict[str, Any],
) -> None:
    if not _table_available(supabase, "stock_ticker_profile_sync_runs_v1"):
        return
    row = {
        "run_id": run_id,
        "stage": "sync",
        "status": "success",
        "input_count": _safe_int(payload.get("input_count")),
        "updated_count": _safe_int(payload.get("updated_count")),
        "queued_count": _safe_int(payload.get("queued_count")),
        "llm_success_count": 0,
        "llm_failed_count": 0,
        "duration_sec": _safe_float(payload.get("duration_sec")),
        "error_summary": "",
        "payload": payload,
        "as_of": _now_utc().isoformat(),
    }
    supabase.table("stock_ticker_profile_sync_runs_v1").upsert(
        row, on_conflict="run_id"
    ).execute()


def run_sync(
    run_id: str,
    override_file: str,
    lookback_hours: int,
    event_limit: int,
    opp_limit: int,
) -> Dict[str, Any]:
    """执行 ticker profile 同步主流程。"""
    start_ts = time.time()
    supabase = _init_supabase()

    if not _table_available(supabase, "stock_ticker_profiles_v1", probe="ticker"):
        return {
            "run_id": run_id,
            "status": "profile_table_missing",
            "input_count": 0,
            "updated_count": 0,
            "queued_count": 0,
        }

    overrides = _load_overrides(override_file)
    sp500 = _fetch_sp500_symbols()
    nasdaq100 = _fetch_nasdaq100_symbols()
    sec_map = _fetch_sec_company_map()
    portfolio = _load_portfolio_tickers(supabase, limit=2000)
    watchlist = _load_watchlist_tickers(supabase, limit=200)
    recent_signal = _load_recent_signal_tickers(
        supabase=supabase,
        lookback_hours=lookback_hours,
        event_limit=event_limit,
        opp_limit=opp_limit,
    )

    universe = _build_universe(
        sp500=sp500,
        nasdaq100=nasdaq100,
        portfolio=portfolio,
        watchlist=watchlist,
        recent_signal=recent_signal,
        overrides=overrides,
    )
    tickers = sorted(universe.keys())
    existing_map = _load_existing_profiles(supabase, tickers)

    profile_rows: List[Dict[str, Any]] = []
    queue_reason_map: Dict[str, str] = {}
    for ticker in tickers:
        row, reason = _build_profile_row(
            ticker=ticker,
            source_tags=universe[ticker],
            sec_map=sec_map,
            overrides=overrides,
            existing_map=existing_map,
            run_id=run_id,
        )
        profile_rows.append(row)
        if reason:
            queue_reason_map[ticker] = reason

    updated_count = _upsert_profile_rows(supabase, profile_rows)
    universe_count = _upsert_universe_members(supabase, run_id=run_id, universe=universe)
    queued_count = _upsert_queue_rows(supabase, run_id=run_id, reasons=queue_reason_map)
    duration_sec = round(time.time() - start_ts, 3)

    result = {
        "run_id": run_id,
        "status": "ok",
        "input_count": len(tickers),
        "updated_count": updated_count,
        "queued_count": queued_count,
        "universe_rows_upserted": universe_count,
        "source_counts": {
            SOURCE_SP500: len(sp500),
            SOURCE_NASDAQ100: len(nasdaq100),
            SOURCE_PORTFOLIO: len(portfolio),
            SOURCE_WATCHLIST: len(watchlist),
            SOURCE_RECENT: len(recent_signal),
        },
        "duration_sec": duration_sec,
    }
    _insert_run_log(supabase, run_id=run_id, payload=result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StockOps P1 ticker profile sync")
    parser.add_argument("--run-id", type=str, default="")
    parser.add_argument("--override-file", type=str, default=OVERRIDE_FILE_DEFAULT)
    parser.add_argument("--lookback-hours", type=int, default=168)
    parser.add_argument("--event-limit", type=int, default=1200)
    parser.add_argument("--opp-limit", type=int, default=5000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_id = args.run_id.strip() or "ticker-profile-sync-" + _now_utc().strftime("%Y%m%d%H%M%S")
    logger.info(
        "[TICKER_PROFILE_SYNC_START] run_id=%s lookback=%s override=%s",
        run_id,
        args.lookback_hours,
        args.override_file,
    )
    result = run_sync(
        run_id=run_id,
        override_file=args.override_file,
        lookback_hours=max(24, args.lookback_hours),
        event_limit=max(100, args.event_limit),
        opp_limit=max(500, args.opp_limit),
    )
    logger.info("[TICKER_PROFILE_SYNC_RESULT] %s", result)


if __name__ == "__main__":
    main()
