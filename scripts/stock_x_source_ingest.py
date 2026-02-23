#!/usr/bin/env python3
"""Stock X(Twitter) 信息源采集与入库脚本。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import math
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from openai import OpenAI
from supabase import Client, create_client

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


CATEGORY_ALIAS = {
    "实时新闻与资讯": "news",
    "量化/期权与资金流": "quant",
    "宏观估值与基本面": "macro",
    "技术分析与交易信号": "technical",
}

CATEGORY_QUOTA = {
    "news": 10,
    "quant": 8,
    "macro": 7,
    "technical": 5,
}

CATEGORY_BONUS = {
    "news": 8.0,
    "quant": 9.0,
    "macro": 7.0,
    "technical": 6.5,
}

FOLLOWER_FALLBACK = {
    "高流量": 550000,
    "中等": 180000,
    "数百万": 3200000,
}

SIGNAL_KEYWORDS = {
    "期权": 3.2,
    "资金": 2.7,
    "gamma": 2.6,
    "breakout": 2.0,
    "突破": 2.0,
    "财报": 1.8,
    "fed": 2.2,
    "评级": 1.5,
    "宏观": 1.8,
    "快讯": 1.8,
    "机构": 1.8,
    "流": 1.4,
}

EVENT_TYPE_ALLOW = {"earnings", "macro", "policy", "flow", "sector", "news", "sentiment"}
EVENT_TYPE_MAP = {
    "earnings": "earnings",
    "macro": "macro",
    "policy": "policy",
    "flow": "flow",
    "sector": "sector",
    "sentiment": "flow",
    "news": "news",
}

TICKER_PATTERN = re.compile(r"\$?([A-Z]{1,5})")


@dataclass
class AccountSeed:
    """候选账号元数据。"""

    handle: str
    category_cn: str
    category_key: str
    follower_text: str
    follower_count: int
    signal_type: str
    value_note: str
    score: float
    priority_rank: int = 999


@dataclass
class IngestStats:
    """运行指标。"""

    accounts_total: int = 0
    accounts_success: int = 0
    accounts_failed: int = 0
    posts_written: int = 0
    signals_written: int = 0
    events_written: int = 0


@dataclass
class AccountResult:
    """单账号执行结果。"""

    handle: str
    ok: bool
    elapsed_sec: float
    error: str
    account_profile: Dict[str, Any]
    posts: List[Dict[str, Any]]


class StockXSourceIngestor:
    """Stock X 信息源采集执行器。"""

    def __init__(
        self,
        mode: str,
        accounts_file: str,
        topn: int,
        post_limit: int,
        workers: int,
        run_id: str,
        dry_run: bool,
        deactivate_others: bool,
    ):
        self.mode = mode
        self.accounts_file = Path(accounts_file)
        self.topn = max(1, topn)
        self.post_limit = max(1, post_limit)
        self.workers = max(1, workers)
        self.run_id = run_id
        self.dry_run = dry_run
        self.deactivate_others = deactivate_others

        self.supabase = self._init_supabase()
        self.grok_model = ""
        self.grok_base_url = ""
        self.grok_api_key = ""
        self.grok_client: Optional[OpenAI] = None
        if self.mode in {"full", "ingest"}:
            self.grok_model, self.grok_base_url, self.grok_api_key = self._resolve_grok_config()
            self.grok_client = self._init_grok_client()

    def _init_supabase(self) -> Client:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("缺少 SUPABASE_URL / SUPABASE_KEY")
        return create_client(url, key)

    def _resolve_grok_config(self) -> Tuple[str, str, str]:
        config_path = Path("grok_apikey.txt")
        if not config_path.exists():
            raise ValueError("缺少 grok_apikey.txt，必须使用该文件提供 Grok 配置")

        parsed = self._parse_grok_file(config_path)
        model = str(parsed.get("model") or "").strip()
        base_url = str(parsed.get("base_url") or "").strip()
        api_key = str(parsed.get("api_key") or "").strip()

        missing: List[str] = []
        if not model:
            missing.append("model")
        if not base_url:
            missing.append("base_url")
        if not api_key:
            missing.append("api_key")

        if missing:
            raise ValueError(
                "grok_apikey.txt 缺少必要字段: " + ",".join(missing)
            )

        return model, base_url, api_key

    def _parse_grok_file(self, path: Path) -> Dict[str, str]:
        raw = path.read_text(encoding="utf-8")
        info: Dict[str, str] = {}
        for line in raw.splitlines():
            text = line.strip()
            if not text:
                continue
            parts = re.split(r"[:：]", text, maxsplit=1)
            if len(parts) != 2:
                continue
            key = parts[0].strip().lower()
            value = parts[1].strip()
            if "模型" in key or "model" in key:
                info["model"] = value
            elif "api地址" in key or "base" in key or "url" in key:
                info["base_url"] = value
            elif "apikey" in key or "api key" in key or "token" in key:
                info["api_key"] = value
        return info

    def _init_grok_client(self) -> OpenAI:
        return OpenAI(api_key=self.grok_api_key, base_url=self.grok_base_url)

    def _load_accounts(self) -> List[AccountSeed]:
        if not self.accounts_file.exists():
            raise FileNotFoundError(f"账号文件不存在: {self.accounts_file}")

        rows: List[AccountSeed] = []
        with self.accounts_file.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                handle = self._normalize_handle(row.get("账号") or "")
                if not handle:
                    continue
                category_cn = str(row.get("类别") or "").strip()
                category_key = CATEGORY_ALIAS.get(category_cn, "news")
                follower_text = str(row.get("粉丝数（约）") or "").strip()
                follower_count = self._parse_follower_count(follower_text)
                signal_type = str(row.get("主要信号类型") or "").strip()
                value_note = str(row.get("作为信号源的价值（趋势/策略应用）") or "").strip()

                score = self._score_account(
                    category_key=category_key,
                    follower_count=follower_count,
                    signal_type=signal_type,
                    value_note=value_note,
                )
                rows.append(
                    AccountSeed(
                        handle=handle,
                        category_cn=category_cn,
                        category_key=category_key,
                        follower_text=follower_text,
                        follower_count=follower_count,
                        signal_type=signal_type,
                        value_note=value_note,
                        score=score,
                    )
                )

        logger.info(f"[STOCK_X_LOAD_ACCOUNTS] loaded={len(rows)} file={self.accounts_file}")
        return rows

    def _normalize_handle(self, handle: str) -> str:
        text = str(handle or "").strip()
        if not text:
            return ""
        text = text.replace("https://x.com/", "").replace("https://twitter.com/", "")
        text = text.lstrip("@").split("/")[0].split("?")[0]
        return text.strip()

    def _parse_follower_count(self, text: str) -> int:
        raw = str(text or "").strip().replace(",", "")
        if not raw:
            return 0

        for marker, value in FOLLOWER_FALLBACK.items():
            if marker in raw:
                return value

        lowered = raw.lower().replace("+", "")
        m = re.search(r"(\d+(?:\.\d+)?)\s*([mk万w]?)", lowered)
        if not m:
            return 0
        value = float(m.group(1))
        unit = m.group(2)
        if unit == "m":
            value *= 1_000_000
        elif unit == "k":
            value *= 1_000
        elif unit in {"万", "w"}:
            value *= 10_000
        return int(value)

    def _score_account(
        self,
        category_key: str,
        follower_count: int,
        signal_type: str,
        value_note: str,
    ) -> float:
        follower_score = min(40.0, math.log10(max(1, follower_count)) * 10.0)
        text = f"{signal_type} {value_note}".lower()
        keyword_score = 0.0
        for keyword, weight in SIGNAL_KEYWORDS.items():
            if keyword in text:
                keyword_score += weight
        category_bonus = CATEGORY_BONUS.get(category_key, 5.0)
        return round(follower_score + keyword_score + category_bonus, 4)

    def _select_top_accounts(self, accounts: List[AccountSeed]) -> List[AccountSeed]:
        by_category: Dict[str, List[AccountSeed]] = {}
        for item in accounts:
            by_category.setdefault(item.category_key, []).append(item)

        for key in by_category:
            by_category[key].sort(key=lambda x: x.score, reverse=True)

        selected: List[AccountSeed] = []
        selected_handles: set[str] = set()

        for category_key, quota in CATEGORY_QUOTA.items():
            cat_items = by_category.get(category_key, [])
            for item in cat_items[:quota]:
                if item.handle in selected_handles:
                    continue
                selected.append(item)
                selected_handles.add(item.handle)

        if len(selected) < self.topn:
            rest = sorted(accounts, key=lambda x: x.score, reverse=True)
            for item in rest:
                if item.handle in selected_handles:
                    continue
                selected.append(item)
                selected_handles.add(item.handle)
                if len(selected) >= self.topn:
                    break

        selected = selected[: self.topn]
        for idx, item in enumerate(selected, start=1):
            item.priority_rank = idx

        category_breakdown: Dict[str, int] = {}
        for item in selected:
            category_breakdown[item.category_key] = category_breakdown.get(item.category_key, 0) + 1
        logger.info(
            "[STOCK_X_TOPN_SELECTED] "
            f"topn={len(selected)} breakdown={json.dumps(category_breakdown, ensure_ascii=False)}"
        )
        return selected

    def _upsert_accounts(self, accounts: Sequence[AccountSeed]) -> Dict[str, int]:
        if not accounts:
            return {}
        now_iso = _now_utc().isoformat()

        payload_rows = []
        selected_handles = []
        for item in accounts:
            selected_handles.append(item.handle)
            payload_rows.append(
                {
                    "handle": item.handle,
                    "category": item.category_key,
                    "follower_text": item.follower_text[:64],
                    "follower_count": item.follower_count,
                    "signal_type": item.signal_type[:500],
                    "value_note": item.value_note[:1200],
                    "score": item.score,
                    "priority_rank": item.priority_rank,
                    "source_payload": {
                        "category_cn": item.category_cn,
                        "signal_type": item.signal_type,
                        "value_note": item.value_note,
                        "seed_source": str(self.accounts_file),
                    },
                    "run_id": self.run_id,
                    "is_active": True,
                    "as_of": now_iso,
                }
            )

        if self.dry_run:
            id_map = {item.handle: idx for idx, item in enumerate(accounts, start=1)}
            logger.info(
                f"[STOCK_X_ACCOUNTS_UPSERT_DRY_RUN] total={len(payload_rows)}"
            )
            return id_map

        try:
            self.supabase.table("stock_x_accounts").upsert(
                payload_rows,
                on_conflict="handle",
            ).execute()
        except Exception as e:
            msg = str(e)
            if "stock_x_accounts" in msg or "schema cache" in msg:
                raise ValueError(
                    "缺少 stock_x_* 表，请先执行 sql/2026-02-23_stock_x_source_tables.sql"
                ) from e
            raise

        if self.deactivate_others:
            existing_rows = (
                self.supabase.table("stock_x_accounts")
                .select("id,handle")
                .eq("is_active", True)
                .limit(500)
                .execute()
                .data
                or []
            )
            stale_ids = [
                int(row.get("id") or 0)
                for row in existing_rows
                if str(row.get("handle") or "") not in selected_handles
            ]
            for batch in _chunks(stale_ids, 100):
                (
                    self.supabase.table("stock_x_accounts")
                    .update({"is_active": False, "as_of": now_iso, "run_id": self.run_id})
                    .in_("id", batch)
                    .execute()
                )

        try:
            rows = (
                self.supabase.table("stock_x_accounts")
                .select("id,handle")
                .in_("handle", selected_handles)
                .execute()
                .data
                or []
            )
        except Exception as e:
            msg = str(e)
            if "stock_x_accounts" in msg or "schema cache" in msg:
                raise ValueError(
                    "缺少 stock_x_* 表，请先执行 sql/2026-02-23_stock_x_source_tables.sql"
                ) from e
            raise
        id_map = {str(row.get("handle") or ""): int(row.get("id") or 0) for row in rows}
        logger.info(f"[STOCK_X_ACCOUNTS_UPSERT] total={len(payload_rows)}")
        return id_map

    def _load_active_accounts(self, limit: int) -> List[Dict[str, Any]]:
        try:
            rows = (
                self.supabase.table("stock_x_accounts")
                .select("id,handle,category,signal_type,value_note,priority_rank")
                .eq("is_active", True)
                .order("priority_rank", desc=False)
                .limit(max(1, limit))
                .execute()
                .data
                or []
            )
        except Exception as e:
            msg = str(e)
            if "stock_x_accounts" in msg or "schema cache" in msg:
                raise ValueError(
                    "缺少 stock_x_* 表，请先执行 sql/2026-02-23_stock_x_source_tables.sql"
                ) from e
            raise
        return rows

    def _grok_fetch_account(self, account: Dict[str, Any]) -> AccountResult:
        if self.grok_client is None:
            raise ValueError("Grok client 未初始化")

        handle = str(account.get("handle") or "")
        started = time.perf_counter()
        prompt = (
            "你是美股投研数据工程助手。"
            "请尽量基于公开信息提取目标 X 账号最近内容，聚焦美股投资相关动态。"
            "如果无法确认真实数据，请返回空数组并在 notes 说明，禁止编造。"
            "仅返回 JSON，不要 markdown。\n"
            "JSON schema:\n"
            "{\n"
            '  "account_profile": {"display_name":"","bio":"","focus":[""],"credibility":0-1,'
            '"last_active_at":"ISO"},\n'
            '  "account_health": {"status":"healthy|degraded|critical","notes":""},\n'
            '  "posts": [\n'
            "    {\n"
            '      "post_id":"", "posted_at":"ISO", "post_url":"",\n'
            '      "text":"", "content_zh":"", "lang":"en|zh|other",\n'
            '      "metrics":{"likes":0,"reposts":0,"replies":0,"views":0},\n'
            '      "signals":[\n'
            "        {\n"
            '          "ticker":"AAPL", "side":"LONG|SHORT|NEUTRAL",\n'
            '          "event_type":"news|earnings|macro|policy|flow|sector|sentiment",\n'
            '          "confidence":0-1, "strength":0-1,\n'
            '          "summary_zh":"", "why_now_zh":"", "invalid_if_zh":"",\n'
            '          "signal_tags":[""], "data_quality":"observed|estimated"\n'
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}\n"
            f"目标账号: @{handle}\n"
            f"账号类别: {account.get('category') or ''}\n"
            f"账号定位: {account.get('signal_type') or ''}\n"
            f"价值备注: {account.get('value_note') or ''}\n"
            f"返回最近条数: {self.post_limit}\n"
            "要求: posts 最多返回该条数，按时间倒序。"
        )

        try:
            response = self.grok_client.chat.completions.create(
                model=self.grok_model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是结构化金融数据助手，必须输出合法 JSON。",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=6000,
                temperature=0.1,
                timeout=120,
            )
            raw_text = str(response.choices[0].message.content or "")
            payload = self._parse_json_payload(raw_text)
            posts = self._normalize_posts(handle=handle, payload=payload)
            elapsed = time.perf_counter() - started
            return AccountResult(
                handle=handle,
                ok=True,
                elapsed_sec=elapsed,
                error="",
                account_profile=payload.get("account_profile") or {},
                posts=posts,
            )
        except Exception as e:
            elapsed = time.perf_counter() - started
            logger.warning(f"[STOCK_X_FETCH_FAILED] handle={handle} error={str(e)[:160]}")
            return AccountResult(
                handle=handle,
                ok=False,
                elapsed_sec=elapsed,
                error=str(e)[:500],
                account_profile={},
                posts=[],
            )

    def _parse_json_payload(self, raw_text: str) -> Dict[str, Any]:
        text = str(raw_text or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        if not text:
            return {}

        try:
            payload = json.loads(text)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            pass

        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx >= 0 and end_idx > start_idx:
            snippet = text[start_idx : end_idx + 1]
            try:
                payload = json.loads(snippet)
                return payload if isinstance(payload, dict) else {}
            except Exception:
                return {}
        return {}

    def _normalize_posts(self, handle: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        posts = payload.get("posts") if isinstance(payload.get("posts"), list) else []
        normalized: List[Dict[str, Any]] = []

        for item in posts[: self.post_limit]:
            if not isinstance(item, dict):
                continue
            text = _safe_text(item.get("text"), 3000)
            content_zh = _safe_text(item.get("content_zh"), 3000)
            if not text and not content_zh:
                continue

            post_id = _safe_text(item.get("post_id"), 80)
            posted_at = _to_iso_datetime(item.get("posted_at"))
            post_url = _safe_text(item.get("post_url"), 500)
            lang = _safe_text(item.get("lang"), 16).lower() or "unknown"
            metrics = _normalize_metrics(item.get("metrics"))

            if not post_id:
                seed = f"{handle}|{posted_at}|{text[:120]}"
                post_id = hashlib.md5(seed.encode("utf-8")).hexdigest()[:24]
            if not post_url:
                post_url = f"https://x.com/{handle}/status/{post_id}"

            signals_raw = item.get("signals") if isinstance(item.get("signals"), list) else []
            signals: List[Dict[str, Any]] = []
            for signal in signals_raw:
                if not isinstance(signal, dict):
                    continue
                ticker = _normalize_ticker(signal.get("ticker"))
                if not ticker:
                    continue
                side = _normalize_side(signal.get("side"))
                event_type = _normalize_event_type(signal.get("event_type"))
                confidence = _clamp(_safe_float(signal.get("confidence"), 0.55), 0.01, 0.99)
                strength = _clamp(_safe_float(signal.get("strength"), 0.55), 0.01, 0.99)
                signal_tags = signal.get("signal_tags")
                tags = []
                if isinstance(signal_tags, list):
                    tags = [
                        _safe_text(tag, 40)
                        for tag in signal_tags
                        if _safe_text(tag, 40)
                    ][:8]
                summary_zh = _safe_text(signal.get("summary_zh"), 220)
                why_now_zh = _safe_text(signal.get("why_now_zh"), 220)
                invalid_if_zh = _safe_text(signal.get("invalid_if_zh"), 220)
                data_quality = _safe_text(signal.get("data_quality"), 16).lower() or "unknown"

                signals.append(
                    {
                        "ticker": ticker,
                        "side": side,
                        "event_type": event_type,
                        "confidence": confidence,
                        "strength": strength,
                        "summary_zh": summary_zh,
                        "why_now_zh": why_now_zh,
                        "invalid_if_zh": invalid_if_zh,
                        "signal_tags": tags,
                        "data_quality": data_quality,
                    }
                )

            # 当 LLM 未给出信号时，尝试从文本提取一个最低置信度的观测信号。
            if not signals:
                fallback_ticker = _extract_first_ticker(text or content_zh)
                if fallback_ticker:
                    signals.append(
                        {
                            "ticker": fallback_ticker,
                            "side": "NEUTRAL",
                            "event_type": "news",
                            "confidence": 0.35,
                            "strength": 0.25,
                            "summary_zh": _safe_text(content_zh or text, 220),
                            "why_now_zh": "",
                            "invalid_if_zh": "",
                            "signal_tags": ["fallback"],
                            "data_quality": "estimated",
                        }
                    )

            normalized.append(
                {
                    "post_id": post_id,
                    "posted_at": posted_at,
                    "post_url": post_url,
                    "text": text,
                    "content_zh": content_zh,
                    "lang": lang,
                    "metrics": metrics,
                    "signals": signals,
                }
            )
        return normalized

    def _create_run_record(self, params_json: Dict[str, Any]) -> None:
        if self.dry_run:
            return
        try:
            self.supabase.table("stock_x_ingest_runs").upsert(
                {
                    "run_id": self.run_id,
                    "mode": self.mode,
                    "status": "running",
                    "params_json": params_json,
                    "started_at": _now_utc().isoformat(),
                    "as_of": _now_utc().isoformat(),
                },
                on_conflict="run_id",
            ).execute()
        except Exception as e:
            logger.warning(f"[STOCK_X_RUN_RECORD_START_FAILED] error={str(e)[:160]}")

    def _finish_run_record(
        self,
        status: str,
        stats: IngestStats,
        started_at: datetime,
        error_summary: str,
    ) -> None:
        if self.dry_run:
            return
        ended_at = _now_utc()
        duration_sec = max(0, int((ended_at - started_at).total_seconds()))
        try:
            self.supabase.table("stock_x_ingest_runs").update(
                {
                    "status": status,
                    "accounts_total": stats.accounts_total,
                    "accounts_success": stats.accounts_success,
                    "accounts_failed": stats.accounts_failed,
                    "posts_written": stats.posts_written,
                    "signals_written": stats.signals_written,
                    "events_written": stats.events_written,
                    "duration_sec": duration_sec,
                    "error_summary": error_summary[:5000],
                    "ended_at": ended_at.isoformat(),
                    "as_of": ended_at.isoformat(),
                }
            ).eq("run_id", self.run_id).execute()
        except Exception as e:
            logger.warning(f"[STOCK_X_RUN_RECORD_FINISH_FAILED] error={str(e)[:160]}")

    def _persist_account_results(
        self,
        account_id_map: Dict[str, int],
        results: List[AccountResult],
    ) -> Tuple[int, int, int]:
        now_iso = _now_utc().isoformat()

        post_rows: List[Dict[str, Any]] = []
        post_key_meta: Dict[str, Dict[str, Any]] = {}
        per_account_health: List[Dict[str, Any]] = []

        for result in results:
            account_id = int(account_id_map.get(result.handle) or 0)
            if account_id <= 0:
                continue

            success_count = 1 if result.ok else 0
            failure_count = 0 if result.ok else 1
            account_post_count = 0
            account_signal_count = 0

            for post in result.posts:
                post_key = f"{result.handle}:{post['post_id']}"
                raw_payload = {
                    "source": "grok",
                    "account_profile": result.account_profile,
                }
                post_rows.append(
                    {
                        "post_key": post_key,
                        "account_id": account_id,
                        "handle": result.handle,
                        "post_id": post["post_id"],
                        "post_url": post["post_url"],
                        "posted_at": post["posted_at"],
                        "content": _safe_text(post["text"], 5000),
                        "content_zh": _safe_text(post.get("content_zh"), 5000),
                        "lang": _safe_text(post.get("lang"), 16) or "unknown",
                        "metrics": post.get("metrics") or {},
                        "raw_payload": raw_payload,
                        "run_id": self.run_id,
                        "as_of": now_iso,
                    }
                )
                post_key_meta[post_key] = {
                    "handle": result.handle,
                    "account_id": account_id,
                    "post_url": post["post_url"],
                    "posted_at": post["posted_at"],
                    "content": post["text"],
                    "content_zh": post.get("content_zh") or "",
                    "signals": post.get("signals") or [],
                }
                account_post_count += 1
                account_signal_count += len(post.get("signals") or [])

            per_account_health.append(
                {
                    "health_date": datetime.now(timezone.utc).date().isoformat(),
                    "handle": result.handle,
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "post_count": account_post_count,
                    "signal_count": account_signal_count,
                    "avg_latency_ms": round(result.elapsed_sec * 1000, 2),
                    "status": _health_status(result.ok, account_post_count, account_signal_count),
                    "latest_error": result.error[:500],
                    "run_id": self.run_id,
                    "as_of": now_iso,
                }
            )

        if self.dry_run:
            return len(post_rows), 0, 0

        if post_rows:
            for batch in _chunks(post_rows, 200):
                self.supabase.table("stock_x_posts_raw").upsert(
                    batch,
                    on_conflict="post_key",
                ).execute()

        if per_account_health:
            for batch in _chunks(per_account_health, 100):
                self.supabase.table("stock_x_account_health_daily").upsert(
                    batch,
                    on_conflict="health_date,handle",
                ).execute()

        post_keys = [row["post_key"] for row in post_rows]
        stored_posts: List[Dict[str, Any]] = []
        for batch in _chunks(post_keys, 200):
            if not batch:
                continue
            fetched = (
                self.supabase.table("stock_x_posts_raw")
                .select("id,post_key")
                .in_("post_key", batch)
                .execute()
                .data
                or []
            )
            stored_posts.extend(fetched)

        post_id_map = {str(row.get("post_key") or ""): int(row.get("id") or 0) for row in stored_posts}

        signal_rows: List[Dict[str, Any]] = []
        event_rows: List[Dict[str, Any]] = []
        event_map_rows: List[Dict[str, Any]] = []

        for post_key, meta in post_key_meta.items():
            post_table_id = int(post_id_map.get(post_key) or 0)
            if post_table_id <= 0:
                continue
            for signal in meta["signals"]:
                signal_row = {
                    "post_id": post_table_id,
                    "account_id": meta["account_id"],
                    "handle": meta["handle"],
                    "ticker": signal["ticker"],
                    "side": signal["side"],
                    "event_type": signal["event_type"],
                    "confidence": signal["confidence"],
                    "strength": signal["strength"],
                    "summary_zh": _safe_text(signal.get("summary_zh"), 220),
                    "why_now_zh": _safe_text(signal.get("why_now_zh"), 220),
                    "invalid_if_zh": _safe_text(signal.get("invalid_if_zh"), 220),
                    "signal_tags": signal.get("signal_tags") or [],
                    "evidence": {
                        "post_url": meta.get("post_url"),
                        "posted_at": meta.get("posted_at"),
                        "data_quality": signal.get("data_quality") or "unknown",
                    },
                    "run_id": self.run_id,
                    "as_of": now_iso,
                }
                signal_rows.append(signal_row)

                event_key_seed = (
                    f"x:{post_key}:{signal['ticker']}:{signal['event_type']}:{signal['side']}"
                )
                event_key = f"x:{hashlib.md5(event_key_seed.encode('utf-8')).hexdigest()[:24]}"
                ttl_hours = _event_ttl_hours(signal["event_type"])
                summary = _safe_text(
                    signal.get("summary_zh")
                    or meta.get("content_zh")
                    or meta.get("content"),
                    220,
                )
                source_ref = _safe_text(meta.get("post_url"), 128)
                if not source_ref:
                    source_ref = _safe_text(f"x:{meta['handle']}:{post_key}", 128)

                event_rows.append(
                    {
                        "event_key": event_key,
                        "source_type": "x_grok",
                        "source_ref": source_ref,
                        "event_type": signal["event_type"],
                        "direction": signal["side"],
                        "strength": signal["strength"],
                        "ttl_hours": ttl_hours,
                        "summary": summary or f"@{meta['handle']} {signal['ticker']} 观察",
                        "details": {
                            "title": _safe_text(meta.get("content"), 180),
                            "title_zh": _safe_text(signal.get("summary_zh"), 120),
                            "summary_zh": _safe_text(summary, 220),
                            "why_now_zh": _safe_text(signal.get("why_now_zh"), 220),
                            "invalid_if_zh": _safe_text(signal.get("invalid_if_zh"), 220),
                            "handle": meta["handle"],
                            "post_key": post_key,
                            "post_url": meta.get("post_url"),
                            "signal_tags": signal.get("signal_tags") or [],
                            "llm_used": True,
                            "source_model": self.grok_model,
                            "source_pipeline": "stock_x_source_ingest",
                            "data_quality": signal.get("data_quality") or "unknown",
                        },
                        "published_at": meta.get("posted_at"),
                        "as_of": now_iso,
                        "run_id": self.run_id,
                        "is_active": True,
                    }
                )

                event_map_rows.append(
                    {
                        "event_key": event_key,
                        "ticker": signal["ticker"],
                        "role": "primary",
                        "weight": 1.0,
                        "confidence": signal["confidence"],
                        "as_of": now_iso,
                        "run_id": self.run_id,
                    }
                )

        if signal_rows:
            for batch in _chunks(signal_rows, 300):
                self.supabase.table("stock_x_post_signals").upsert(
                    batch,
                    on_conflict="post_id,ticker,event_type,side",
                ).execute()

        events_written = self._upsert_events(event_rows=event_rows, raw_map_rows=event_map_rows)
        return len(post_rows), len(signal_rows), events_written

    def _upsert_events(
        self,
        event_rows: List[Dict[str, Any]],
        raw_map_rows: List[Dict[str, Any]],
    ) -> int:
        if not event_rows:
            return 0

        for batch in _chunks(event_rows, 250):
            self.supabase.table("stock_events_v2").upsert(
                batch,
                on_conflict="event_key",
            ).execute()

        event_keys = [row["event_key"] for row in event_rows]
        id_rows: List[Dict[str, Any]] = []
        for batch in _chunks(event_keys, 250):
            fetched = (
                self.supabase.table("stock_events_v2")
                .select("id,event_key")
                .in_("event_key", batch)
                .execute()
                .data
                or []
            )
            id_rows.extend(fetched)

        key_to_id = {str(row.get("event_key") or ""): int(row.get("id") or 0) for row in id_rows}

        map_rows: List[Dict[str, Any]] = []
        for row in raw_map_rows:
            event_id = int(key_to_id.get(row["event_key"]) or 0)
            if event_id <= 0:
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
            for batch in _chunks(map_rows, 300):
                self.supabase.table("stock_event_tickers_v2").upsert(
                    batch,
                    on_conflict="event_id,ticker,role",
                ).execute()

        return len(event_rows)

    def _upsert_source_health(self, stats: IngestStats, freshest_post_at: str) -> None:
        if self.dry_run:
            return

        now = _now_utc()
        total = max(1, stats.accounts_total)
        success_rate = stats.accounts_success / total
        error_rate = 1.0 - success_rate
        null_rate = 1.0 if stats.posts_written <= 0 else 0.0
        freshness_sec = 999999
        if freshest_post_at:
            freshness_sec = _seconds_since_iso(freshest_post_at)

        status = "healthy"
        if success_rate < 0.6 or freshness_sec > 43200:
            status = "critical"
        elif success_rate < 0.9 or freshness_sec > 21600:
            status = "degraded"

        payload = {
            "source_id": "x_grok_accounts",
            "health_date": now.date().isoformat(),
            "success_rate": round(success_rate, 4),
            "p95_latency_ms": 0,
            "freshness_sec": max(0, freshness_sec),
            "null_rate": round(null_rate, 4),
            "error_rate": round(error_rate, 4),
            "status": status,
            "notes": (
                f"accounts={stats.accounts_total}, success={stats.accounts_success}, "
                f"posts={stats.posts_written}, signals={stats.signals_written}"
            ),
            "source_payload": {
                "mode": self.mode,
                "run_id": self.run_id,
                "events_written": stats.events_written,
            },
            "run_id": self.run_id,
            "as_of": now.isoformat(),
        }
        try:
            self.supabase.table("source_health_daily").upsert(
                payload,
                on_conflict="source_id,health_date",
            ).execute()
        except Exception as e:
            logger.warning(f"[STOCK_X_SOURCE_HEALTH_FAILED] error={str(e)[:160]}")

    def run(self) -> Dict[str, Any]:
        started_at = _now_utc()
        stats = IngestStats()
        errors: List[str] = []

        logger.info(
            f"[STOCK_X_RUN_START] run_id={self.run_id} mode={self.mode} topn={self.topn} "
            f"post_limit={self.post_limit} workers={self.workers} dry_run={self.dry_run}"
        )
        self._create_run_record(
            {
                "mode": self.mode,
                "topn": self.topn,
                "post_limit": self.post_limit,
                "workers": self.workers,
                "accounts_file": str(self.accounts_file),
                "deactivate_others": self.deactivate_others,
            }
        )

        accounts_for_ingest: List[Dict[str, Any]] = []
        account_id_map: Dict[str, int] = {}

        if self.mode in {"full", "import"}:
            seeds = self._load_accounts()
            top_accounts = self._select_top_accounts(seeds)
            account_id_map = self._upsert_accounts(top_accounts)
            accounts_for_ingest = [
                {
                    "id": account_id_map.get(item.handle),
                    "handle": item.handle,
                    "category": item.category_key,
                    "signal_type": item.signal_type,
                    "value_note": item.value_note,
                    "priority_rank": item.priority_rank,
                }
                for item in top_accounts
            ]

        if self.mode == "import":
            logger.info(
                f"[STOCK_X_IMPORT_DONE] run_id={self.run_id} accounts={len(account_id_map)}"
            )
            self._finish_run_record(
                status="success",
                stats=stats,
                started_at=started_at,
                error_summary="",
            )
            return {
                "run_id": self.run_id,
                "mode": self.mode,
                "accounts_imported": len(account_id_map),
                "stats": stats.__dict__,
            }

        if self.mode == "ingest":
            accounts_for_ingest = self._load_active_accounts(self.topn)
            account_id_map = {
                str(row.get("handle") or ""): int(row.get("id") or 0)
                for row in accounts_for_ingest
            }

        if not accounts_for_ingest:
            logger.warning("[STOCK_X_NO_ACCOUNTS] no active accounts to ingest")
            self._finish_run_record(
                status="failed",
                stats=stats,
                started_at=started_at,
                error_summary="no accounts",
            )
            return {
                "run_id": self.run_id,
                "mode": self.mode,
                "error": "no accounts",
                "stats": stats.__dict__,
            }

        stats.accounts_total = len(accounts_for_ingest)
        worker_count = min(self.workers, max(1, len(accounts_for_ingest)))
        results: List[AccountResult] = []

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(self._grok_fetch_account, account): account
                for account in accounts_for_ingest
            }
            for idx, future in enumerate(as_completed(futures), start=1):
                account = futures[future]
                handle = str(account.get("handle") or "")
                try:
                    result = future.result()
                except Exception as e:
                    result = AccountResult(
                        handle=handle,
                        ok=False,
                        elapsed_sec=0.0,
                        error=str(e)[:300],
                        account_profile={},
                        posts=[],
                    )
                results.append(result)

                if result.ok:
                    stats.accounts_success += 1
                else:
                    stats.accounts_failed += 1
                    errors.append(f"{handle}:{result.error}")

                logger.info(
                    "[STOCK_X_FETCH_PROGRESS] "
                    f"idx={idx}/{len(accounts_for_ingest)} handle={handle} "
                    f"ok={result.ok} posts={len(result.posts)} elapsed={result.elapsed_sec:.2f}s"
                )

        post_count, signal_count, events_count = self._persist_account_results(
            account_id_map=account_id_map,
            results=results,
        )
        stats.posts_written = post_count
        stats.signals_written = signal_count
        stats.events_written = events_count

        freshest_post_at = _find_freshest_post(results)
        self._upsert_source_health(stats=stats, freshest_post_at=freshest_post_at)

        status = "success" if stats.accounts_failed == 0 else "failed"
        self._finish_run_record(
            status=status,
            stats=stats,
            started_at=started_at,
            error_summary="; ".join(errors)[:5000],
        )

        logger.info(
            "[STOCK_X_RUN_DONE] "
            f"run_id={self.run_id} accounts={stats.accounts_total} success={stats.accounts_success} "
            f"failed={stats.accounts_failed} posts={stats.posts_written} "
            f"signals={stats.signals_written} events={stats.events_written}"
        )
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "stats": stats.__dict__,
            "error_summary": "; ".join(errors)[:1000],
        }


def _safe_text(value: Any, max_len: int) -> str:
    return str(value or "").strip()[:max_len]


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp(value: float, left: float, right: float) -> float:
    return max(left, min(right, value))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip()
        if not text:
            return _now_utc().isoformat()
        text = text.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except Exception:
            return _now_utc().isoformat()

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _chunks(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    if size <= 0:
        size = 100
    for i in range(0, len(values), size):
        yield values[i : i + size]


def _normalize_metrics(raw_metrics: Any) -> Dict[str, int]:
    metrics = raw_metrics if isinstance(raw_metrics, dict) else {}
    result: Dict[str, int] = {}
    for key in ("likes", "reposts", "replies", "views"):
        try:
            result[key] = max(0, int(float(metrics.get(key, 0))))
        except Exception:
            result[key] = 0
    return result


def _normalize_ticker(value: Any) -> str:
    text = str(value or "").strip().upper()
    text = text.lstrip("$")
    if not text:
        return ""
    if not re.fullmatch(r"[A-Z]{1,5}", text):
        return ""
    return text


def _extract_first_ticker(text: str) -> str:
    for match in TICKER_PATTERN.findall(text.upper()):
        if 1 <= len(match) <= 5:
            return match
    return ""


def _normalize_side(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"LONG", "SHORT", "NEUTRAL"}:
        return text
    return "NEUTRAL"


def _normalize_event_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in EVENT_TYPE_ALLOW:
        return EVENT_TYPE_MAP.get(text, "news")
    return "news"


def _event_ttl_hours(event_type: str) -> int:
    mapping = {
        "earnings": 96,
        "macro": 120,
        "policy": 120,
        "flow": 72,
        "sector": 96,
        "news": 72,
    }
    return mapping.get(event_type, 72)


def _health_status(ok: bool, post_count: int, signal_count: int) -> str:
    if not ok:
        return "critical"
    if post_count <= 0:
        return "degraded"
    if signal_count <= 0:
        return "degraded"
    return "healthy"


def _seconds_since_iso(value: str) -> int:
    text = str(value or "").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return 999999
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, int((_now_utc() - dt.astimezone(timezone.utc)).total_seconds()))


def _find_freshest_post(results: Sequence[AccountResult]) -> str:
    freshest = ""
    freshest_age = 10**9
    for result in results:
        for post in result.posts:
            posted_at = str(post.get("posted_at") or "")
            age = _seconds_since_iso(posted_at)
            if age < freshest_age:
                freshest_age = age
                freshest = posted_at
    return freshest


def _default_run_id(mode: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"stock-x-{mode}-{ts}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stock X source ingest")
    parser.add_argument(
        "--mode",
        choices=["full", "import", "ingest"],
        default="full",
        help="full=导入账号并采集；import=仅导入账号；ingest=仅采集",
    )
    parser.add_argument(
        "--accounts-file",
        default="us_stock_x_list.txt",
        help="账号清单 TSV 文件",
    )
    parser.add_argument("--topn", type=int, default=30, help="入选账号数量")
    parser.add_argument("--post-limit", type=int, default=20, help="每账号最多采集帖子数量")
    parser.add_argument("--workers", type=int, default=6, help="并发账号采集线程数")
    parser.add_argument("--run-id", default="", help="自定义 run_id")
    parser.add_argument("--dry-run", action="store_true", help="仅演练，不写库")
    parser.add_argument(
        "--no-deactivate-others",
        action="store_true",
        help="导入模式下不自动停用未入选账号",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_id = args.run_id or _default_run_id(args.mode)

    ingestor = StockXSourceIngestor(
        mode=args.mode,
        accounts_file=args.accounts_file,
        topn=args.topn,
        post_limit=args.post_limit,
        workers=args.workers,
        run_id=run_id,
        dry_run=bool(args.dry_run),
        deactivate_others=not bool(args.no_deactivate_others),
    )
    result = ingestor.run()
    logger.info(f"[STOCK_X_RESULT] {json.dumps(result, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
