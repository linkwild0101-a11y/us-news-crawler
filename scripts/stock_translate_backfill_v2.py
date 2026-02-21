#!/usr/bin/env python3
"""Stock V2 历史事件中文翻译回填脚本。"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from supabase import Client, create_client

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.llm_client import LLMClient  # noqa: E402


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


@dataclass
class EventCandidate:
    """待翻译事件。"""

    event_id: int
    summary: str
    details: Dict[str, Any]


def _contains_chinese(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _normalize_text(text: str, max_len: int) -> str:
    return str(text or "").strip()[:max_len]


class StockV2TranslationBackfill:
    """Stock V2 历史中文翻译回填执行器。"""

    def __init__(self, workers: int, dry_run: bool, force: bool):
        self.supabase = self._init_supabase()
        self.workers = max(1, workers)
        self.dry_run = dry_run
        self.force = force
        self._thread_local = threading.local()

        if not (os.getenv("DASHSCOPE_API_KEY") or os.getenv("ALIBABA_API_KEY")):
            raise ValueError("缺少 DASHSCOPE_API_KEY / ALIBABA_API_KEY，无法执行翻译回填")

    def _init_supabase(self) -> Client:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("缺少 SUPABASE_URL / SUPABASE_KEY")
        return create_client(url, key)

    def _get_llm_client(self) -> LLMClient:
        """Thread-local LLM client for concurrent translation."""
        client = getattr(self._thread_local, "llm_client", None)
        if client is None:
            client = LLMClient()
            self._thread_local.llm_client = client
        return client

    def _load_batch(
        self,
        offset: int,
        batch_size: int,
        active_only: bool,
    ) -> List[Dict[str, Any]]:
        query = (
            self.supabase.table("stock_events_v2")
            .select("id,summary,details,is_active")
            .order("id", desc=True)
            .range(offset, offset + batch_size - 1)
        )
        if active_only:
            query = query.eq("is_active", True)
        return query.execute().data or []

    def _build_candidates(
        self,
        limit: int,
        scan_limit: int,
        batch_size: int,
        active_only: bool,
    ) -> Tuple[List[EventCandidate], int]:
        candidates: List[EventCandidate] = []
        scanned = 0
        offset = 0

        while len(candidates) < limit and scanned < scan_limit:
            rows = self._load_batch(offset=offset, batch_size=batch_size, active_only=active_only)
            if not rows:
                break
            scanned += len(rows)

            for row in rows:
                event_id = int(row.get("id") or 0)
                if event_id <= 0:
                    continue
                details = row.get("details")
                detail_map = details if isinstance(details, dict) else {}

                title_zh = _normalize_text(detail_map.get("title_zh"), 180)
                summary_zh = _normalize_text(detail_map.get("summary_zh"), 220)
                if not self.force and title_zh and summary_zh:
                    continue

                candidates.append(
                    EventCandidate(
                        event_id=event_id,
                        summary=_normalize_text(row.get("summary"), 220),
                        details=detail_map,
                    )
                )
                if len(candidates) >= limit:
                    break

            if len(rows) < batch_size:
                break
            offset += batch_size

        return candidates, scanned

    def _translate_pair(self, title_src: str, summary_src: str) -> Tuple[str, str]:
        title_src = _normalize_text(title_src, 240)
        summary_src = _normalize_text(summary_src, 420)
        if not title_src and not summary_src:
            return "", ""
        if not summary_src:
            summary_src = title_src
        if not title_src:
            title_src = summary_src[:120]

        if _contains_chinese(title_src) and _contains_chinese(summary_src):
            return title_src[:180], summary_src[:220]

        client = self._get_llm_client()
        prompt = (
            "你是财经新闻翻译助手。请把下面英文内容翻译成自然流畅的中文，"
            "只输出 JSON：{\"title_zh\":\"<=40字\",\"summary_zh\":\"<=80字\"}。\n"
            f"title: {title_src}\n"
            f"summary: {summary_src}"
        )
        try:
            result = client.summarize(prompt, use_cache=True)
            title_zh = _normalize_text(result.get("title_zh"), 180)
            summary_zh = _normalize_text(result.get("summary_zh"), 220)
            if not title_zh:
                title_zh = _normalize_text(client.translate_text(title_src, use_cache=True), 180)
            if not summary_zh:
                summary_zh = _normalize_text(client.translate_text(summary_src, use_cache=True), 220)
            return title_zh, summary_zh
        except Exception as e:
            logger.warning(f"[STOCK_V2_TRANSLATE_FALLBACK] error={str(e)[:120]}")
            title_zh = _normalize_text(client.translate_text(title_src, use_cache=True), 180)
            summary_zh = _normalize_text(client.translate_text(summary_src, use_cache=True), 220)
            return title_zh, summary_zh

    def _prepare_update(self, row: EventCandidate) -> Optional[Tuple[int, Dict[str, Any]]]:
        details = dict(row.details or {})
        title_src = _normalize_text(details.get("title"), 240)
        summary_src = _normalize_text(row.summary or details.get("summary"), 420)
        if not title_src:
            title_src = summary_src
        if not summary_src:
            summary_src = title_src

        if not title_src and not summary_src:
            return None

        title_zh_existing = _normalize_text(details.get("title_zh"), 180)
        summary_zh_existing = _normalize_text(details.get("summary_zh"), 220)

        title_zh = title_zh_existing if (title_zh_existing and not self.force) else ""
        summary_zh = summary_zh_existing if (summary_zh_existing and not self.force) else ""

        if not title_zh or not summary_zh:
            translated_title, translated_summary = self._translate_pair(title_src, summary_src)
            if not title_zh:
                title_zh = translated_title or title_src[:180]
            if not summary_zh:
                summary_zh = translated_summary or summary_src[:220]

        if (title_zh == title_zh_existing) and (summary_zh == summary_zh_existing):
            return None

        details["title_zh"] = title_zh[:180]
        details["summary_zh"] = summary_zh[:220]
        return row.event_id, details

    def _apply_update(self, event_id: int, details: Dict[str, Any]) -> None:
        if self.dry_run:
            return
        (
            self.supabase.table("stock_events_v2")
            .update({"details": details})
            .eq("id", event_id)
            .execute()
        )

    def run(
        self,
        limit: int,
        scan_limit: int,
        batch_size: int,
        active_only: bool,
    ) -> Dict[str, int]:
        logger.info(
            f"[STOCK_V2_TRANSLATE_START] limit={limit} scan_limit={scan_limit} "
            f"batch={batch_size} workers={self.workers} active_only={active_only} dry_run={self.dry_run}"
        )

        candidates, scanned = self._build_candidates(
            limit=limit,
            scan_limit=scan_limit,
            batch_size=batch_size,
            active_only=active_only,
        )
        logger.info(
            f"[STOCK_V2_TRANSLATE_CANDIDATES] scanned={scanned} candidates={len(candidates)}"
        )
        if not candidates:
            return {"scanned": scanned, "candidates": 0, "translated": 0, "updated": 0}

        translated = 0
        updated = 0
        worker_count = min(self.workers, len(candidates))

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {executor.submit(self._prepare_update, row): row.event_id for row in candidates}
            for idx, future in enumerate(as_completed(futures), start=1):
                event_id = futures[future]
                try:
                    payload = future.result()
                except Exception as e:
                    logger.warning(
                        f"[STOCK_V2_TRANSLATE_ITEM_FAILED] event_id={event_id} error={str(e)[:120]}"
                    )
                    continue

                translated += 1
                if not payload:
                    continue
                target_event_id, details = payload
                try:
                    self._apply_update(target_event_id, details)
                    updated += 1
                except Exception as e:
                    logger.warning(
                        f"[STOCK_V2_TRANSLATE_UPDATE_FAILED] event_id={target_event_id} error={str(e)[:120]}"
                    )

                if idx % 50 == 0:
                    logger.info(
                        f"[STOCK_V2_TRANSLATE_PROGRESS] done={idx}/{len(candidates)} updated={updated}"
                    )

        logger.info(
            f"[STOCK_V2_TRANSLATE_DONE] scanned={scanned} candidates={len(candidates)} "
            f"translated={translated} updated={updated}"
        )
        return {
            "scanned": scanned,
            "candidates": len(candidates),
            "translated": translated,
            "updated": updated,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock V2 历史中文翻译回填")
    parser.add_argument("--limit", type=int, default=1200, help="最多翻译多少条候选事件")
    parser.add_argument("--scan-limit", type=int, default=20000, help="最多扫描多少条事件")
    parser.add_argument("--batch-size", type=int, default=500, help="分页批次大小")
    parser.add_argument("--workers", type=int, default=8, help="LLM 并发 worker 数")
    parser.add_argument("--active-only", action="store_true", help="仅处理 is_active=true 的事件")
    parser.add_argument("--force", action="store_true", help="强制重译（覆盖已有中文字段）")
    parser.add_argument("--dry-run", action="store_true", help="只执行翻译，不写回数据库")
    args = parser.parse_args()

    engine = StockV2TranslationBackfill(
        workers=args.workers,
        dry_run=args.dry_run,
        force=args.force,
    )
    metrics = engine.run(
        limit=max(1, args.limit),
        scan_limit=max(1, args.scan_limit),
        batch_size=max(1, args.batch_size),
        active_only=bool(args.active_only),
    )
    logger.info("[STOCK_V2_TRANSLATE_METRICS] " + ", ".join([f"{k}={v}" for k, v in metrics.items()]))


if __name__ == "__main__":
    main()
