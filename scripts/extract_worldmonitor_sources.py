#!/usr/bin/env python3
"""
Extract RSS and non-RSS source candidates from worldmonitor.

Outputs:
- data/worldmonitor_rss_sources.json
- data/worldmonitor_rss_new_domains.json
- data/worldmonitor_signal_sources.json
- docs/WORLDMONITOR_SOURCES_EXTRACTED.md
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
WORLDMONITOR_DIR = ROOT / "worldmonitor"
FEEDS_TS = WORLDMONITOR_DIR / "src" / "config" / "feeds.ts"
API_DIR = WORLDMONITOR_DIR / "api"
CURRENT_SOURCES = ROOT / "data" / "sources.json"

OUT_RSS = ROOT / "data" / "worldmonitor_rss_sources.json"
OUT_RSS_NEW = ROOT / "data" / "worldmonitor_rss_new_domains.json"
OUT_SIGNAL = ROOT / "data" / "worldmonitor_signal_sources.json"
OUT_REPORT = ROOT / "docs" / "WORLDMONITOR_SOURCES_EXTRACTED.md"


ENTRY_RE = re.compile(
    r"\{\s*name:\s*'([^']+)'\s*,\s*url:\s*([^,}]+)(?:,\s*type:\s*'([^']+)')?"
)
WRAPPER_RE = re.compile(r"^(rss|railwayRss)\('([^']+)'\)$")
SECTION_RE = re.compile(r"^\s{2}([a-zA-Z0-9_]+):\s*\[$")


@dataclass
class RssEntry:
    variant: str
    section: str
    name: str
    wrapper: str
    source_url: str
    domain: str
    tag_type: str
    google_query_domains: List[str]
    already_in_us_newslist_domain: bool

    def to_dict(self) -> Dict:
        return {
            "variant": self.variant,
            "section": self.section,
            "name": self.name,
            "wrapper": self.wrapper,
            "source_url": self.source_url,
            "domain": self.domain,
            "tag_type": self.tag_type,
            "google_query_domains": self.google_query_domains,
            "already_in_us_newslist_domain": self.already_in_us_newslist_domain,
        }


def load_existing_domains() -> Set[str]:
    if not CURRENT_SOURCES.exists():
        return set()

    rows = json.loads(CURRENT_SOURCES.read_text())
    domains: Set[str] = set()
    for row in rows:
        rss_url = str(row.get("rss_url") or "")
        domain = (urlparse(rss_url).hostname or "").lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if domain:
            domains.add(domain)
    return domains


def parse_google_query_domains(url: str) -> List[str]:
    parsed = urlparse(url)
    if parsed.hostname != "news.google.com":
        return []
    query = parse_qs(parsed.query).get("q", [""])[0]
    query = unquote(query)
    domains = sorted(set(re.findall(r"site:([a-zA-Z0-9.-]+)", query)))
    return [d[4:] if d.startswith("www.") else d for d in domains]


def parse_rss_entries(existing_domains: Set[str]) -> List[RssEntry]:
    lines = FEEDS_TS.read_text().splitlines()
    variant = ""
    section = ""
    results: List[RssEntry] = []

    for raw in lines:
        line = raw.strip()

        if raw.startswith("const FULL_FEEDS"):
            variant = "full"
            section = ""
            continue
        if raw.startswith("const TECH_FEEDS"):
            variant = "tech"
            section = ""
            continue
        if raw.startswith("export const FEEDS"):
            variant = ""
            section = ""
            continue
        if not variant:
            continue

        section_match = SECTION_RE.match(raw)
        if section_match:
            section = section_match.group(1)
            continue

        if "{ name:" not in raw:
            continue

        entry_match = ENTRY_RE.search(raw)
        if not entry_match:
            continue

        name = entry_match.group(1)
        url_expr = entry_match.group(2).strip()
        tag_type = entry_match.group(3) or ""

        wrapper = "unknown"
        source_url = ""

        wrapped = WRAPPER_RE.match(url_expr)
        if wrapped:
            wrapper = wrapped.group(1)
            source_url = wrapped.group(2).strip()
        elif url_expr.startswith("'") and url_expr.endswith("'"):
            wrapper = "direct"
            source_url = url_expr[1:-1].strip()
        elif url_expr.startswith('"') and url_expr.endswith('"'):
            wrapper = "direct"
            source_url = url_expr[1:-1].strip()
        else:
            continue

        domain = (urlparse(source_url).hostname or "").lower()
        if domain.startswith("www."):
            domain = domain[4:]

        google_domains = parse_google_query_domains(source_url)
        already_exists = bool(domain and domain in existing_domains)

        results.append(
            RssEntry(
                variant=variant,
                section=section,
                name=name,
                wrapper=wrapper,
                source_url=source_url,
                domain=domain,
                tag_type=tag_type,
                google_query_domains=google_domains,
                already_in_us_newslist_domain=already_exists,
            )
        )

    # Deduplicate in-source duplicates.
    unique: Dict[Tuple[str, str, str, str], RssEntry] = {}
    for item in results:
        key = (item.variant, item.section, item.name, item.source_url)
        unique[key] = item
    return list(unique.values())


def parse_signal_sources() -> List[Dict]:
    results: List[Dict] = []
    env_re = re.compile(r"process\.env\.([A-Z0-9_]+)")
    domain_re = re.compile(r"https?://([A-Za-z0-9.-]+)")
    useful_re = re.compile(
        r"(acled|gdelt|ucdp|unhcr|hapi|earthquake|firms|outages|faa|nga|"
        r"worldbank|fred|eia|macro|etf|polymarket|coingecko|finnhub|"
        r"yahoo-finance|service-status|climate)",
        re.IGNORECASE,
    )

    for file in sorted(API_DIR.rglob("*.js")):
        rel = file.relative_to(API_DIR)
        if rel.name.startswith("_"):
            continue
        if rel.name.endswith(".test.mjs"):
            continue

        text = file.read_text(errors="ignore")
        env_keys = sorted(set(env_re.findall(text)))
        domains = sorted(set(domain_re.findall(text)))

        endpoint = f"/api/{str(rel).replace('.js', '')}"
        endpoint = endpoint.replace("\\", "/")
        if "/index" in endpoint:
            endpoint = endpoint.replace("/index", "")

        is_signal_like = bool(useful_re.search(str(rel)) or useful_re.search(text))
        if not is_signal_like and not domains:
            continue

        results.append(
            {
                "endpoint": endpoint,
                "file": str(rel),
                "upstream_domains": domains,
                "required_env_keys": env_keys,
                "auth_required": bool(env_keys),
                "signal_or_macro_relevant": is_signal_like,
            }
        )

    return results


def build_new_domain_view(entries: List[RssEntry], existing_domains: Set[str]) -> List[Dict]:
    domain_map: Dict[str, Dict] = {}

    for item in entries:
        domain = item.domain
        if not domain:
            continue
        if domain in existing_domains:
            continue
        agg = domain_map.setdefault(
            domain,
            {
                "domain": domain,
                "sample_names": [],
                "sample_sections": [],
                "sample_urls": [],
                "count": 0,
            },
        )
        agg["count"] += 1
        if len(agg["sample_names"]) < 4 and item.name not in agg["sample_names"]:
            agg["sample_names"].append(item.name)
        if len(agg["sample_sections"]) < 4 and item.section not in agg["sample_sections"]:
            agg["sample_sections"].append(item.section)
        if len(agg["sample_urls"]) < 3 and item.source_url not in agg["sample_urls"]:
            agg["sample_urls"].append(item.source_url)

    return sorted(domain_map.values(), key=lambda row: (-row["count"], row["domain"]))


def write_report(entries: List[RssEntry], new_domains: List[Dict], signals: List[Dict]) -> None:
    total = len(entries)
    full_count = len([e for e in entries if e.variant == "full"])
    tech_count = len([e for e in entries if e.variant == "tech"])
    railway_count = len([e for e in entries if e.wrapper == "railwayRss"])
    google_count = len([e for e in entries if e.domain == "news.google.com"])
    new_domain_count = len(new_domains)

    signal_rows = [row for row in signals if row["signal_or_macro_relevant"]]
    signal_rows = sorted(signal_rows, key=lambda row: row["endpoint"])

    lines: List[str] = []
    lines.append("# Worldmonitor Source Extraction")
    lines.append("")
    lines.append("- Extracted from `worldmonitor` latest `main` branch.")
    lines.append(f"- RSS entries: {total} (full={full_count}, tech={tech_count})")
    lines.append(f"- Railway-proxied RSS entries: {railway_count}")
    lines.append(f"- Google News query feeds: {google_count}")
    lines.append(f"- New RSS domains vs `data/sources.json`: {new_domain_count}")
    lines.append("")
    lines.append("## New RSS Domains (Top 30)")
    lines.append("")
    lines.append("| domain | count | sample names |")
    lines.append("|---|---:|---|")
    for row in new_domains[:30]:
        names = ", ".join(row["sample_names"][:3])
        lines.append(f"| `{row['domain']}` | {row['count']} | {names} |")
    lines.append("")
    lines.append("## Signal / Macro API Sources")
    lines.append("")
    lines.append("| endpoint | env keys | upstream domains |")
    lines.append("|---|---|---|")
    for row in signal_rows:
        env = ", ".join(row["required_env_keys"]) if row["required_env_keys"] else "-"
        domains = ", ".join(row["upstream_domains"][:4]) if row["upstream_domains"] else "-"
        lines.append(f"| `{row['endpoint']}` | {env} | {domains} |")
    lines.append("")
    lines.append("## Output Files")
    lines.append("")
    lines.append("- `data/worldmonitor_rss_sources.json`")
    lines.append("- `data/worldmonitor_rss_new_domains.json`")
    lines.append("- `data/worldmonitor_signal_sources.json`")
    lines.append("")

    OUT_REPORT.write_text("\n".join(lines))


def main() -> None:
    if not FEEDS_TS.exists():
        raise FileNotFoundError(f"feeds.ts not found: {FEEDS_TS}")

    existing_domains = load_existing_domains()
    rss_entries = parse_rss_entries(existing_domains)
    signal_sources = parse_signal_sources()
    new_domain_rows = build_new_domain_view(rss_entries, existing_domains)

    OUT_RSS.write_text(
        json.dumps([item.to_dict() for item in rss_entries], indent=2, ensure_ascii=False)
    )
    OUT_RSS_NEW.write_text(json.dumps(new_domain_rows, indent=2, ensure_ascii=False))
    OUT_SIGNAL.write_text(json.dumps(signal_sources, indent=2, ensure_ascii=False))
    write_report(rss_entries, new_domain_rows, signal_sources)

    print(f"RSS entries: {len(rss_entries)}")
    print(f"New domains vs current sources: {len(new_domain_rows)}")
    print(f"Signal/non-RSS API endpoints: {len(signal_sources)}")
    print("Wrote:")
    print(f"- {OUT_RSS.relative_to(ROOT)}")
    print(f"- {OUT_RSS_NEW.relative_to(ROOT)}")
    print(f"- {OUT_SIGNAL.relative_to(ROOT)}")
    print(f"- {OUT_REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
