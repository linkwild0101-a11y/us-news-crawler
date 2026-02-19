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


def _same_record(db_row: Dict, target: Dict) -> bool:
    fields = ("name", "rss_url", "listing_url", "category", "anti_scraping", "status")
    for field in fields:
        if (db_row.get(field) or "") != (target.get(field) or ""):
            return False
    return True


def main() -> None:
    if not SUPABASE_KEY:
        raise RuntimeError("未设置 SUPABASE_KEY")
    if not RECOMMENDED_FILE.exists():
        raise FileNotFoundError(f"推荐源文件不存在: {RECOMMENDED_FILE}")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    recommended = json.loads(RECOMMENDED_FILE.read_text(encoding="utf-8"))

    candidates = [
        _to_db_row(source) for source in recommended if source.get("rss_url", "").strip()
    ]
    candidate_urls = sorted({row["rss_url"].strip() for row in candidates})

    existing_map: Dict[str, Dict] = {}
    for batch_urls in _chunks(candidate_urls, 100):
        rows = (
            supabase.table("rss_sources")
            .select("id, name, rss_url, listing_url, category, anti_scraping, status")
            .in_("rss_url", batch_urls)
            .execute()
            .data
        )
        for row in rows:
            existing_map[(row.get("rss_url") or "").strip()] = row

    inserted = 0
    updated = 0
    unchanged = 0
    failed = 0
    tech_constraint_blocked = 0
    failed_rows: List[Dict] = []

    for row in candidates:
        existing = existing_map.get(row["rss_url"].strip())
        if existing and _same_record(existing, row):
            unchanged += 1
            continue

        try:
            if existing:
                supabase.table("rss_sources").update(row).eq("id", existing["id"]).execute()
                updated += 1
            else:
                supabase.table("rss_sources").insert(row).execute()
                inserted += 1
        except Exception as exc:
            msg = str(exc)
            if row["category"] == "tech" and "rss_sources_category_check" in msg:
                tech_constraint_blocked += 1
            else:
                failed += 1
                failed_rows.append({"name": row["name"], "rss_url": row["rss_url"], "error": msg[:240]})

    total = supabase.table("rss_sources").select("id", count="exact").execute().count

    print(f"Recommended total: {len(recommended)}")
    print(f"Inserted: {inserted}")
    print(f"Updated: {updated}")
    print(f"Unchanged: {unchanged}")
    print(f"Tech category blocked by DB constraint: {tech_constraint_blocked}")
    print(f"Failed: {failed}")
    print(f"DB total rss_sources: {total}")
    if failed_rows:
        print("Failure examples:")
        for row in failed_rows[:5]:
            print(f"- {row['name']} | {row['error']}")


if __name__ == "__main__":
    main()
