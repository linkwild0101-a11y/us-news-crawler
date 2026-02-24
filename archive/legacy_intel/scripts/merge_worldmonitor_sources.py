#!/usr/bin/env python3
"""从 worldmonitor 提取推荐 RSS 源并合并到本地 sources.json。"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Set

ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = ROOT / "data" / "sources.json"
WORLDMONITOR_RSS_FILE = ROOT / "data" / "worldmonitor_rss_sources.json"
RECOMMENDED_FILE = ROOT / "data" / "worldmonitor_recommended_sources.json"

MILITARY_SECTIONS = {"security", "crisis"}
POLITICS_SECTIONS = {
    "politics",
    "regional",
    "middleeast",
    "africa",
    "asia",
    "latam",
    "gov",
    "thinktanks",
    "policy",
    "gccNews",
}
TECH_SECTIONS = {
    "tech",
    "ai",
    "cloud",
    "dev",
    "github",
    "hardware",
    "producthunt",
    "startups",
    "regionalStartups",
    "vcblogs",
    "layoffs",
    "podcasts",
}
ECONOMY_SECTIONS = {
    "finance",
    "markets",
    "forex",
    "bonds",
    "economic",
    "fintech",
    "institutional",
    "analysis",
    "derivatives",
    "commodities",
    "energy",
    "funding",
    "ipo",
    "unicorns",
    "accelerators",
    "centralbanks",
    "crypto",
    "regulation",
}

ALLOWED_SECTIONS = (
    MILITARY_SECTIONS | POLITICS_SECTIONS | TECH_SECTIONS | ECONOMY_SECTIONS
)

CATEGORY_BY_SECTION = {
    **{section: "military" for section in MILITARY_SECTIONS},
    **{section: "politics" for section in POLITICS_SECTIONS},
    **{section: "tech" for section in TECH_SECTIONS},
    **{section: "economy" for section in ECONOMY_SECTIONS},
}


def _normalize_url(url: str) -> str:
    return (url or "").strip()


def _build_source_record(raw: Dict, next_id: int) -> Dict:
    section = raw.get("section", "")
    wrapper = raw.get("wrapper", "")
    category = CATEGORY_BY_SECTION.get(section, "politics")

    return {
        "id": next_id,
        "name": raw.get("name", "").strip(),
        "listing_url": raw.get("source_url", "").strip(),
        "rss_url": raw.get("source_url", "").strip(),
        "description": f"Imported from worldmonitor ({section})",
        "category": category,
        "anti_scraping": "railway" if wrapper == "railwayRss" else "None",
        "status": "active",
    }


def load_json(path: Path) -> List[Dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    if not SOURCES_FILE.exists():
        raise FileNotFoundError(f"sources.json not found: {SOURCES_FILE}")
    if not WORLDMONITOR_RSS_FILE.exists():
        raise FileNotFoundError(
            f"worldmonitor rss file not found: {WORLDMONITOR_RSS_FILE}"
        )

    current_sources = load_json(SOURCES_FILE)
    worldmonitor_rows = load_json(WORLDMONITOR_RSS_FILE)

    existing_urls: Set[str] = {
        _normalize_url(row.get("rss_url", ""))
        for row in current_sources
        if row.get("rss_url")
    }
    source_by_url: Dict[str, Dict] = {
        _normalize_url(row.get("rss_url", "")): row
        for row in current_sources
        if row.get("rss_url")
    }
    max_id = max((int(row.get("id", 0)) for row in current_sources), default=0)

    recommended_rows: List[Dict] = []
    seen_candidate_urls: Set[str] = set()
    added = 0
    updated = 0
    skipped_existing = 0

    for row in worldmonitor_rows:
        url = _normalize_url(row.get("source_url", ""))
        section = row.get("section", "")
        domain = row.get("domain", "")

        if not url.startswith("http"):
            continue
        if section not in ALLOWED_SECTIONS:
            continue
        if domain == "news.google.com":
            continue

        if url in seen_candidate_urls:
            continue

        current = source_by_url.get(url)
        if current:
            source = _build_source_record(row, int(current["id"]))
            source["status"] = current.get("status", "active")
            if str(current.get("description", "")).startswith("Imported from worldmonitor"):
                fields = ("name", "listing_url", "category", "anti_scraping", "description")
                changed = False
                for field in fields:
                    if current.get(field) != source.get(field):
                        current[field] = source[field]
                        changed = True
                if changed:
                    updated += 1
            else:
                skipped_existing += 1
            recommended_rows.append(
                {
                    **source,
                    "source_origin": "worldmonitor",
                }
            )
            seen_candidate_urls.add(url)
            continue

        max_id += 1
        source = _build_source_record(row, max_id)
        source["source_origin"] = "worldmonitor"
        recommended_rows.append(source)
        current_sources.append({k: v for k, v in source.items() if k != "source_origin"})
        seen_candidate_urls.add(url)
        existing_urls.add(url)
        source_by_url[url] = current_sources[-1]
        added += 1

    # 写入推荐源清单（用于同步 Supabase）
    RECOMMENDED_FILE.write_text(
        json.dumps(recommended_rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    SOURCES_FILE.write_text(
        json.dumps(current_sources, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    cat_counter = Counter(row["category"] for row in recommended_rows)

    print(f"Total sources after merge: {len(current_sources)}")
    print(f"Worldmonitor candidate sources: {len(recommended_rows)}")
    print(f"Added sources: {added}")
    print(f"Updated existing worldmonitor sources: {updated}")
    print(f"Skipped existing non-worldmonitor sources: {skipped_existing}")
    print(
        "Worldmonitor categories: "
        + ", ".join(f"{k}={v}" for k, v in sorted(cat_counter.items()))
    )
    print(f"Wrote: {RECOMMENDED_FILE.relative_to(ROOT)}")
    print(f"Updated: {SOURCES_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
