#!/usr/bin/env python3
"""导入 worldmonitor 推荐源到 Supabase。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List

from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
RECOMMENDED_FILE = ROOT / "data" / "worldmonitor_recommended_sources.json"
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://lwigqxyfxevldfjdeokp.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BATCH_SIZE = 50


def _to_db_row(source: Dict) -> Dict:
    return {
        "name": source["name"],
        "rss_url": source["rss_url"],
        "listing_url": source.get("listing_url", ""),
        "category": source["category"],
        "anti_scraping": source.get("anti_scraping", "None"),
        "status": source.get("status", "active"),
    }


def _chunks(rows: List[Dict], size: int):
    for idx in range(0, len(rows), size):
        yield rows[idx : idx + size]


def main() -> None:
    if not SUPABASE_KEY:
        raise RuntimeError("未设置 SUPABASE_KEY")
    if not RECOMMENDED_FILE.exists():
        raise FileNotFoundError(f"推荐源文件不存在: {RECOMMENDED_FILE}")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    recommended = json.loads(RECOMMENDED_FILE.read_text(encoding="utf-8"))

    # 先取现有 URL，避免重复插入
    all_existing = supabase.table("rss_sources").select("rss_url").execute().data
    existing_urls = {
        (row.get("rss_url") or "").strip() for row in all_existing if row.get("rss_url")
    }

    pending = [
        _to_db_row(source)
        for source in recommended
        if source.get("rss_url", "").strip() and source.get("rss_url", "").strip() not in existing_urls
    ]

    inserted = 0
    failed = 0

    for batch in _chunks(pending, BATCH_SIZE):
        try:
            supabase.table("rss_sources").insert(batch).execute()
            inserted += len(batch)
        except Exception:
            # 批量失败时回退到逐条，避免单条异常阻塞整体导入
            for row in batch:
                try:
                    supabase.table("rss_sources").insert(row).execute()
                    inserted += 1
                except Exception:
                    failed += 1

    total = supabase.table("rss_sources").select("id", count="exact").execute().count

    print(f"Recommended total: {len(recommended)}")
    print(f"Pending insert: {len(pending)}")
    print(f"Inserted: {inserted}")
    print(f"Failed: {failed}")
    print(f"DB total rss_sources: {total}")


if __name__ == "__main__":
    main()
