#!/usr/bin/env python3
"""美股机会聚合脚本（方案1：机会漏斗）。"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from supabase import create_client

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

LEVEL_SCORE = {"L0": 0.1, "L1": 0.25, "L2": 0.5, "L3": 0.75, "L4": 1.0}
TICKER_PATTERN = re.compile(r"\b[A-Z]{2,5}\b")
DEFAULT_TICKERS = {
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
    "VIX",
    "DXY",
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
}
STOCK_HINTS = [
    "美股",
    "纳斯达克",
    "道琼斯",
    "标普",
    "華爾街",
    "华尔街",
    "earnings",
    "guidance",
    "fed",
    "fomc",
    "treasury",
    "yield",
    "vix",
    "dxy",
]
BULLISH_HINTS = [
    "beat",
    "upgrade",
    "inflow",
    "rebound",
    "approval",
    "easing",
    "增长",
    "上调",
    "超预期",
    "回购",
]
BEARISH_HINTS = [
    "downgrade",
    "outflow",
    "ban",
    "sanction",
    "warning",
    "investigation",
    "default",
    "miss",
    "下调",
    "诉讼",
    "爆雷",
]


def _init_supabase():
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


def _safe_level(value: Any) -> str:
    text = str(value or "L1").upper()
    return text if text in LEVEL_SCORE else "L1"


def _clamp(value: float, left: float, right: float) -> float:
    return max(left, min(right, value))


def _extract_market_snapshot(supabase) -> Dict[str, Any]:
    """读取最新市场快照。"""
    rows = (
        supabase.table("market_snapshot_daily")
        .select("snapshot_date,spy,qqq,dia,vix,us10y,dxy,risk_level,daily_brief")
        .order("snapshot_date", desc=True)
        .limit(1)
        .execute()
    )
    data = rows.data or []
    if not data:
        return {}
    return data[0]


def _build_regime(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """基于快照构建市场状态。"""
    vix = _safe_float(snapshot.get("vix"), 18.0)
    us10y = _safe_float(snapshot.get("us10y"), 4.0)
    dxy = _safe_float(snapshot.get("dxy"), 103.0)
    score = 0.0

    if vix <= 16:
        score += 0.35
    elif vix >= 24:
        score -= 0.45

    if us10y <= 4.0:
        score += 0.25
    elif us10y >= 4.6:
        score -= 0.25

    if dxy <= 101:
        score += 0.2
    elif dxy >= 105:
        score -= 0.2

    score = _clamp(score, -1.0, 1.0)
    risk_state = "risk_on" if score >= 0.2 else "risk_off" if score <= -0.2 else "neutral"
    vol_state = "high_vol" if vix >= 24 else "low_vol" if vix <= 16 else "mid_vol"
    liquidity_state = "tight" if us10y >= 4.6 else "loose" if us10y <= 4.0 else "neutral"
    summary = (
        f"状态:{risk_state} | VIX:{vix:.2f} | 10Y:{us10y:.2f}% | DXY:{dxy:.2f}"
    )
    return {
        "risk_state": risk_state,
        "vol_state": vol_state,
        "liquidity_state": liquidity_state,
        "regime_score": score,
        "summary": summary,
        "snapshot": snapshot,
    }


def _tokenize_tickers(text: str, candidates: Set[str]) -> Set[str]:
    found = set()
    for token in TICKER_PATTERN.findall(text.upper()):
        if token in candidates:
            found.add(token)
    return found


def _is_stock_signal(signal: Dict[str, Any], candidates: Set[str]) -> bool:
    details = signal.get("details", {})
    if isinstance(details, dict):
        related_tickers = details.get("related_tickers", [])
        if isinstance(related_tickers, list):
            for item in related_tickers:
                if str(item).upper() in candidates:
                    return True
    payload = " ".join(
        [
            str(signal.get("sentinel_id") or ""),
            str(signal.get("description") or ""),
            " ".join([str(x) for x in signal.get("trigger_reasons", []) or []]),
        ]
    ).lower()
    if _tokenize_tickers(payload, candidates):
        return True
    return any(hint.lower() in payload for hint in STOCK_HINTS)


def _extract_signal_tickers(signal: Dict[str, Any], candidates: Set[str]) -> Set[str]:
    details = signal.get("details", {})
    result: Set[str] = set()
    if isinstance(details, dict):
        related_tickers = details.get("related_tickers", [])
        if isinstance(related_tickers, list):
            for item in related_tickers:
                ticker = str(item or "").upper()
                if ticker in candidates:
                    result.add(ticker)
        one_ticker = str(details.get("ticker") or "").upper()
        if one_ticker in candidates:
            result.add(one_ticker)

    payload = " ".join(
        [
            str(signal.get("description") or ""),
            " ".join([str(x) for x in signal.get("trigger_reasons", []) or []]),
        ]
    )
    result.update(_tokenize_tickers(payload, candidates))
    return result


def _sentiment_bias(text: str) -> float:
    lower = text.lower()
    bull = sum(1 for token in BULLISH_HINTS if token in lower)
    bear = sum(1 for token in BEARISH_HINTS if token in lower)
    if bull == 0 and bear == 0:
        return 0.0
    return _clamp((bull - bear) / max(1, bull + bear), -1.0, 1.0)


def _load_signals(supabase, cutoff_iso: str, limit: int) -> List[Dict[str, Any]]:
    """读取信号，兼容旧库缺少 details 字段。"""
    try:
        rows = (
            supabase.table("analysis_signals")
            .select(
                "id,signal_type,cluster_id,sentinel_id,alert_level,risk_score,description,"
                "trigger_reasons,evidence_links,details,created_at"
            )
            .gte("created_at", cutoff_iso)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return rows.data or []
    except Exception as e:
        logger.warning(
            "[OPPORTUNITY_SCHEMA_FALLBACK] analysis_signals 缺少 details 字段，"
            f"降级查询: {str(e)[:120]}"
        )
        rows = (
            supabase.table("analysis_signals")
            .select(
                "id,signal_type,cluster_id,sentinel_id,alert_level,risk_score,description,"
                "trigger_reasons,evidence_links,created_at"
            )
            .gte("created_at", cutoff_iso)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return rows.data or []


def _load_clusters(supabase, cutoff_iso: str, limit: int) -> Dict[int, Dict[str, Any]]:
    rows = (
        supabase.table("analysis_clusters")
        .select("id,primary_title,primary_link,summary,category,created_at")
        .gte("created_at", cutoff_iso)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    result: Dict[int, Dict[str, Any]] = {}
    for row in rows.data or []:
        cid = int(row.get("id") or 0)
        if cid > 0:
            result[cid] = row
    return result


def _load_ticker_digest(supabase, limit: int = 80) -> List[Dict[str, Any]]:
    rows = (
        supabase.table("ticker_signal_digest")
        .select("ticker,signal_count_24h,related_cluster_count_24h,risk_level,top_sentinel_levels")
        .order("signal_count_24h", desc=True)
        .limit(limit)
        .execute()
    )
    return rows.data or []


def _score_ticker(
    row: Dict[str, Any],
    regime: Dict[str, Any],
    related_signals: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """按 A 优先、B 次之计算机会分。"""
    ticker = str(row.get("ticker") or "").upper()
    signal_count = int(row.get("signal_count_24h") or 0)
    cluster_count = int(row.get("related_cluster_count_24h") or 0)
    risk_level = _safe_level(row.get("risk_level"))
    level_score = LEVEL_SCORE.get(risk_level, 0.25)

    event_score = _clamp(
        0.45 * level_score
        + 0.35 * _clamp(signal_count / 8.0, 0.0, 1.0)
        + 0.20 * _clamp(cluster_count / 5.0, 0.0, 1.0),
        0.0,
        1.0,
    )
    flow_score = _clamp(
        0.5 * _clamp(signal_count / 10.0, 0.0, 1.0)
        + 0.5 * _clamp(len(row.get("top_sentinel_levels", []) or []) / 3.0, 0.0, 1.0),
        0.0,
        1.0,
    )

    signal_text = " ".join(
        [
            str(item.get("description") or "")
            + " "
            + " ".join([str(x) for x in item.get("trigger_reasons", []) or []])
            for item in related_signals[:8]
        ]
    )
    sentiment = _sentiment_bias(signal_text)
    side = "LONG" if sentiment >= 0 else "SHORT"
    regime_score = _safe_float(regime.get("regime_score"), 0.0)
    if abs(sentiment) < 0.15:
        side = "SHORT" if regime_score <= -0.2 else "LONG"

    macro_support = regime_score if side == "LONG" else -regime_score
    macro_score = _clamp((macro_support + 1.0) / 2.0, 0.0, 1.0)

    vix = _safe_float(regime.get("snapshot", {}).get("vix"), 18.0)
    if side == "LONG":
        vol_support = _clamp((22.0 - vix) / 10.0, -1.0, 1.0)
    else:
        vol_support = _clamp((vix - 18.0) / 10.0, -1.0, 1.0)
    volatility_score = _clamp((vol_support + 1.0) / 2.0, 0.0, 1.0)

    risk_adjust = 0.6 * volatility_score + 0.4 * _clamp(abs(sentiment), 0.0, 1.0)
    score_a = _clamp(
        0.5 * event_score + 0.25 * flow_score + 0.15 * risk_adjust + 0.10 * macro_score,
        0.0,
        1.0,
    )
    score_b = _clamp(
        0.45 * event_score + 0.35 * macro_score + 0.20 * _clamp(1.0 - abs(vol_support), 0.0, 1.0),
        0.0,
        1.0,
    )

    horizon = "B" if score_b - score_a >= 0.18 else "A"
    score = _clamp((0.65 * score_a + 0.25 * score_b + 0.10 * risk_adjust) * 100.0, 0.0, 100.0)
    confidence = _clamp(0.45 + score / 220.0, 0.4, 0.95)

    why_now = (
        f"{ticker} 近24h信号{signal_count}条、热点{cluster_count}个，"
        f"事件强度{event_score:.2f}，市场状态{regime.get('risk_state', 'neutral')}。"
    )
    if side == "LONG":
        invalid_if = (
            "若VIX快速上破24、美元指数明显走强且该标的24h信号热度回落，"
            "则该机会失效。"
        )
    else:
        invalid_if = (
            "若VIX快速回落至16下方、风险偏好修复且该标的负面信号减弱，"
            "则该机会失效。"
        )

    return {
        "ticker": ticker,
        "side": side,
        "horizon": horizon,
        "opportunity_score": round(score, 2),
        "confidence": round(confidence, 4),
        "risk_level": risk_level,
        "why_now": why_now,
        "invalid_if": invalid_if,
        "factor_breakdown": {
            "score_a": round(score_a, 4),
            "score_b": round(score_b, 4),
            "event_score": round(event_score, 4),
            "flow_score": round(flow_score, 4),
            "macro_score": round(macro_score, 4),
            "volatility_score": round(volatility_score, 4),
            "sentiment_bias": round(sentiment, 4),
            "regime_score": round(regime_score, 4),
        },
    }


def refresh_opportunities(hours: int = 48, limit: int = 600, topn: int = 40) -> Dict[str, Any]:
    """刷新机会榜与证据层。"""
    supabase = _init_supabase()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_iso = cutoff.isoformat()
    logger.info(f"[OPPORTUNITY_START] hours={hours} limit={limit} topn={topn}")

    digest_rows = _load_ticker_digest(supabase, limit=120)
    candidates = set(DEFAULT_TICKERS)
    for row in digest_rows:
        ticker = str(row.get("ticker") or "").upper()
        if ticker:
            candidates.add(ticker)

    all_signals = _load_signals(supabase, cutoff_iso, limit)
    stock_signals = [item for item in all_signals if _is_stock_signal(item, candidates)]
    clusters = _load_clusters(supabase, cutoff_iso, limit)
    snapshot = _extract_market_snapshot(supabase)
    regime = _build_regime(snapshot)

    signals_by_ticker: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for signal in stock_signals:
        tickers = _extract_signal_tickers(signal, candidates)
        if not tickers:
            continue
        for ticker in tickers:
            signals_by_ticker[ticker].append(signal)

    digest_map = {str(row.get("ticker") or "").upper(): row for row in digest_rows}
    ticker_pool = set(signals_by_ticker.keys()) | set(digest_map.keys())

    scored_rows: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for ticker in ticker_pool:
        digest_row = digest_map.get(
            ticker,
            {
                "ticker": ticker,
                "signal_count_24h": len(signals_by_ticker.get(ticker, [])),
                "related_cluster_count_24h": len(
                    {
                        int(x.get("cluster_id") or 0)
                        for x in signals_by_ticker.get(ticker, [])
                        if int(x.get("cluster_id") or 0) > 0
                    }
                ),
                "risk_level": "L1",
                "top_sentinel_levels": [],
            },
        )
        related = sorted(
            signals_by_ticker.get(ticker, []),
            key=lambda x: str(x.get("created_at") or ""),
            reverse=True,
        )
        scored = _score_ticker(digest_row, regime, related)
        scored["opportunity_key"] = (
            f"{ticker}:{scored['side']}:{scored['horizon']}:{now.strftime('%Y%m%d%H')}"
        )
        scored["as_of"] = now.isoformat()
        scored["expires_at"] = (
            now + timedelta(hours=72 if scored["horizon"] == "A" else 24 * 14)
        ).isoformat()
        scored["source_signal_ids"] = [
            int(item.get("id"))
            for item in related[:20]
            if int(item.get("id") or 0) > 0
        ]
        scored["source_cluster_ids"] = sorted(
            list(
                {
                    int(item.get("cluster_id"))
                    for item in related[:20]
                    if int(item.get("cluster_id") or 0) > 0
                }
            )
        )
        scored["catalysts"] = [
            str(item.get("description") or "")[:120]
            for item in related[:3]
            if item.get("description")
        ]
        scored_rows.append(scored)

    scored_rows.sort(key=lambda row: float(row.get("opportunity_score", 0.0)), reverse=True)
    scored_rows = scored_rows[:topn]

    regime_row = {
        "regime_date": datetime.now(timezone.utc).date().isoformat(),
        "risk_state": regime["risk_state"],
        "vol_state": regime["vol_state"],
        "liquidity_state": regime["liquidity_state"],
        "regime_score": round(_safe_float(regime["regime_score"]), 4),
        "summary": regime["summary"],
        "source_payload": {
            "snapshot": snapshot,
            "all_signals": len(all_signals),
            "stock_signals": len(stock_signals),
            "generated_at": now.isoformat(),
        },
    }
    supabase.table("market_regime_daily").upsert(regime_row).execute()

    factor_rows = []
    for row in scored_rows:
        factor = row.get("factor_breakdown", {})
        factor_rows.append(
            {
                "ticker": row["ticker"],
                "flow_score": _safe_float(factor.get("flow_score")) * 2 - 1,
                "macro_score": _safe_float(factor.get("macro_score")) * 2 - 1,
                "event_score": _safe_float(factor.get("event_score")) * 2 - 1,
                "sentiment_score": _safe_float(factor.get("sentiment_bias")),
                "volatility_score": _safe_float(factor.get("volatility_score")) * 2 - 1,
                "risk_adjust": _safe_float(factor.get("score_a")) * 2 - 1,
                "total_score": _safe_float(row.get("opportunity_score")) / 50.0 - 1,
                "updated_at": now.isoformat(),
            }
        )
    if factor_rows:
        supabase.table("ticker_factor_snapshot").upsert(factor_rows).execute()

    supabase.table("opportunity_evidence").delete().neq("id", 0).execute()
    supabase.table("opportunities").delete().neq("id", 0).execute()

    opportunity_payload = [
        {
            "opportunity_key": row["opportunity_key"],
            "ticker": row["ticker"],
            "side": row["side"],
            "horizon": row["horizon"],
            "opportunity_score": row["opportunity_score"],
            "confidence": row["confidence"],
            "risk_level": row["risk_level"],
            "why_now": row["why_now"],
            "invalid_if": row["invalid_if"],
            "catalysts": row["catalysts"],
            "factor_breakdown": row["factor_breakdown"],
            "source_signal_ids": row["source_signal_ids"],
            "source_cluster_ids": row["source_cluster_ids"],
            "expires_at": row["expires_at"],
            "as_of": row["as_of"],
        }
        for row in scored_rows
    ]

    if opportunity_payload:
        supabase.table("opportunities").insert(opportunity_payload).execute()

    created = (
        supabase.table("opportunities")
        .select("id,opportunity_key,ticker,source_signal_ids,source_cluster_ids")
        .order("opportunity_score", desc=True)
        .limit(topn)
        .execute()
    ).data or []
    key_to_id = {str(row.get("opportunity_key")): int(row.get("id")) for row in created}

    evidence_rows = []
    for row in scored_rows:
        opportunity_id = key_to_id.get(row["opportunity_key"])
        if not opportunity_id:
            continue

        for signal_id in row["source_signal_ids"][:8]:
            evidence_rows.append(
                {
                    "opportunity_id": opportunity_id,
                    "source_type": "signal",
                    "source_ref": f"signal:{signal_id}",
                    "title": f"{row['ticker']} 关联信号 #{signal_id}",
                    "url": "",
                    "weight": 0.7,
                }
            )

        for cluster_id in row["source_cluster_ids"][:6]:
            cluster = clusters.get(cluster_id, {})
            evidence_rows.append(
                {
                    "opportunity_id": opportunity_id,
                    "source_type": "cluster",
                    "source_ref": f"cluster:{cluster_id}",
                    "title": str(cluster.get("primary_title") or f"cluster:{cluster_id}")[:180],
                    "url": str(cluster.get("primary_link") or ""),
                    "weight": 0.6,
                }
            )

    if evidence_rows:
        supabase.table("opportunity_evidence").insert(evidence_rows).execute()

    long_count = sum(1 for row in scored_rows if row.get("side") == "LONG")
    short_count = sum(1 for row in scored_rows if row.get("side") == "SHORT")
    logger.info(
        "[OPPORTUNITY_DONE] "
        f"total={len(scored_rows)} long={long_count} short={short_count} "
        f"stock_signals={len(stock_signals)}"
    )
    return {
        "total": len(scored_rows),
        "long": long_count,
        "short": short_count,
        "stock_signals": len(stock_signals),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="刷新美股机会榜")
    parser.add_argument("--hours", type=int, default=48, help="统计窗口（小时）")
    parser.add_argument("--limit", type=int, default=600, help="最多读取信号数")
    parser.add_argument("--topn", type=int, default=40, help="最多输出机会数")
    args = parser.parse_args()

    try:
        metrics = refresh_opportunities(
            hours=args.hours,
            limit=args.limit,
            topn=args.topn,
        )
        logger.info(
            "[OPPORTUNITY_METRICS] "
            + ", ".join([f"{key}={value}" for key, value in metrics.items()])
        )
    except Exception as e:
        logger.error(f"[OPPORTUNITY_FAILED] error={str(e)[:200]}")
        raise


if __name__ == "__main__":
    main()
