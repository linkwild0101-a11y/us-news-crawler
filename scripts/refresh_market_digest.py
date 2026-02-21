#!/usr/bin/env python3
"""市场聚合摘要刷新脚本。"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Set, Tuple

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

LEVEL_ORDER = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}
TRACKED_TICKERS = {
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
    "GLD",
    "USO",
    "DXY",
    "VIX",
}
TOKEN_PATTERN = re.compile(r"\b[A-Z]{2,5}\b")


def _init_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("缺少 SUPABASE_URL / SUPABASE_KEY")
    return create_client(url, key)


def _safe_level(level: Any) -> str:
    text = str(level or "L1").upper()
    return text if text in LEVEL_ORDER else "L1"


def _extract_tickers(row: Dict[str, Any]) -> Set[str]:
    tickers: Set[str] = set()

    details = row.get("details", {})
    if isinstance(details, dict):
        related_tickers = details.get("related_tickers", [])
        if isinstance(related_tickers, list):
            tickers.update(str(item).upper() for item in related_tickers if item)

        single_ticker = details.get("ticker")
        if single_ticker:
            tickers.add(str(single_ticker).upper())

    texts: List[str] = [str(row.get("description") or "")]
    trigger_reasons = row.get("trigger_reasons", [])
    if isinstance(trigger_reasons, list):
        texts.extend([str(item) for item in trigger_reasons if item])

    for text in texts:
        for token in TOKEN_PATTERN.findall(text.upper()):
            if token in TRACKED_TICKERS:
                tickers.add(token)

    return {item for item in tickers if item in TRACKED_TICKERS}


def _highest_level(levels: List[str]) -> str:
    if not levels:
        return "L1"
    return max(levels, key=lambda item: LEVEL_ORDER.get(item, 0))


def _build_daily_brief(
    signals: List[Dict[str, Any]],
    clusters: List[Dict[str, Any]],
) -> Tuple[str, str]:
    if not signals:
        return "L1", "最近24小时暂无哨兵告警，风险状态维持低位。"

    levels = [_safe_level(item.get("alert_level")) for item in signals]
    highest = _highest_level(levels)
    counter = Counter(levels)

    brief_parts = [
        f"最近24小时共检测到 {len(signals)} 条哨兵告警",
        f"L4:{counter.get('L4', 0)} L3:{counter.get('L3', 0)} L2:{counter.get('L2', 0)}",
    ]

    top_signal = signals[0]
    description = str(top_signal.get("description") or "")
    if description:
        brief_parts.append(f"最新告警: {description[:120]}")

    if clusters:
        top_cluster = clusters[0]
        cluster_title = str(top_cluster.get("primary_title") or "")
        if cluster_title:
            brief_parts.append(f"热点主题: {cluster_title[:80]}")

    return highest, "；".join(brief_parts)


def _load_recent_signals(supabase, cutoff_iso: str, limit: int) -> List[Dict[str, Any]]:
    try:
        result = (
            supabase.table("analysis_signals")
            .select(
                "id,cluster_id,sentinel_id,alert_level,risk_score,description,"
                "trigger_reasons,evidence_links,details,created_at"
            )
            .eq("signal_type", "watchlist_alert")
            .gte("created_at", cutoff_iso)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.warning(
            "[MARKET_DIGEST_SCHEMA_FALLBACK] analysis_signals 缺少 details 字段，"
            f"降级查询: {str(e)[:120]}"
        )
        result = (
            supabase.table("analysis_signals")
            .select(
                "id,cluster_id,sentinel_id,alert_level,risk_score,description,"
                "trigger_reasons,evidence_links,created_at"
            )
            .eq("signal_type", "watchlist_alert")
            .gte("created_at", cutoff_iso)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []


def _load_recent_clusters(supabase, cutoff_iso: str, limit: int) -> List[Dict[str, Any]]:
    result = (
        supabase.table("analysis_clusters")
        .select("id,primary_title,summary,article_count,category,created_at")
        .gte("created_at", cutoff_iso)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def refresh_market_digest(hours: int = 24, limit: int = 400) -> Dict[str, Any]:
    """刷新移动端所需 market_snapshot_daily 与 ticker_signal_digest。"""

    supabase = _init_supabase()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_iso = cutoff.isoformat()

    logger.info(f"[MARKET_DIGEST_START] hours={hours} limit={limit}")

    signals = _load_recent_signals(supabase, cutoff_iso, limit)
    clusters = _load_recent_clusters(supabase, cutoff_iso, limit)

    risk_level, daily_brief = _build_daily_brief(signals, clusters)

    today = datetime.now(timezone.utc).date().isoformat()
    snapshot_payload = {
        "snapshot_date": today,
        "spy": None,
        "qqq": None,
        "dia": None,
        "vix": None,
        "us10y": None,
        "dxy": None,
        "risk_level": risk_level,
        "daily_brief": daily_brief,
        "source_payload": {
            "signal_count": len(signals),
            "cluster_count": len(clusters),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_hours": hours,
        },
    }

    supabase.table("market_snapshot_daily").upsert(snapshot_payload).execute()
    logger.info(f"[MARKET_DIGEST_SNAPSHOT] date={today} risk={risk_level}")

    cluster_map = {int(item.get("id", 0)): item for item in clusters if item.get("id")}

    bucket: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "signal_count_24h": 0,
            "cluster_ids": set(),
            "levels": [],
            "top_clusters": [],
        }
    )

    for signal in signals:
        tickers = _extract_tickers(signal)
        if not tickers:
            continue

        level = _safe_level(signal.get("alert_level"))
        cluster_id = signal.get("cluster_id")
        try:
            cluster_numeric = int(cluster_id) if cluster_id is not None else None
        except Exception:
            cluster_numeric = None

        for ticker in tickers:
            item = bucket[ticker]
            item["signal_count_24h"] += 1
            item["levels"].append(level)
            if cluster_numeric is not None:
                item["cluster_ids"].add(cluster_numeric)

    digest_rows: List[Dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for ticker, item in bucket.items():
        cluster_ids = list(item["cluster_ids"])
        top_clusters = []
        for cid in cluster_ids[:3]:
            cluster_row = cluster_map.get(cid)
            if not cluster_row:
                continue
            top_clusters.append(
                {
                    "id": cid,
                    "title": str(cluster_row.get("primary_title") or ""),
                    "category": str(cluster_row.get("category") or ""),
                }
            )

        level_counter = Counter(item["levels"])
        top_levels = [name for name, _ in level_counter.most_common(3)]

        digest_rows.append(
            {
                "ticker": ticker,
                "signal_count_24h": int(item["signal_count_24h"]),
                "related_cluster_count_24h": len(cluster_ids),
                "risk_level": _highest_level(item["levels"]),
                "top_sentinel_levels": top_levels,
                "top_clusters": top_clusters,
                "updated_at": now_iso,
            }
        )

    digest_rows.sort(
        key=lambda row: (
            LEVEL_ORDER.get(str(row.get("risk_level", "L1")), 1),
            int(row.get("signal_count_24h", 0)),
        ),
        reverse=True,
    )

    supabase.table("ticker_signal_digest").delete().neq("ticker", "").execute()
    if digest_rows:
        supabase.table("ticker_signal_digest").insert(digest_rows).execute()

    logger.info(
        "[MARKET_DIGEST_DONE] "
        f"snapshot_risk={risk_level} ticker_rows={len(digest_rows)} "
        f"signals={len(signals)} clusters={len(clusters)}"
    )

    return {
        "risk_level": risk_level,
        "signals": len(signals),
        "clusters": len(clusters),
        "ticker_rows": len(digest_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="刷新移动端 market digest 聚合")
    parser.add_argument("--hours", type=int, default=24, help="统计窗口小时数")
    parser.add_argument("--limit", type=int, default=400, help="最大读取记录数")
    args = parser.parse_args()

    try:
        metrics = refresh_market_digest(hours=args.hours, limit=args.limit)
        logger.info(
            "[MARKET_DIGEST_METRICS] "
            + ", ".join([f"{key}={value}" for key, value in metrics.items()])
        )
    except Exception as e:
        logger.error(f"[MARKET_DIGEST_FAILED] error={str(e)[:200]}")
        raise


if __name__ == "__main__":
    main()
