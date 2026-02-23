#!/usr/bin/env python3
"""Stock V2 专用分析流水线（增量 + 回填）。"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse

from supabase import Client, create_client

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.feature_flags import FeatureFlags

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

TICKER_TO_INDUSTRY: Dict[str, str] = {
    "SPY": "Index",
    "QQQ": "Index",
    "DIA": "Index",
    "IWM": "Index",
    "VTI": "Index",
    "VOO": "Index",
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
    "TLT": "Rates",
    "AAPL": "Technology",
    "MSFT": "Technology",
    "NVDA": "Semiconductors",
    "AMZN": "Consumer Discretionary",
    "GOOGL": "Technology",
    "META": "Technology",
    "TSLA": "Automotive",
}

DEFAULT_MACRO_FACTORS: List[Dict[str, Any]] = [
    {
        "factor": "rates",
        "label": "利率",
        "keywords": ["yield", "10y", "rates", "加息", "降息", "fomc", "fed"],
    },
    {
        "factor": "inflation",
        "label": "通胀",
        "keywords": ["cpi", "pce", "inflation", "通胀", "物价"],
    },
    {
        "factor": "oil",
        "label": "油价",
        "keywords": ["oil", "crude", "wti", "brent", "原油", "油价"],
    },
    {
        "factor": "fx",
        "label": "美元汇率",
        "keywords": ["dxy", "dollar", "usd", "汇率", "美元"],
    },
    {
        "factor": "policy",
        "label": "政策监管",
        "keywords": ["policy", "regulation", "监管", "制裁", "antitrust", "tariff", "关税"],
    },
]


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
        self.macro_factors = self._load_macro_factor_config()
        self.flags = FeatureFlags.from_env()
        self.stats: Dict[str, int] = defaultdict(int)
        logger.info(
            "[FEATURE_FLAGS] "
            f"ENABLE_STOCK_V3_RUN_LOG={self.flags.enable_stock_v3_run_log} "
            f"ENABLE_STOCK_V3_EVAL={self.flags.enable_stock_v3_eval} "
            f"ENABLE_STOCK_V3_PAPER={self.flags.enable_stock_v3_paper} "
            f"ENABLE_STOCK_V3_CHALLENGER={self.flags.enable_stock_v3_challenger} "
            f"ENABLE_STOCK_V3_DRIFT={self.flags.enable_stock_v3_drift} "
            f"ENABLE_STOCK_V3_LIFECYCLE={self.flags.enable_stock_v3_lifecycle} "
            f"ENABLE_STOCK_V3_SUBSCRIPTION_ALERT="
            f"{self.flags.enable_stock_v3_subscription_alert} "
            f"ENABLE_STOCK_EVIDENCE_LAYER={self.flags.enable_stock_evidence_layer} "
            f"ENABLE_STOCK_TRANSMISSION_LAYER={self.flags.enable_stock_transmission_layer} "
            f"ENABLE_STOCK_AI_DEBATE_VIEW={self.flags.enable_stock_ai_debate_view}"
        )

    def _build_v3_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(params)
        merged["enable_llm"] = self.enable_llm
        merged["llm_workers"] = self.llm_workers
        merged["flag_enable_stock_v3_run_log"] = self.flags.enable_stock_v3_run_log
        merged["flag_enable_stock_v3_eval"] = self.flags.enable_stock_v3_eval
        merged["flag_enable_stock_v3_paper"] = self.flags.enable_stock_v3_paper
        merged["flag_enable_stock_v3_challenger"] = self.flags.enable_stock_v3_challenger
        merged["flag_enable_stock_v3_drift"] = self.flags.enable_stock_v3_drift
        merged["flag_enable_stock_v3_lifecycle"] = self.flags.enable_stock_v3_lifecycle
        merged["flag_enable_stock_v3_subscription_alert"] = (
            self.flags.enable_stock_v3_subscription_alert
        )
        merged["flag_enable_stock_evidence_layer"] = self.flags.enable_stock_evidence_layer
        merged["flag_enable_stock_transmission_layer"] = self.flags.enable_stock_transmission_layer
        merged["flag_enable_stock_ai_debate_view"] = self.flags.enable_stock_ai_debate_view
        return merged

    def _v3_log_run_start(
        self,
        run_id: str,
        pipeline_name: str,
        started_at: datetime,
        input_window: Dict[str, Any],
        params_json: Dict[str, Any],
    ) -> None:
        if not self.flags.enable_stock_v3_run_log:
            return
        payload = {
            "run_id": run_id,
            "pipeline_name": pipeline_name,
            "pipeline_version": os.getenv("GITHUB_SHA", "")[:12] or "local",
            "trigger_type": os.getenv("GITHUB_EVENT_NAME", "manual"),
            "status": "running",
            "started_at": started_at.isoformat(),
            "input_window": input_window,
            "params_json": params_json,
            "commit_sha": os.getenv("GITHUB_SHA", "")[:40],
            "as_of": _now_utc().isoformat(),
        }
        try:
            self.supabase.table("research_runs").upsert(
                payload,
                on_conflict="run_id",
            ).execute()
        except Exception as e:
            logger.warning(f"[V3_RUN_LOG_START_FAILED] run_id={run_id} error={str(e)[:120]}")

    def _v3_log_run_finish(
        self,
        run_id: str,
        started_at: datetime,
        status: str,
        metrics: Dict[str, Any],
        notes: str = "",
    ) -> None:
        if not self.flags.enable_stock_v3_run_log:
            return

        ended_at = _now_utc()
        duration_sec = max(0, int((ended_at - started_at).total_seconds()))
        status = status if status in ("success", "failed", "degraded") else "failed"

        try:
            (
                self.supabase.table("research_runs")
                .update(
                    {
                        "status": status,
                        "ended_at": ended_at.isoformat(),
                        "duration_sec": duration_sec,
                        "notes": notes[:1000],
                        "as_of": ended_at.isoformat(),
                    }
                )
                .eq("run_id", run_id)
                .execute()
            )
        except Exception as e:
            logger.warning(f"[V3_RUN_LOG_FINISH_FAILED] run_id={run_id} error={str(e)[:120]}")

        rows = []
        for key, value in metrics.items():
            try:
                number = float(value)
            except Exception:
                continue
            rows.append(
                {
                    "run_id": run_id,
                    "metric_name": str(key)[:64],
                    "metric_value": number,
                    "metric_unit": "count",
                }
            )
        if not rows:
            return
        try:
            self.supabase.table("research_run_metrics").upsert(
                rows,
                on_conflict="run_id,metric_name",
            ).execute()
        except Exception as e:
            logger.warning(f"[V3_RUN_METRICS_FAILED] run_id={run_id} error={str(e)[:120]}")

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

    def _load_macro_factor_config(self) -> List[Dict[str, Any]]:
        """加载宏观因子词典配置，缺失时回退默认值。"""
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config",
            "macro_factor_dictionary.json",
        )
        try:
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as fp:
                    payload = json.load(fp)
                rows = payload.get("factors") if isinstance(payload, dict) else payload
                if isinstance(rows, list) and rows:
                    normalized: List[Dict[str, Any]] = []
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        factor = str(row.get("factor") or "").strip().lower()
                        label = str(row.get("label") or factor).strip()
                        keywords = [
                            str(item or "").strip().lower()
                            for item in (row.get("keywords") or [])
                            if str(item or "").strip()
                        ]
                        if factor and keywords:
                            normalized.append(
                                {
                                    "factor": factor,
                                    "label": label,
                                    "keywords": keywords,
                                }
                            )
                    if normalized:
                        logger.info(
                            f"[V2_MACRO_DICT_LOADED] path={config_path} factors={len(normalized)}"
                        )
                        return normalized
        except Exception as e:
            logger.warning(f"[V2_MACRO_DICT_FALLBACK] error={str(e)[:120]}")
        return [dict(item) for item in DEFAULT_MACRO_FACTORS]

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
        total_candidates = len(llm_candidates)
        started_at = time.perf_counter()
        milestones = {
            max(1, int(total_candidates * 0.25)),
            max(1, int(total_candidates * 0.5)),
            max(1, int(total_candidates * 0.75)),
            total_candidates,
        }
        completed = 0
        logger.info(
            "[V2_LLM_PROGRESS_START] "
            f"candidates={total_candidates} workers={worker_count}"
        )

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
                completed += 1
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
                if completed in milestones:
                    elapsed = time.perf_counter() - started_at
                    eta = (
                        (elapsed / completed) * (total_candidates - completed)
                        if completed
                        else 0.0
                    )
                    logger.info(
                        "[V2_LLM_PROGRESS] "
                        f"done={completed}/{total_candidates} "
                        f"used={used_count} elapsed={elapsed:.1f}s eta={eta:.1f}s"
                    )
        elapsed = time.perf_counter() - started_at
        logger.info(
            "[V2_LLM_PROGRESS_DONE] "
            f"done={total_candidates}/{total_candidates} "
            f"used={used_count} elapsed={elapsed:.1f}s"
        )
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
            .select(
                "id,event_type,direction,strength,summary,published_at,as_of,"
                "source_type,source_ref,details"
            )
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
            details = event_row.get("details")
            detail_map = details if isinstance(details, dict) else {}
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
                    "source_type": str(event_row.get("source_type") or "article").strip().lower(),
                    "source_ref": str(event_row.get("source_ref") or "")[:256],
                    "source_handle": str(detail_map.get("handle") or "").strip(),
                }
            )
        return bundle

    def _to_int_list(self, value: Any, limit: int = 20) -> List[int]:
        """将任意数组值转换为 int 列表。"""
        if not isinstance(value, list):
            return []
        nums: List[int] = []
        for item in value:
            try:
                number = int(item)
            except Exception:
                continue
            if number > 0:
                nums.append(number)
            if len(nums) >= limit:
                break
        return nums

    def _extract_numeric_facts(self, text: str) -> List[Dict[str, Any]]:
        """从证据句段抽取数字事实，便于前端快速复核。"""
        if not text:
            return []

        facts: List[Dict[str, Any]] = []
        patterns = [
            ("percent", re.compile(r"(-?\d+(?:\.\d+)?)\s*%")),
            ("bps", re.compile(r"(-?\d+(?:\.\d+)?)\s*bps", re.IGNORECASE)),
            (
                "usd",
                re.compile(
                    r"(\$\s*\d+(?:\.\d+)?(?:\s*(?:bn|billion|m|million|trillion|t))?)",
                    re.IGNORECASE,
                ),
            ),
            ("number", re.compile(r"\b(-?\d+(?:\.\d+)?)\b")),
        ]
        for fact_type, pattern in patterns:
            for match in pattern.finditer(text):
                raw = match.group(0).strip()
                if not raw:
                    continue
                value = _safe_float(match.group(1), 0.0)
                facts.append(
                    {
                        "type": fact_type,
                        "raw": raw[:32],
                        "value": round(value, 4),
                    }
                )
                if len(facts) >= 5:
                    return facts
        return facts

    def _source_name_from_ref(self, source_ref: str, source_type: str) -> str:
        """将 source_ref 归一化为可读来源名。"""
        text = str(source_ref or "").strip()
        if text.startswith("http://") or text.startswith("https://"):
            host = (urlparse(text).hostname or "").strip().lower()
            if host.startswith("www."):
                host = host[4:]
            return host or "news"
        source_type_norm = str(source_type or "").strip().lower()
        if source_type_norm == "x_grok":
            return "x.com"
        return source_type_norm or "news"

    def _build_ai_debate_view(
        self,
        opportunity: Dict[str, Any],
        regime: Dict[str, Any],
    ) -> Dict[str, Any]:
        """构建机会的正反观点与不确定性摘要。"""
        side = str(opportunity.get("side") or "LONG").upper()
        ticker = str(opportunity.get("ticker") or "")
        source_mix = opportunity.get("source_mix")
        mix = source_mix if isinstance(source_mix, dict) else {}
        x_ratio = _clamp(_safe_float(mix.get("x_ratio"), 0.0), 0.0, 1.0)
        source_total = max(0, int(_safe_float(mix.get("source_total"), 0.0)))
        confidence = _clamp(_safe_float(opportunity.get("confidence"), 0.0), 0.0, 1.0)
        regime_state = str(regime.get("risk_state") or "neutral")

        pro_case = (
            f"{ticker} 当前方向为 {side}，主信号分与催化共振支持该判断。"
            f" 市场状态为 {regime_state}。"
        )
        if side == "LONG":
            counter_case = "若利率与美元同步走强，成长估值可能承压，机会兑现难度上升。"
        else:
            counter_case = "若流动性边际转松且风险偏好回升，空头逻辑可能快速失效。"

        uncertainties: List[str] = []
        if source_total <= 1:
            uncertainties.append("单源证据占比高，需补充交叉来源确认。")
        if x_ratio >= 0.7:
            uncertainties.append("X 信源占比偏高，短期情绪噪声可能放大波动。")
        if confidence < 0.55:
            uncertainties.append("模型置信度偏低，建议降低仓位并等待新增证据。")
        if regime_state == "neutral":
            uncertainties.append("宏观状态中性，方向延续性不确定。")
        if not uncertainties:
            uncertainties.append("需持续跟踪财报、政策与流动性变化。")

        pre_trade_checks = [
            "核对原文关键数字是否与二次传播一致。",
            "确认近24小时是否出现反向催化新闻。",
            "检查同板块 ETF 与龙头个股是否共振。",
        ]
        return {
            "pro_case": pro_case[:220],
            "counter_case": counter_case[:220],
            "uncertainties": uncertainties[:4],
            "pre_trade_checks": pre_trade_checks[:3],
        }

    def _build_evidence_rows(
        self,
        opportunities: List[Dict[str, Any]],
        events_by_ticker: Dict[str, List[Dict[str, Any]]],
        run_id: str,
        now: datetime,
    ) -> List[Dict[str, Any]]:
        """根据机会关联事件生成关键证据段落。"""
        rows: List[Dict[str, Any]] = []
        now_iso = now.isoformat()
        for opp in opportunities:
            opp_id = int(opp.get("id") or 0)
            if opp_id <= 0:
                continue
            ticker = str(opp.get("ticker") or "").upper()
            event_rows = events_by_ticker.get(ticker) or []
            if not event_rows:
                continue

            event_ids = set(self._to_int_list(opp.get("source_event_ids"), limit=12))
            selected = [
                row for row in event_rows
                if int(row.get("event_id") or 0) in event_ids
            ][:8]
            if not selected:
                selected = event_rows[:5]

            for row in selected:
                summary = str(row.get("summary") or "").strip()
                if not summary:
                    continue
                event_id = int(row.get("event_id") or 0)
                source_ref = str(row.get("source_ref") or "").strip()
                source_type = str(row.get("source_type") or "article").strip().lower()
                source_url = source_ref if source_ref.startswith("http") else ""
                snippet_hash = _hash_text(f"{opp_id}:{event_id}:{summary}")
                rows.append(
                    {
                        "opportunity_id": opp_id,
                        "ticker": ticker,
                        "source_type": source_type or "article",
                        "source_ref": source_ref[:128],
                        "source_url": source_url[:512],
                        "source_name": self._source_name_from_ref(source_ref, source_type)[:128],
                        "published_at": _to_iso(row.get("published_at"), fallback=now_iso),
                        "quote_snippet": summary[:560],
                        "numeric_facts": self._extract_numeric_facts(summary),
                        "entity_tags": [ticker],
                        "confidence": round(
                            _clamp(
                                _safe_float(row.get("map_confidence"), 0.5) * 0.55
                                + _safe_float(row.get("strength"), 0.45) * 0.45,
                                0.35,
                                0.95,
                            ),
                            4,
                        ),
                        "snippet_hash": snippet_hash,
                        "as_of": now_iso,
                        "run_id": run_id,
                        "is_active": True,
                    }
                )
        return rows

    def _build_transmission_rows(
        self,
        opportunities: List[Dict[str, Any]],
        events_by_ticker: Dict[str, List[Dict[str, Any]]],
        evidence_ids_by_opp: Dict[int, List[int]],
        run_id: str,
        now: datetime,
    ) -> List[Dict[str, Any]]:
        """基于宏观词典构建宏观→行业→个股传导链。"""
        rows: List[Dict[str, Any]] = []
        now_iso = now.isoformat()
        for opp in opportunities:
            opp_id = int(opp.get("id") or 0)
            if opp_id <= 0:
                continue
            ticker = str(opp.get("ticker") or "").upper()
            if not ticker:
                continue
            side = str(opp.get("side") or "LONG").upper()
            industry = TICKER_TO_INDUSTRY.get(ticker, "Unknown")
            summaries = [
                str(row.get("summary") or "").strip()
                for row in (events_by_ticker.get(ticker) or [])[:16]
                if str(row.get("summary") or "").strip()
            ]
            merged_text = " ".join(summaries).lower()
            if not merged_text:
                continue

            factor_hits: List[Tuple[float, Dict[str, Any]]] = []
            for factor in self.macro_factors:
                keywords = factor.get("keywords") or []
                hit_count = 0
                for word in keywords:
                    token = str(word or "").strip().lower()
                    if token and token in merged_text:
                        hit_count += 1
                if hit_count <= 0:
                    continue
                factor_hits.append((float(hit_count), factor))

            if not factor_hits:
                continue
            factor_hits.sort(key=lambda item: item[0], reverse=True)
            opp_evidence_ids = evidence_ids_by_opp.get(opp_id) or []
            for weight, factor in factor_hits[:3]:
                factor_label = str(factor.get("label") or factor.get("factor") or "").strip()
                factor_key = str(factor.get("factor") or factor_label).strip().lower() or "macro"
                strength = _clamp(
                    0.4 + min(4.0, weight) * 0.12 + _safe_float(opp.get("confidence"), 0.5) * 0.1,
                    0.35,
                    0.95,
                )
                rows.append(
                    {
                        "opportunity_id": opp_id,
                        "path_key": f"{run_id}:{opp_id}:{factor_key}",
                        "ticker": ticker,
                        "macro_factor": factor_label[:64] or factor_key[:64],
                        "industry": industry[:64],
                        "direction": side if side in ("LONG", "SHORT") else "NEUTRAL",
                        "strength": round(strength, 4),
                        "reason": (
                            f"{factor_label} 相关事件触发 {industry} 板块传导，"
                            f"{ticker} 在当前窗口呈现 {side} 倾向。"
                        )[:260],
                        "evidence_ids": opp_evidence_ids[:8],
                        "as_of": now_iso,
                        "run_id": run_id,
                        "is_active": True,
                    }
                )
        return rows

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
            source_counts: Counter[str] = Counter()
            x_handles: Counter[str] = Counter()
            source_event_ids: List[int] = []
            sorted_rows = sorted(rows, key=lambda item: item.get("published_at", ""), reverse=True)
            latest_x_at = ""
            latest_news_at = ""

            for row in sorted_rows[:24]:
                value = row["strength"] * row["weight"] * row["map_confidence"]
                if row["direction"] == "LONG":
                    pos += value
                elif row["direction"] == "SHORT":
                    neg += value
                source_event_ids.append(int(row["event_id"]))
                counts[str(row["event_type"])] += 1
                source_type = str(row.get("source_type") or "article").strip().lower()
                source_counts[source_type] += 1
                published_at = _to_iso(row.get("published_at"))
                if source_type == "x_grok":
                    if not latest_x_at:
                        latest_x_at = published_at
                    handle = str(row.get("source_handle") or "").strip()
                    if handle:
                        x_handles[handle] += 1
                elif source_type == "article" and not latest_news_at:
                    latest_news_at = published_at

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
            x_count = int(source_counts.get("x_grok", 0))
            article_count = int(source_counts.get("article", 0))
            other_count = max(0, sum(source_counts.values()) - x_count - article_count)
            source_total = max(1, x_count + article_count + other_count)
            x_ratio = round(x_count / source_total, 4)
            event_diversity = min(1.0, len(counts) / 3.0)
            count_density = min(1.0, event_count / 8.0)
            mixed_flag = bool(x_count > 0 and article_count > 0)
            resonance_score = _clamp(
                (0.5 if mixed_flag else 0.0) + event_diversity * 0.25 + count_density * 0.25,
                0.0,
                1.0,
            )
            top_x_handles = [name for name, _ in x_handles.most_common(3)]
            source_mix = {
                "x_count": x_count,
                "article_count": article_count,
                "other_count": other_count,
                "source_total": source_total,
                "x_ratio": x_ratio,
                "mixed_sources": mixed_flag,
                "resonance_score": round(resonance_score, 4),
                "top_x_handles": top_x_handles,
                "latest_x_at": latest_x_at,
                "latest_news_at": latest_news_at,
            }

            explanation = str(sorted_rows[0].get("summary") or f"{ticker} 事件聚合")[:220]
            if x_count > 0:
                explanation = (
                    f"{explanation} | X贡献 {x_count}/{source_total}"
                    f"({int(round(x_ratio * 100))}%)"
                )[:220]

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
                    "source_mix": source_mix,
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

    def _load_x_quality_context(self) -> Dict[str, Any]:
        """加载 X 源健康状态与账号质量评分。"""
        context: Dict[str, Any] = {
            "health_status": "healthy",
            "freshness_sec": 0,
            "avg_quality_score": 60.0,
            "handle_scores": {},
        }

        try:
            row = (
                self.supabase.table("source_health_daily")
                .select("status,freshness_sec,source_payload,as_of")
                .eq("source_id", "x_grok_accounts")
                .order("as_of", desc=True)
                .limit(1)
                .maybe_single()
                .execute()
                .data
            )
            if isinstance(row, dict):
                context["health_status"] = str(row.get("status") or "healthy").strip().lower()
                context["freshness_sec"] = max(0, int(_safe_float(row.get("freshness_sec"), 0.0)))
        except Exception as e:
            logger.warning(f"[V2_X_HEALTH_FALLBACK] error={str(e)[:120]}")

        try:
            score_rows = (
                self.supabase.table("stock_x_account_score_daily")
                .select("handle,quality_score,score_date")
                .order("score_date", desc=True)
                .limit(600)
                .execute()
                .data
                or []
            )
            handle_scores: Dict[str, float] = {}
            for row in score_rows:
                handle = str(row.get("handle") or "").strip()
                if not handle or handle in handle_scores:
                    continue
                handle_scores[handle] = _clamp(_safe_float(row.get("quality_score"), 60.0), 0.0, 100.0)
            if handle_scores:
                context["handle_scores"] = handle_scores
                context["avg_quality_score"] = round(
                    sum(handle_scores.values()) / max(1, len(handle_scores)),
                    2,
                )
        except Exception as e:
            logger.warning(f"[V2_X_SCORE_FALLBACK] error={str(e)[:120]}")

        return context

    def _build_opportunities(
        self,
        signals: List[Dict[str, Any]],
        regime: Dict[str, Any],
        run_id: str,
        now: datetime,
        x_context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        regime_score = _safe_float(regime.get("regime_score"), 0.0)
        x_ctx = x_context if isinstance(x_context, dict) else {}
        x_health_status = str(x_ctx.get("health_status") or "healthy").strip().lower()
        x_freshness_sec = max(0, int(_safe_float(x_ctx.get("freshness_sec"), 0.0)))
        handle_scores = x_ctx.get("handle_scores")
        x_handle_scores = handle_scores if isinstance(handle_scores, dict) else {}
        x_avg_score = _clamp(_safe_float(x_ctx.get("avg_quality_score"), 60.0), 0.0, 100.0)
        rows: List[Dict[str, Any]] = []
        for signal in signals:
            side = str(signal.get("side") or "LONG")
            signal_score = _safe_float(signal.get("signal_score"), 0.0)
            confidence = _safe_float(signal.get("confidence"), 0.5)
            macro_boost = regime_score if side == "LONG" else -regime_score
            source_mix_raw = signal.get("source_mix")
            source_mix = source_mix_raw if isinstance(source_mix_raw, dict) else {}
            x_ratio = _clamp(_safe_float(source_mix.get("x_ratio"), 0.0), 0.0, 1.0)
            x_count = max(0, int(_safe_float(source_mix.get("x_count"), 0.0)))
            source_total = max(1, int(_safe_float(source_mix.get("source_total"), 0.0)))
            mixed_sources = bool(source_mix.get("mixed_sources"))
            resonance_score = _clamp(_safe_float(source_mix.get("resonance_score"), 0.0), 0.0, 1.0)
            top_x_handles = source_mix.get("top_x_handles")
            handles = top_x_handles if isinstance(top_x_handles, list) else []
            quality_scores = [
                _clamp(_safe_float(x_handle_scores.get(str(handle or "").strip()), x_avg_score), 0.0, 100.0)
                for handle in handles
                if str(handle or "").strip()
            ]
            x_quality = round(
                (sum(quality_scores) / max(1, len(quality_scores)))
                if quality_scores
                else x_avg_score,
                2,
            )
            horizon = "A" if signal_score >= 65 else "B"
            source_boost = 0.0
            if x_count > 0:
                source_boost += 1.2 + x_ratio * 1.8
            if mixed_sources:
                source_boost += 1.5
            source_boost += resonance_score * 1.6
            if x_count > 0 and x_quality < 55:
                source_boost -= 1.1
            if x_health_status == "critical" or x_freshness_sec > 43200:
                source_boost *= 0.2
            elif x_health_status == "degraded" or x_freshness_sec > 21600:
                source_boost *= 0.6
            opp_score = _clamp(
                signal_score * 0.82 + (macro_boost + 1.0) * 9.0 + source_boost,
                0.0,
                100.0,
            )
            opp_conf = _clamp(confidence * 0.82 + 0.13, 0.4, 0.95)
            if x_count > 0 and x_quality < 50 and x_ratio >= 0.6:
                opp_conf = _clamp(opp_conf - 0.08, 0.35, 0.95)
            expiry = now + timedelta(hours=72 if horizon == "A" else 24 * 14)

            if side == "LONG":
                invalid_if = "若风险偏好转弱且相关事件显著减少，则机会失效。"
            else:
                invalid_if = "若风险偏好快速修复且负面事件衰减，则机会失效。"
            x_note = ""
            if x_count > 0:
                x_note = (
                    f" X贡献 {x_count}/{source_total}"
                    f"（{int(round(x_ratio * 100))}%），"
                    f"共振 {int(round(resonance_score * 100))}，"
                    f"质量 {int(round(x_quality))}。"
                )
            debate_view = self._build_ai_debate_view(
                opportunity={
                    "ticker": signal.get("ticker"),
                    "side": side,
                    "confidence": opp_conf,
                    "source_mix": source_mix,
                },
                regime=regime,
            )
            counter_view = str(debate_view.get("counter_case") or "")
            uncertainty_flags = [
                str(item or "").strip()
                for item in (debate_view.get("uncertainties") or [])
                if str(item or "").strip()
            ]

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
                        f"{x_note}"
                    ),
                    "invalid_if": invalid_if,
                    "catalysts": signal.get("trigger_factors") or [],
                    "source_signal_ids": [],
                    "source_event_ids": signal.get("source_event_ids") or [],
                    "source_mix": source_mix,
                    "counter_view": counter_view[:260],
                    "uncertainty_flags": uncertainty_flags[:4],
                    "expires_at": expiry.isoformat(),
                    "as_of": now.isoformat(),
                    "run_id": run_id,
                    "is_active": True,
                }
            )
        rows.sort(key=lambda row: float(row.get("opportunity_score", 0.0)), reverse=True)
        return rows[:80]

    def _replace_active(
        self,
        table_name: str,
        rows: List[Dict[str, Any]],
        clear_when_empty: bool = False,
    ) -> int:
        if not rows:
            if clear_when_empty:
                self.supabase.table(table_name).update({"is_active": False}).eq("is_active", True).execute()
            return 0
        self.supabase.table(table_name).update({"is_active": False}).eq("is_active", True).execute()
        try:
            self.supabase.table(table_name).insert(rows).execute()
        except Exception as e:
            error_text = str(e).lower()
            optional_columns = [
                "source_mix",
                "counter_view",
                "uncertainty_flags",
                "evidence_ids",
                "path_ids",
            ]
            drop_cols = [col for col in optional_columns if col in error_text]
            if not drop_cols:
                raise
            fallback_rows = [
                {key: value for key, value in row.items() if key not in drop_cols}
                for row in rows
            ]
            self.supabase.table(table_name).insert(fallback_rows).execute()
            logger.warning(
                f"[V2_OPTIONAL_COLUMN_MISSING] table={table_name} dropped={','.join(drop_cols)}"
            )
        return len(rows)

    def _safe_replace_optional_table(
        self,
        table_name: str,
        rows: List[Dict[str, Any]],
    ) -> int:
        """写入可选表，若表未创建则告警降级。"""
        try:
            return self._replace_active(table_name, rows, clear_when_empty=True)
        except Exception as e:
            logger.warning(f"[V2_OPTIONAL_TABLE_FALLBACK] table={table_name} error={str(e)[:160]}")
            return 0

    def _load_active_opportunities_by_run(self, run_id: str) -> List[Dict[str, Any]]:
        """加载本轮机会行，用于证据/链路二次写入。"""
        try:
            rows = (
                self.supabase.table("stock_opportunities_v2")
                .select(
                    "id,opportunity_key,ticker,side,confidence,source_event_ids,source_mix,as_of"
                )
                .eq("run_id", run_id)
                .eq("is_active", True)
                .order("opportunity_score", desc=True)
                .limit(300)
                .execute()
                .data
                or []
            )
            return rows
        except Exception as e:
            logger.warning(f"[V2_OPP_LOAD_FALLBACK] run_id={run_id} error={str(e)[:160]}")
            return []

    def _load_active_id_map(self, table_name: str, run_id: str) -> Dict[int, List[int]]:
        """读取 run 内表数据并按 opportunity_id 聚合 ID。"""
        try:
            rows = (
                self.supabase.table(table_name)
                .select("id,opportunity_id")
                .eq("run_id", run_id)
                .eq("is_active", True)
                .execute()
                .data
                or []
            )
        except Exception as e:
            logger.warning(f"[V2_ID_MAP_FALLBACK] table={table_name} error={str(e)[:140]}")
            return {}

        grouped: Dict[int, List[int]] = defaultdict(list)
        for row in rows:
            opp_id = int(row.get("opportunity_id") or 0)
            item_id = int(row.get("id") or 0)
            if opp_id > 0 and item_id > 0:
                grouped[opp_id].append(item_id)
        return dict(grouped)

    def _patch_opportunity_enrichment(
        self,
        opportunities: List[Dict[str, Any]],
        evidence_ids_by_opp: Dict[int, List[int]],
        path_ids_by_opp: Dict[int, List[int]],
        regime: Dict[str, Any],
    ) -> int:
        """回写机会证据与反方观点字段。"""
        updated = 0
        for opp in opportunities:
            opp_id = int(opp.get("id") or 0)
            if opp_id <= 0:
                continue
            debate_view = self._build_ai_debate_view(opp, regime)
            payload: Dict[str, Any] = {
                "counter_view": str(debate_view.get("counter_case") or "")[:260],
                "uncertainty_flags": [
                    str(item or "").strip()
                    for item in (debate_view.get("uncertainties") or [])
                    if str(item or "").strip()
                ][:4],
                "evidence_ids": (evidence_ids_by_opp.get(opp_id) or [])[:24],
                "path_ids": (path_ids_by_opp.get(opp_id) or [])[:12],
            }
            try:
                (
                    self.supabase.table("stock_opportunities_v2")
                    .update(payload)
                    .eq("id", opp_id)
                    .execute()
                )
                updated += 1
            except Exception as e:
                logger.warning(
                    f"[V2_OPP_ENRICH_FALLBACK] opp_id={opp_id} error={str(e)[:160]}"
                )
                break
        return updated

    def _build_snapshot(
        self,
        opportunities: List[Dict[str, Any]],
        signals: List[Dict[str, Any]],
        regime: Dict[str, Any],
        run_id: str,
        now: datetime,
        x_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        risk_badge = "L1"
        if signals:
            risk_badge = max([str(item.get("level") or "L1") for item in signals])
        x_ctx = x_context if isinstance(x_context, dict) else {}
        x_health_status = str(x_ctx.get("health_status") or "healthy").strip().lower()
        x_freshness_sec = max(0, int(_safe_float(x_ctx.get("freshness_sec"), 0.0)))
        x_avg_quality = round(_clamp(_safe_float(x_ctx.get("avg_quality_score"), 60.0), 0.0, 100.0), 2)
        x_signal_count = 0
        x_mixed_count = 0
        x_event_total = 0
        x_ratio_sum = 0.0
        x_ratio_rows = 0
        x_handles: Counter[str] = Counter()

        for row in signals:
            source_mix = row.get("source_mix")
            if not isinstance(source_mix, dict):
                continue
            x_count = max(0, int(_safe_float(source_mix.get("x_count"), 0.0)))
            if x_count <= 0:
                continue
            x_signal_count += 1
            x_event_total += x_count
            x_ratio = _clamp(_safe_float(source_mix.get("x_ratio"), 0.0), 0.0, 1.0)
            x_ratio_sum += x_ratio
            x_ratio_rows += 1
            if bool(source_mix.get("mixed_sources")):
                x_mixed_count += 1
            handles = source_mix.get("top_x_handles")
            if isinstance(handles, list):
                for handle in handles:
                    h = str(handle or "").strip()
                    if h:
                        x_handles[h] += 1

        x_ratio_avg = round(x_ratio_sum / max(1, x_ratio_rows), 4)
        x_top_handles = [name for name, _ in x_handles.most_common(3)]
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
                f" X相关信号 {x_signal_count} 条，平均占比 {int(round(x_ratio_avg * 100))}% 。"
                f" X源健康 {x_health_status}，质量均值 {int(round(x_avg_quality))}。"
            ),
            "risk_badge": risk_badge,
            "data_health": {
                "opportunities": len(opportunities),
                "signals": len(signals),
                "risk_state": regime.get("risk_state", "neutral"),
                "x_signal_count": x_signal_count,
                "x_mixed_signal_count": x_mixed_count,
                "x_event_total": x_event_total,
                "x_ratio_avg": x_ratio_avg,
                "x_top_handles": x_top_handles,
                "x_health_status": x_health_status,
                "x_freshness_sec": x_freshness_sec,
                "x_quality_avg": x_avg_quality,
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
        x_context = self._load_x_quality_context()
        self._replace_active("stock_market_regime_v2", [regime])

        bundle = self._load_event_bundle(lookback_hours=lookback_hours)
        signal_rows = self._build_signals(bundle, run_id=run_id, now=now)
        if not signal_rows:
            logger.warning("[V2_KEEP_OLD] 未生成新信号，本轮仅刷新市场状态和快照")
            snapshot = self._build_snapshot(
                [],
                [],
                regime,
                run_id=run_id,
                now=now,
                x_context=x_context,
            )
            self._replace_active("stock_dashboard_snapshot_v2", [snapshot])
            return {"signals": 0, "opportunities": 0, "snapshot": 1, "evidence": 0, "paths": 0}

        signal_count = self._replace_active("stock_signals_v2", signal_rows)
        opp_rows = self._build_opportunities(
            signal_rows,
            regime,
            run_id=run_id,
            now=now,
            x_context=x_context,
        )
        opp_count = self._replace_active("stock_opportunities_v2", opp_rows)

        evidence_count = 0
        path_count = 0
        enriched_opp_count = 0
        if self.flags.enable_stock_evidence_layer or self.flags.enable_stock_transmission_layer:
            active_opps = self._load_active_opportunities_by_run(run_id=run_id)
            events_by_ticker: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for row in bundle:
                ticker = str(row.get("ticker") or "").upper()
                if ticker:
                    events_by_ticker[ticker].append(row)

            evidence_ids_by_opp: Dict[int, List[int]] = {}
            if self.flags.enable_stock_evidence_layer:
                evidence_rows = self._build_evidence_rows(
                    opportunities=active_opps,
                    events_by_ticker=events_by_ticker,
                    run_id=run_id,
                    now=now,
                )
                evidence_count = self._safe_replace_optional_table("stock_evidence_v2", evidence_rows)
                evidence_ids_by_opp = self._load_active_id_map("stock_evidence_v2", run_id=run_id)

            path_ids_by_opp: Dict[int, List[int]] = {}
            if self.flags.enable_stock_transmission_layer:
                path_rows = self._build_transmission_rows(
                    opportunities=active_opps,
                    events_by_ticker=events_by_ticker,
                    evidence_ids_by_opp=evidence_ids_by_opp,
                    run_id=run_id,
                    now=now,
                )
                path_count = self._safe_replace_optional_table(
                    "stock_transmission_paths_v2",
                    path_rows,
                )
                path_ids_by_opp = self._load_active_id_map(
                    "stock_transmission_paths_v2",
                    run_id=run_id,
                )

            if (
                self.flags.enable_stock_ai_debate_view
                or self.flags.enable_stock_evidence_layer
                or self.flags.enable_stock_transmission_layer
            ):
                enriched_opp_count = self._patch_opportunity_enrichment(
                    opportunities=active_opps,
                    evidence_ids_by_opp=evidence_ids_by_opp,
                    path_ids_by_opp=path_ids_by_opp,
                    regime=regime,
                )
                if enriched_opp_count > 0:
                    logger.info(
                        f"[V2_OPP_ENRICHED] count={enriched_opp_count} "
                        f"evidence_rows={evidence_count} path_rows={path_count}"
                    )

        snapshot = self._build_snapshot(
            opp_rows,
            signal_rows,
            regime,
            run_id=run_id,
            now=now,
            x_context=x_context,
        )
        snap_count = self._replace_active("stock_dashboard_snapshot_v2", [snapshot])
        return {
            "signals": signal_count,
            "opportunities": opp_count,
            "snapshot": snap_count,
            "evidence": evidence_count,
            "paths": path_count,
        }

    def run_incremental(
        self,
        hours: int = 48,
        article_limit: int = 1200,
        llm_event_cap: int = 60,
        lookback_hours: int = 168,
    ) -> Dict[str, Any]:
        """执行增量计算。"""
        run_id = f"inc-{_now_utc().strftime('%Y%m%d%H%M%S')}"
        run_started_at = _now_utc()
        cutoff_iso = (_now_utc() - timedelta(hours=hours)).isoformat()
        logger.info(
            f"[STOCK_V2_INCREMENTAL_START] run_id={run_id} hours={hours} limit={article_limit}"
        )
        self._v3_log_run_start(
            run_id=run_id,
            pipeline_name="stock_pipeline_v2_incremental",
            started_at=run_started_at,
            input_window={
                "hours": hours,
                "article_limit": article_limit,
                "lookback_hours": lookback_hours,
            },
            params_json=self._build_v3_params(
                {
                    "mode": "incremental",
                    "llm_event_cap": llm_event_cap,
                }
            ),
        )

        try:
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
                f"signals={serve_stats['signals']} opps={serve_stats['opportunities']} "
                f"evidence={serve_stats.get('evidence', 0)} paths={serve_stats.get('paths', 0)}"
            )
            metrics = {
                "run_id": run_id,
                "articles_seen": self.stats["articles_seen"],
                "stock_articles": self.stats["articles_stock_related"],
                "events_upserted": event_count,
                "mappings_upserted": mapping_count,
                "signals_written": serve_stats["signals"],
                "opportunities_written": serve_stats["opportunities"],
                "evidence_rows_written": serve_stats.get("evidence", 0),
                "transmission_paths_written": serve_stats.get("paths", 0),
            }
            self._v3_log_run_finish(
                run_id=run_id,
                started_at=run_started_at,
                status="success",
                metrics=metrics,
            )
            return metrics
        except Exception as e:
            self._v3_log_run_finish(
                run_id=run_id,
                started_at=run_started_at,
                status="failed",
                metrics={
                    "articles_seen": self.stats["articles_seen"],
                    "stock_articles": self.stats["articles_stock_related"],
                },
                notes=str(e),
            )
            raise

    def run_backfill(
        self,
        batch_size: int = 500,
        max_articles: Optional[int] = None,
        llm_event_cap: int = 0,
        lookback_hours: int = 336,
    ) -> Dict[str, Any]:
        """执行全量回填。"""
        run_id = f"backfill-{_now_utc().strftime('%Y%m%d%H%M%S')}"
        run_started_at = _now_utc()
        logger.info(
            f"[STOCK_V2_BACKFILL_START] run_id={run_id} batch={batch_size} max={max_articles}"
        )
        self._v3_log_run_start(
            run_id=run_id,
            pipeline_name="stock_pipeline_v2_backfill",
            started_at=run_started_at,
            input_window={
                "batch_size": batch_size,
                "max_articles": max_articles,
                "lookback_hours": lookback_hours,
            },
            params_json=self._build_v3_params(
                {
                    "mode": "backfill",
                    "llm_event_cap": llm_event_cap,
                }
            ),
        )

        try:
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
                rows = self._load_articles_batch(
                    offset=offset,
                    batch_size=current_size,
                    fetched_after=None,
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
                f"opps={serve_stats['opportunities']} "
                f"evidence={serve_stats.get('evidence', 0)} paths={serve_stats.get('paths', 0)}"
            )
            metrics = {
                "run_id": run_id,
                "processed_articles": processed,
                "stock_articles": self.stats["articles_stock_related"],
                "events_upserted": total_events,
                "mappings_upserted": total_mappings,
                "signals_written": serve_stats["signals"],
                "opportunities_written": serve_stats["opportunities"],
                "evidence_rows_written": serve_stats.get("evidence", 0),
                "transmission_paths_written": serve_stats.get("paths", 0),
            }
            self._v3_log_run_finish(
                run_id=run_id,
                started_at=run_started_at,
                status="success",
                metrics=metrics,
            )
            return metrics
        except Exception as e:
            self._v3_log_run_finish(
                run_id=run_id,
                started_at=run_started_at,
                status="failed",
                metrics={
                    "processed_articles": self.stats["articles_seen"],
                    "stock_articles": self.stats["articles_stock_related"],
                },
                notes=str(e),
            )
            raise


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
