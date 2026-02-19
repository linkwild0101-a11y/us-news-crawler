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

ALLOWED_SECTIONS = {
    "politics",
    "regional",
    "middleeast",
    "africa",
    "asia",
    "latam",
    "gov",
    "thinktanks",
    "crisis",
    "security",
    "tech",
    "ai",
    "layoffs",
    "startups",
    "regionalStartups",
    "vcblogs",
    "cloud",
    "crypto",
}

CATEGORY_BY_SECTION = {
    "security": "military",
    "crisis": "military",
    "gov": "politics",
    "politics": "politics",
    "regional": "politics",
    "middleeast": "politics",
    "africa": "politics",
    "asia": "politics",
    "latam": "politics",
    "thinktanks": "politics",
    "tech": "economy",
    "ai": "economy",
    "layoffs": "economy",
    "startups": "economy",
    "regionalStartups": "economy",
    "vcblogs": "economy",
    "cloud": "economy",
    "crypto": "economy",
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
        _normalize_url(row.get("rss_url", "")) for row in current_sources if row.get("rss_url")
    }
    max_id = max((int(row.get("id", 0)) for row in current_sources), default=0)

    recommended_rows: List[Dict] = []
    seen_candidate_urls: Set[str] = set()

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

        # 仅合并当前 sources.json 中不存在的 URL
        if url in existing_urls or url in seen_candidate_urls:
            continue

        max_id += 1
        source = _build_source_record(row, max_id)
        recommended_rows.append(source)
        seen_candidate_urls.add(url)

    # 将推荐源写入单独文件，便于审计
    RECOMMENDED_FILE.write_text(
        json.dumps(recommended_rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    merged_sources = current_sources + recommended_rows
    SOURCES_FILE.write_text(
        json.dumps(merged_sources, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    cat_counter = Counter(row["category"] for row in recommended_rows)

    print(f"Current sources: {len(current_sources)}")
    print(f"Recommended new sources: {len(recommended_rows)}")
    print(f"Merged sources: {len(merged_sources)}")
    print(
        "Recommended categories: "
        + ", ".join(f"{k}={v}" for k, v in sorted(cat_counter.items()))
    )
    print(f"Wrote: {RECOMMENDED_FILE.relative_to(ROOT)}")
    print(f"Updated: {SOURCES_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
