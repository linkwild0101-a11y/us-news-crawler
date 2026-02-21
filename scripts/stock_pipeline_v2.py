#!/usr/bin/env python3
"""Stock V2 专用分析流水线（增量 + 回填）。"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from supabase import Client, create_client

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from scripts.llm_client import LLMClient
except Exception:
    LLMClient = None

try:
    from scripts.refresh_market_digest import _fetch_market_prices
except Exception:
    _fetch_market_prices = None

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

TICKER_PATTERN = re.compile(r"\b[A-Z]{2,5}\b")
TRACKED_TICKERS: Set[str] = {
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
    "納斯達克",
    "道琼斯",
    "道瓊斯",
    "标普",
    "標普",
    "华尔街",
    "華爾街",
    "财报",
    "財報",
    "earnings",
    "guidance",
    "fed",
    "fomc",
    "yield",
    "treasury",
    "ipo",
    "buyback",
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
    "突破",
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
    "下跌",
]
EVENT_RULES: Sequence[Tuple[str, Sequence[str], int]] = (
    ("earnings", ("财报", "財報", "earnings", "guidance"), 96),
    ("macro", ("fed", "fomc", "yield", "treasury", "cpi", "pce"), 120),
    ("policy", ("监管", "ban", "sanction", "antitrust", "诉讼"), 120),
    ("flow", ("etf", "inflow", "outflow", "buyback", "回购"), 96),
    ("sector", ("半导体", "semiconductor", "ai", "cloud"), 96),
)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(value: Any, fallback: Optional[str] = None) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return fallback or _now_utc().isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp(value: float, left: float, right: float) -> float:
    return max(left, min(right, value))


def _risk_level(score: float) -> str:
    if score >= 82:
        return "L4"
    if score >= 72:
        return "L3"
    if score >= 60:
        return "L2"
    if score >= 45:
        return "L1"
    return "L0"


def _hash_text(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


class StockPipelineV2:
    """Stock V2 增量/回填引擎。"""

    def __init__(self, enable_llm: bool = False, llm_workers: int = 1):
        self.supabase = self._init_supabase()
        self.enable_llm = enable_llm
        self.llm_client = self._init_llm_client(enable_llm)
        self.llm_workers = max(1, llm_workers)
        self.stats: Dict[str, int] = defaultdict(int)

    def _init_supabase(self) -> Client:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("缺少 SUPABASE_URL / SUPABASE_KEY")
        return create_client(url, key)

    def _init_llm_client(self, enable_llm: bool) -> Optional[Any]:
        if not enable_llm:
            return None
        if LLMClient is None:
            logger.warning("[V2_LLM_DISABLED] LLMClient 不可用，降级规则模式")
            return None
        try:
            return LLMClient()
        except Exception as e:
            logger.warning(f"[V2_LLM_DISABLED] LLM 初始化失败: {str(e)[:160]}")
            return None

    def _extract_tickers(self, text: str) -> Set[str]:
        found: Set[str] = set()
        for token in TICKER_PATTERN.findall(text.upper()):
            if token in TRACKED_TICKERS:
                found.add(token)
        return found

    def _is_stock_article(self, article: Dict[str, Any]) -> bool:
        payload = " ".join(
            [
                str(article.get("title") or ""),
                str(article.get("content") or "")[:1200],
                str(article.get("category") or ""),
            ]
        )
        if self._extract_tickers(payload):
            return True
        upper = payload.upper()
        return any(word.upper() in upper for word in STOCK_HINTS)

    def _classify_event(self, text: str) -> Tuple[str, int]:
        lower = text.lower()
        for event_type, keywords, ttl_hours in EVENT_RULES:
            if any(word.lower() in lower for word in keywords):
                return event_type, ttl_hours
        return "news", 72

    def _direction_strength(self, text: str) -> Tuple[str, float, float]:
        lower = text.lower()
        bull = sum(1 for word in BULLISH_HINTS if word in lower)
        bear = sum(1 for word in BEARISH_HINTS if word in lower)
        total = bull + bear
        if total == 0:
            return "NEUTRAL", 0.45, 0.0
        bias = (bull - bear) / max(1, total)
        direction = "LONG" if bias > 0.1 else "SHORT" if bias < -0.1 else "NEUTRAL"
        strength = _clamp(0.45 + abs(bias) * 0.45, 0.35, 0.95)
        return direction, strength, bias

    def _llm_adjust(
        self,
        title: str,
        content: str,
        base_direction: str,
        base_strength: float,
    ) -> Tuple[str, float, str, bool, str, str]:
        """使用 LLM 修正方向/强度，失败时自动回退。"""
        if not self.llm_client:
            short = title[:160]
            return base_direction, base_strength, short, False, short, short

        prompt = (
            "你是美股事件分析器。根据标题和正文判断交易方向与强度，并翻译成中文。"
            "请只输出 JSON："
            "{\"direction\":\"LONG|SHORT|NEUTRAL\",\"strength\":0-1,"
            "\"title_zh\":\"<=40字\",\"summary_zh\":\"<=80字\"}。\n"
            f"标题: {title[:220]}\n"
            f"正文摘要: {content[:1200]}\n"
            f"规则基线: direction={base_direction}, strength={base_strength:.2f}"
        )
        try:
            result = self.llm_client.summarize(prompt, use_cache=True)
            direction = str(result.get("direction") or base_direction).upper()
            if direction not in ("LONG", "SHORT", "NEUTRAL"):
                direction = base_direction
            llm_strength = _clamp(_safe_float(result.get("strength"), base_strength), 0.0, 1.0)
            strength = _clamp(base_strength * 0.7 + llm_strength * 0.3, 0.0, 1.0)
            title_zh = str(result.get("title_zh") or "").strip()[:180]
            summary_zh = str(
                result.get("summary_zh") or result.get("summary") or title
            ).strip()[:220]
            summary = summary_zh or title[:180]
            return direction, strength, summary, True, (title_zh or title[:180]), summary
        except Exception as e:
            logger.warning(f"[V2_LLM_FALLBACK] error={str(e)[:120]}")
            short = title[:160]
            return base_direction, base_strength, short, False, short, short

    def _load_articles_batch(
        self,
        offset: int,
        batch_size: int,
        fetched_after: Optional[str],
    ) -> List[Dict[str, Any]]:
        query = (
            self.supabase.table("articles")
            .select("id,title,content,url,category,source_id,published_at,fetched_at,analyzed_at")
            .not_.is_("analyzed_at", "null")
            .order("id", desc=True)
            .range(offset, offset + batch_size - 1)
        )
        if fetched_after:
            query = query.gte("fetched_at", fetched_after)
        return query.execute().data or []

    def _build_events(
        self,
        articles: List[Dict[str, Any]],
        run_id: str,
        now_iso: str,
        llm_budget: int,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int]:
        event_rows: List[Dict[str, Any]] = []
        raw_map_rows: List[Dict[str, Any]] = []
        llm_candidates: List[Tuple[int, str, str, str, float]] = []

        for article in articles:
            self.stats["articles_seen"] += 1
            if not self._is_stock_article(article):
                continue
            self.stats["articles_stock_related"] += 1

            title = str(article.get("title") or "")[:240]
            content = str(article.get("content") or "")
            payload = f"{title} {content[:1800]}"
            tickers = self._extract_tickers(payload)

            if not tickers and any(word in payload.lower() for word in ("fed", "fomc", "yield")):
                tickers = {"SPY", "QQQ", "DIA"}
            if not tickers:
                continue

            event_type, ttl_hours = self._classify_event(payload)
            base_direction, base_strength, bias = self._direction_strength(payload)
            direction = base_direction
            strength = base_strength
            summary = title or "美股事件"

            article_id = int(article.get("id") or 0)
            event_key = f"article:{article_id}:{_hash_text(title)}"
            source_ref = str(article.get("url") or f"article:{article_id}")[:128]
            published_at = _to_iso(article.get("published_at"), fallback=now_iso)

            event_rows.append(
                {
                    "event_key": event_key,
                    "source_type": "article",
                    "source_ref": source_ref,
                    "event_type": event_type,
                    "direction": direction,
                    "strength": round(strength, 4),
                    "ttl_hours": ttl_hours,
                    "summary": summary,
                    "details": {
                        "article_id": article_id,
                        "title": title,
                        "category": article.get("category"),
                        "source_id": article.get("source_id"),
                        "bias": round(bias, 4),
                        "llm_used": False,
                        "title_zh": "",
                        "summary_zh": "",
                    },
                    "published_at": published_at,
                    "as_of": now_iso,
                    "run_id": run_id,
                    "is_active": True,
                }
            )
            event_idx = len(event_rows) - 1
            if self.llm_client and llm_budget > 0:
                llm_candidates.append((event_idx, title, content, base_direction, base_strength))
                llm_budget -= 1

            for ticker in sorted(tickers):
                raw_map_rows.append(
                    {
                        "event_key": event_key,
                        "ticker": ticker,
                        "role": "primary",
                        "weight": 1.0,
                        "confidence": round(_clamp(0.45 + strength * 0.45, 0.4, 0.95), 4),
                        "as_of": now_iso,
                        "run_id": run_id,
                    }
                )

        llm_used_count = self._apply_llm_adjustments(event_rows, llm_candidates)
        return event_rows, raw_map_rows, llm_used_count

    def _apply_llm_adjustments(
        self,
        event_rows: List[Dict[str, Any]],
        llm_candidates: List[Tuple[int, str, str, str, float]],
    ) -> int:
        if not self.llm_client or not llm_candidates:
            return 0

        used_count = 0
        worker_count = min(self.llm_workers, len(llm_candidates))

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {
                executor.submit(
                    self._llm_adjust,
                    title,
                    content,
                    base_direction,
                    base_strength,
                ): event_idx
                for event_idx, title, content, base_direction, base_strength in llm_candidates
            }
            for future in as_completed(future_map):
                event_idx = future_map[future]
                try:
                    direction, strength, summary, llm_used, title_zh, summary_zh = future.result()
                except Exception:
                    continue
                row = event_rows[event_idx]
                row["direction"] = direction
                row["strength"] = round(strength, 4)
                row["summary"] = summary
                details = row.get("details") or {}
                details["llm_used"] = bool(llm_used)
                details["title_zh"] = str(title_zh or details.get("title") or "")[:180]
                details["summary_zh"] = str(summary_zh or summary or "")[:220]
                row["details"] = details
                if llm_used:
                    used_count += 1
        return used_count

    def _upsert_events(
        self,
        event_rows: List[Dict[str, Any]],
        raw_map_rows: List[Dict[str, Any]],
    ) -> Tuple[int, int]:
        if not event_rows:
            return 0, 0

        self.supabase.table("stock_events_v2").upsert(
            event_rows,
            on_conflict="event_key",
        ).execute()

        keys = [row["event_key"] for row in event_rows]
        id_rows = (
            self.supabase.table("stock_events_v2")
            .select("id,event_key")
            .in_("event_key", keys)
            .execute()
            .data
            or []
        )
        key_to_id = {str(row.get("event_key")): int(row.get("id") or 0) for row in id_rows}
        map_rows: List[Dict[str, Any]] = []

        for row in raw_map_rows:
            event_id = key_to_id.get(row["event_key"])
            if not event_id:
                continue
            map_rows.append(
                {
                    "event_id": event_id,
                    "ticker": row["ticker"],
                    "role": row["role"],
                    "weight": row["weight"],
                    "confidence": row["confidence"],
                    "as_of": row["as_of"],
                    "run_id": row["run_id"],
                }
            )

        if map_rows:
            self.supabase.table("stock_event_tickers_v2").upsert(
                map_rows,
                on_conflict="event_id,ticker,role",
            ).execute()

        return len(event_rows), len(map_rows)

    def _load_event_bundle(self, lookback_hours: int) -> List[Dict[str, Any]]:
        cutoff_iso = (_now_utc() - timedelta(hours=lookback_hours)).isoformat()
        event_rows = (
            self.supabase.table("stock_events_v2")
            .select("id,event_type,direction,strength,summary,published_at,as_of")
            .eq("is_active", True)
            .gte("as_of", cutoff_iso)
            .order("as_of", desc=True)
            .limit(4000)
            .execute()
            .data
            or []
        )
        if not event_rows:
            return []

        event_ids = [int(row.get("id") or 0) for row in event_rows if int(row.get("id") or 0) > 0]
        map_rows = (
            self.supabase.table("stock_event_tickers_v2")
            .select("event_id,ticker,weight,confidence")
            .in_("event_id", event_ids)
            .execute()
            .data
            or []
        )

        event_map = {int(row.get("id") or 0): row for row in event_rows}
        bundle: List[Dict[str, Any]] = []
        for row in map_rows:
            event_id = int(row.get("event_id") or 0)
            event_row = event_map.get(event_id)
            if not event_row:
                continue
            bundle.append(
                {
                    "event_id": event_id,
                    "ticker": str(row.get("ticker") or "").upper(),
                    "weight": _safe_float(row.get("weight"), 1.0),
                    "map_confidence": _safe_float(row.get("confidence"), 0.5),
                    "event_type": str(event_row.get("event_type") or "news"),
                    "direction": str(event_row.get("direction") or "NEUTRAL"),
                    "strength": _safe_float(event_row.get("strength"), 0.45),
                    "summary": str(event_row.get("summary") or ""),
                    "published_at": _to_iso(event_row.get("published_at")),
                }
            )
        return bundle

    def _build_signals(
        self,
        event_bundle: List[Dict[str, Any]],
        run_id: str,
        now: datetime,
    ) -> List[Dict[str, Any]]:
        by_ticker: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in event_bundle:
            ticker = str(row.get("ticker") or "")
            if ticker:
                by_ticker[ticker].append(row)

        signal_rows: List[Dict[str, Any]] = []
        for ticker, rows in by_ticker.items():
            if not rows:
                continue

            pos = 0.0
            neg = 0.0
            counts: Counter[str] = Counter()
            source_event_ids: List[int] = []
            sorted_rows = sorted(rows, key=lambda item: item.get("published_at", ""), reverse=True)

            for row in sorted_rows[:24]:
                value = row["strength"] * row["weight"] * row["map_confidence"]
                if row["direction"] == "LONG":
                    pos += value
                elif row["direction"] == "SHORT":
                    neg += value
                source_event_ids.append(int(row["event_id"]))
                counts[str(row["event_type"])] += 1

            event_count = len(rows)
            net = pos - neg
            side = "LONG" if net >= 0 else "SHORT"
            magnitude = _clamp(abs(net) / max(0.1, pos + neg), 0.0, 1.0)
            score = _clamp(42 + magnitude * 38 + min(event_count, 10) * 2.2, 0.0, 100.0)
            level = _risk_level(score)
            confidence = _clamp(0.44 + magnitude * 0.26 + min(event_count, 8) * 0.03, 0.4, 0.95)
            expire_hours = 96 if level in ("L3", "L4") else 72
            trigger_factors = [
                {"event_type": name, "count": count}
                for name, count in counts.most_common(3)
            ]
            explanation = str(sorted_rows[0].get("summary") or f"{ticker} 事件聚合")[:220]

            signal_rows.append(
                {
                    "signal_key": f"{ticker}:{run_id}",
                    "ticker": ticker,
                    "level": level,
                    "side": side,
                    "signal_score": round(score, 2),
                    "confidence": round(confidence, 4),
                    "trigger_factors": trigger_factors,
                    "llm_used": bool(self.llm_client),
                    "explanation": explanation,
                    "source_event_ids": source_event_ids[:20],
                    "expires_at": (now + timedelta(hours=expire_hours)).isoformat(),
                    "as_of": now.isoformat(),
                    "run_id": run_id,
                    "is_active": True,
                }
            )

        signal_rows.sort(key=lambda row: float(row.get("signal_score", 0.0)), reverse=True)
        return signal_rows

    def _build_regime(self, run_id: str, now: datetime) -> Dict[str, Any]:
        prices: Dict[str, Any] = {}
        if _fetch_market_prices is not None:
            try:
                prices = _fetch_market_prices() or {}
            except Exception as e:
                logger.warning(f"[V2_MARKET_PRICE_FALLBACK] error={str(e)[:120]}")

        vix = _safe_float(prices.get("vix"), 19.0)
        us10y = _safe_float(prices.get("us10y"), 4.1)
        dxy = _safe_float(prices.get("dxy"), 103.0)

        score = 0.0
        if vix <= 16:
            score += 0.35
        elif vix >= 24:
            score -= 0.45
        if us10y <= 4.0:
            score += 0.25
        elif us10y >= 4.7:
            score -= 0.25
        if dxy <= 101:
            score += 0.2
        elif dxy >= 106:
            score -= 0.2

        score = _clamp(score, -1.0, 1.0)
        risk_state = "risk_on" if score >= 0.2 else "risk_off" if score <= -0.2 else "neutral"
        vol_state = "high_vol" if vix >= 24 else "low_vol" if vix <= 16 else "mid_vol"
        liquidity_state = "tight" if us10y >= 4.7 else "loose" if us10y <= 4.0 else "neutral"

        return {
            "regime_date": now.date().isoformat(),
            "risk_state": risk_state,
            "vol_state": vol_state,
            "liquidity_state": liquidity_state,
            "regime_score": round(score, 4),
            "summary": f"状态:{risk_state} | VIX:{vix:.2f} | 10Y:{us10y:.2f}% | DXY:{dxy:.2f}",
            "source_payload": prices,
            "as_of": now.isoformat(),
            "run_id": run_id,
            "is_active": True,
        }

    def _build_opportunities(
        self,
        signals: List[Dict[str, Any]],
        regime: Dict[str, Any],
        run_id: str,
        now: datetime,
    ) -> List[Dict[str, Any]]:
        regime_score = _safe_float(regime.get("regime_score"), 0.0)
        rows: List[Dict[str, Any]] = []
        for signal in signals:
            side = str(signal.get("side") or "LONG")
            signal_score = _safe_float(signal.get("signal_score"), 0.0)
            confidence = _safe_float(signal.get("confidence"), 0.5)
            macro_boost = regime_score if side == "LONG" else -regime_score
            horizon = "A" if signal_score >= 65 else "B"
            opp_score = _clamp(signal_score * 0.82 + (macro_boost + 1.0) * 9.0, 0.0, 100.0)
            opp_conf = _clamp(confidence * 0.82 + 0.13, 0.4, 0.95)
            expiry = now + timedelta(hours=72 if horizon == "A" else 24 * 14)

            if side == "LONG":
                invalid_if = "若风险偏好转弱且相关事件显著减少，则机会失效。"
            else:
                invalid_if = "若风险偏好快速修复且负面事件衰减，则机会失效。"

            rows.append(
                {
                    "opportunity_key": f"{signal['ticker']}:{side}:{horizon}:{run_id}",
                    "ticker": signal["ticker"],
                    "side": side,
                    "horizon": horizon,
                    "opportunity_score": round(opp_score, 2),
                    "confidence": round(opp_conf, 4),
                    "risk_level": signal.get("level", "L1"),
                    "why_now": (
                        f"{signal['ticker']} 当前信号分 {signal_score:.1f}，方向 {side}，"
                        f"市场状态 {regime.get('risk_state', 'neutral')}。"
                    ),
                    "invalid_if": invalid_if,
                    "catalysts": signal.get("trigger_factors") or [],
                    "source_signal_ids": [],
                    "source_event_ids": signal.get("source_event_ids") or [],
                    "expires_at": expiry.isoformat(),
                    "as_of": now.isoformat(),
                    "run_id": run_id,
                    "is_active": True,
                }
            )
        rows.sort(key=lambda row: float(row.get("opportunity_score", 0.0)), reverse=True)
        return rows[:80]

    def _replace_active(self, table_name: str, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        self.supabase.table(table_name).update({"is_active": False}).eq("is_active", True).execute()
        self.supabase.table(table_name).insert(rows).execute()
        return len(rows)

    def _build_snapshot(
        self,
        opportunities: List[Dict[str, Any]],
        signals: List[Dict[str, Any]],
        regime: Dict[str, Any],
        run_id: str,
        now: datetime,
    ) -> Dict[str, Any]:
        risk_badge = "L1"
        if signals:
            risk_badge = max([str(item.get("level") or "L1") for item in signals])
        return {
            "snapshot_time": now.isoformat(),
            "top_opportunities": [
                {
                    "ticker": row["ticker"],
                    "side": row["side"],
                    "horizon": row["horizon"],
                    "score": row["opportunity_score"],
                    "confidence": row["confidence"],
                }
                for row in opportunities[:12]
            ],
            "top_signals": [
                {
                    "ticker": row["ticker"],
                    "side": row["side"],
                    "level": row["level"],
                    "score": row["signal_score"],
                }
                for row in signals[:16]
            ],
            "market_brief": (
                f"Stock V2 已生成 {len(opportunities)} 个机会、{len(signals)} 条信号，"
                f"市场状态 {regime.get('risk_state', 'neutral')}。"
            ),
            "risk_badge": risk_badge,
            "data_health": {
                "opportunities": len(opportunities),
                "signals": len(signals),
                "risk_state": regime.get("risk_state", "neutral"),
                "generated_at": now.isoformat(),
            },
            "as_of": now.isoformat(),
            "run_id": run_id,
            "is_active": True,
        }

    def refresh_serve_layer(self, run_id: str, lookback_hours: int) -> Dict[str, int]:
        """从事件层重建信号/机会/快照。"""
        now = _now_utc()
        regime = self._build_regime(run_id=run_id, now=now)
        self._replace_active("stock_market_regime_v2", [regime])

        bundle = self._load_event_bundle(lookback_hours=lookback_hours)
        signal_rows = self._build_signals(bundle, run_id=run_id, now=now)
        if not signal_rows:
            logger.warning("[V2_KEEP_OLD] 未生成新信号，本轮仅刷新市场状态和快照")
            snapshot = self._build_snapshot([], [], regime, run_id=run_id, now=now)
            self._replace_active("stock_dashboard_snapshot_v2", [snapshot])
            return {"signals": 0, "opportunities": 0, "snapshot": 1}

        signal_count = self._replace_active("stock_signals_v2", signal_rows)
        opp_rows = self._build_opportunities(signal_rows, regime, run_id=run_id, now=now)
        opp_count = self._replace_active("stock_opportunities_v2", opp_rows)
        snapshot = self._build_snapshot(opp_rows, signal_rows, regime, run_id=run_id, now=now)
        snap_count = self._replace_active("stock_dashboard_snapshot_v2", [snapshot])
        return {"signals": signal_count, "opportunities": opp_count, "snapshot": snap_count}

    def run_incremental(
        self,
        hours: int = 48,
        article_limit: int = 1200,
        llm_event_cap: int = 60,
        lookback_hours: int = 168,
    ) -> Dict[str, Any]:
        """执行增量计算。"""
        run_id = f"inc-{_now_utc().strftime('%Y%m%d%H%M%S')}"
        cutoff_iso = (_now_utc() - timedelta(hours=hours)).isoformat()
        logger.info(
            f"[STOCK_V2_INCREMENTAL_START] run_id={run_id} hours={hours} limit={article_limit}"
        )

        offset = 0
        page_size = 500
        remaining = article_limit
        llm_budget = llm_event_cap
        all_events: List[Dict[str, Any]] = []
        all_mappings: List[Dict[str, Any]] = []

        while remaining > 0:
            current_size = min(page_size, remaining)
            rows = self._load_articles_batch(
                offset=offset,
                batch_size=current_size,
                fetched_after=cutoff_iso,
            )
            if not rows:
                break

            events, mappings, llm_used = self._build_events(
                rows,
                run_id=run_id,
                now_iso=_now_utc().isoformat(),
                llm_budget=llm_budget,
            )
            llm_budget -= llm_used
            all_events.extend(events)
            all_mappings.extend(mappings)

            offset += current_size
            remaining -= len(rows)
            if len(rows) < current_size:
                break

        event_count = 0
        mapping_count = 0
        if all_events:
            event_count, mapping_count = self._upsert_events(all_events, all_mappings)
        else:
            logger.warning("[STOCK_V2_NO_EVENTS] 本轮未发现可用事件")

        serve_stats = self.refresh_serve_layer(run_id=run_id, lookback_hours=lookback_hours)
        logger.info(
            "[STOCK_V2_INCREMENTAL_DONE] "
            f"articles_seen={self.stats['articles_seen']} "
            f"stock_articles={self.stats['articles_stock_related']} "
            f"events={event_count} mappings={mapping_count} "
            f"signals={serve_stats['signals']} opps={serve_stats['opportunities']}"
        )
        return {
            "run_id": run_id,
            "articles_seen": self.stats["articles_seen"],
            "stock_articles": self.stats["articles_stock_related"],
            "events_upserted": event_count,
            "mappings_upserted": mapping_count,
            "signals_written": serve_stats["signals"],
            "opportunities_written": serve_stats["opportunities"],
        }

    def run_backfill(
        self,
        batch_size: int = 500,
        max_articles: Optional[int] = None,
        llm_event_cap: int = 0,
        lookback_hours: int = 336,
    ) -> Dict[str, Any]:
        """执行全量回填。"""
        run_id = f"backfill-{_now_utc().strftime('%Y%m%d%H%M%S')}"
        logger.info(
            f"[STOCK_V2_BACKFILL_START] run_id={run_id} batch={batch_size} max={max_articles}"
        )

        offset = 0
        processed = 0
        llm_budget = llm_event_cap
        total_events = 0
        total_mappings = 0

        while True:
            if max_articles is not None and processed >= max_articles:
                break
            current_size = batch_size
            if max_articles is not None:
                current_size = min(batch_size, max_articles - processed)
            rows = self._load_articles_batch(offset=offset, batch_size=current_size, fetched_after=None)
            if not rows:
                break

            events, mappings, llm_used = self._build_events(
                rows,
                run_id=run_id,
                now_iso=_now_utc().isoformat(),
                llm_budget=llm_budget,
            )
            llm_budget -= llm_used

            event_count, mapping_count = self._upsert_events(events, mappings)
            total_events += event_count
            total_mappings += mapping_count
            processed += len(rows)
            offset += current_size

            logger.info(
                f"[STOCK_V2_BACKFILL_PROGRESS] processed={processed} events={total_events}"
            )
            if len(rows) < current_size:
                break

        serve_stats = self.refresh_serve_layer(run_id=run_id, lookback_hours=lookback_hours)
        logger.info(
            "[STOCK_V2_BACKFILL_DONE] "
            f"processed={processed} stock_articles={self.stats['articles_stock_related']} "
            f"events={total_events} signals={serve_stats['signals']} "
            f"opps={serve_stats['opportunities']}"
        )
        return {
            "run_id": run_id,
            "processed_articles": processed,
            "stock_articles": self.stats["articles_stock_related"],
            "events_upserted": total_events,
            "mappings_upserted": total_mappings,
            "signals_written": serve_stats["signals"],
            "opportunities_written": serve_stats["opportunities"],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock V2 分析流水线")
    parser.add_argument("--mode", choices=["incremental", "backfill"], default="incremental")
    parser.add_argument("--hours", type=int, default=48, help="增量窗口小时")
    parser.add_argument("--article-limit", type=int, default=1200, help="增量最大文章数")
    parser.add_argument("--batch-size", type=int, default=500, help="回填批大小")
    parser.add_argument("--max-articles", type=int, default=None, help="回填最大文章数")
    parser.add_argument("--lookback-hours", type=int, default=168, help="信号聚合回看小时")
    parser.add_argument("--enable-llm", action="store_true", help="启用 LLM 修正")
    parser.add_argument("--llm-event-cap", type=int, default=60, help="本轮最多 LLM 事件数")
    parser.add_argument("--llm-workers", type=int, default=1, help="LLM 并发 worker 数")
    args = parser.parse_args()

    engine = StockPipelineV2(enable_llm=args.enable_llm, llm_workers=args.llm_workers)
    if args.mode == "incremental":
        metrics = engine.run_incremental(
            hours=args.hours,
            article_limit=args.article_limit,
            llm_event_cap=args.llm_event_cap,
            lookback_hours=args.lookback_hours,
        )
    else:
        metrics = engine.run_backfill(
            batch_size=args.batch_size,
            max_articles=args.max_articles,
            llm_event_cap=args.llm_event_cap,
            lookback_hours=max(args.lookback_hours, 336),
        )
    logger.info("[STOCK_V2_METRICS] " + ", ".join([f"{key}={value}" for key, value in metrics.items()]))


if __name__ == "__main__":
    main()
