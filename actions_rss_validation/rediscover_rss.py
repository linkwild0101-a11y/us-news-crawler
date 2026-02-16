#!/usr/bin/env python3
import json
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import requests
from requests.exceptions import RequestException
from xml.etree import ElementTree as ET

INPUT_FILE = "rss_validation_report_20260216_091927.json"
PREVIOUS_RESULTS_FILE = "rss_rediscovery_results.json"
OUTPUT_FILE = "rss_rediscovery_results_search.json"
OUTPUT_CSV = "rss_rediscovery_updates_search.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

COMMON_FEED_PATHS = [
    "/feed",
    "/feed/",
    "/rss",
    "/rss/",
    "/rss.xml",
    "/feed.xml",
    "/atom.xml",
    "/index.xml",
    "/news/feed",
    "/news/rss",
    "/news/rss.xml",
    "/blog/feed",
    "/blog/rss",
    "/?feed=rss2",
    "/?output=rss",
    "/feeds/posts/default",
]

DISCOVERY_PAGES = ["/", "/news", "/blog", "/press", "/latest", "/updates"]
SEARCH_QUERIES = [
    'site:{domain} (rss OR feed OR atom OR "rss.xml" OR "atom.xml")',
]
REQUEST_TIMEOUT = 6.0
MAX_SEARCH_RESULT_PAGES = 4
MAX_CANDIDATES_PER_DOMAIN = 45


def root_domain(host: str) -> str:
    if not host:
        return ""
    host = host.lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    second_level_suffixes = {
        "co.uk",
        "org.uk",
        "gov.uk",
        "ac.uk",
        "com.au",
        "net.au",
        "org.au",
        "co.jp",
        "com.br",
        "com.cn",
        "com.hk",
        "co.nz",
        "com.sg",
        "com.tr",
    }
    tail2 = ".".join(parts[-2:])
    if tail2 in second_level_suffixes and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{scheme}://{netloc}{path}{query}"


def fetch_url(session: requests.Session, url: str, timeout: float = REQUEST_TIMEOUT) -> Optional[requests.Response]:
    try:
        return session.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
    except RequestException:
        return None


def extract_feed_links_from_html(html: str, base_url: str) -> Set[str]:
    links: Set[str] = set()

    for tag in re.findall(r"<link\\b[^>]*>", html, flags=re.IGNORECASE):
        if not re.search(r"type\\s*=\\s*[\"']application/(rss\\+xml|atom\\+xml|xml)[\"']", tag, flags=re.IGNORECASE):
            continue
        href_m = re.search(r"href\\s*=\\s*[\"']([^\"'>]+)[\"']", tag, flags=re.IGNORECASE)
        if href_m:
            href = href_m.group(1).strip()
            if href and not href.startswith(("javascript:", "mailto:", "#")):
                links.add(urljoin(base_url, href))

    for href in re.findall(r"href\\s*=\\s*[\"']([^\"'>]+)[\"']", html, flags=re.IGNORECASE):
        h = href.strip()
        if not h or h.startswith(("javascript:", "mailto:", "#")):
            continue
        hl = h.lower()
        if any(token in hl for token in ["rss", "feed", "atom", ".xml", "?feed="]):
            links.add(urljoin(base_url, h))

    return links


def is_probable_feed_content(content_type: str, text_head: str) -> bool:
    ct = (content_type or "").lower()
    th = (text_head or "").lower()
    if any(t in ct for t in ["rss", "atom", "xml"]):
        return True
    if "<rss" in th or "<feed" in th or "rdf:rdf" in th:
        return True
    return False


def parse_feed_entries(xml_bytes: bytes) -> Tuple[bool, int, str]:
    b = xml_bytes.lstrip()
    try:
        root = ET.fromstring(b)
    except ET.ParseError:
        return False, 0, "xml_parse_error"

    root_name = root.tag.lower().split("}")[-1]
    if root_name not in {"rss", "feed", "rdf"}:
        return False, 0, f"unexpected_root:{root_name}"

    count = len(root.findall(".//item")) + len(root.findall(".//{*}entry"))
    return True, count, "ok"


def validate_feed(session: requests.Session, url: str) -> Dict[str, object]:
    resp = fetch_url(session, url)
    if not resp:
        return {"ok": False, "reason": "request_failed"}
    if resp.status_code >= 400:
        return {"ok": False, "reason": f"http_{resp.status_code}"}

    content_type = resp.headers.get("Content-Type", "")
    text_head = resp.text[:6000] if resp.text else ""
    if not is_probable_feed_content(content_type, text_head):
        return {"ok": False, "reason": "not_feed_like"}

    ok_xml, entries_count, reason = parse_feed_entries(resp.content)
    if not ok_xml:
        return {"ok": False, "reason": reason}
    if entries_count <= 0:
        return {"ok": False, "reason": "feed_empty"}

    return {
        "ok": True,
        "feed_url": resp.url,
        "entries_count": entries_count,
        "http_status": resp.status_code,
        "content_type": content_type,
    }


def _normalize_candidate_url(raw_url: str) -> Optional[str]:
    if not raw_url:
        return None
    u = unescape(raw_url).strip()
    if u.startswith("//"):
        u = "https:" + u
    if u.startswith("/") and not u.startswith("//"):
        return None
    if u.startswith("http://") or u.startswith("https://"):
        return u
    return None


def _extract_bing_links(html: str) -> List[str]:
    urls: List[str] = []
    # prioritize normal web result blocks
    for m in re.finditer(r'<li class="b_algo"[^>]*>.*?<h2><a href="([^"]+)"', html, flags=re.IGNORECASE | re.DOTALL):
        u = _normalize_candidate_url(m.group(1))
        if u:
            urls.append(u)
    if not urls:
        for m in re.finditer(r'<a[^>]+href="(https?://[^"]+)"', html, flags=re.IGNORECASE):
            u = _normalize_candidate_url(m.group(1))
            if u:
                urls.append(u)
    return urls


def _extract_duckduckgo_links(html: str) -> List[str]:
    urls: List[str] = []
    for m in re.finditer(r'href="([^"]*duckduckgo\.com/l/\?[^\"]+)"', html, flags=re.IGNORECASE):
        link = unescape(m.group(1))
        if link.startswith("//"):
            link = "https:" + link
        parsed = urlparse(link)
        q = parse_qs(parsed.query)
        uddg = q.get("uddg", [])
        if uddg:
            u = unquote(uddg[0])
            nu = _normalize_candidate_url(u)
            if nu:
                urls.append(nu)
    if not urls:
        for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"', html, flags=re.IGNORECASE):
            u = _normalize_candidate_url(m.group(1))
            if u:
                urls.append(u)
    return urls


def _looks_feed_like_url(url: str) -> bool:
    ul = url.lower()
    return any(token in ul for token in ["rss", "feed", "atom", ".xml", "?feed=", "output=rss"])


def search_engine_candidates(session: requests.Session, domain: str, timeout: float = REQUEST_TIMEOUT) -> Tuple[Set[str], Set[str]]:
    feed_like: Set[str] = set()
    pages: Set[str] = set()

    block_hosts = {"bing.com", "duckduckgo.com", "microsoft.com"}

    def accept_candidate(url: str) -> bool:
        h = (urlparse(url).hostname or "").lower()
        if not h or any(h == b or h.endswith("." + b) for b in block_hosts):
            return False
        return root_domain(h) == domain

    for query_tpl in SEARCH_QUERIES:
        query = query_tpl.format(domain=domain)
        encoded_q = quote_plus(query)

        bing_url = f"https://www.bing.com/search?q={encoded_q}&count=10"
        r_bing = fetch_url(session, bing_url, timeout=timeout)
        if r_bing and r_bing.status_code < 400 and r_bing.text:
            for u in _extract_bing_links(r_bing.text[:300000]):
                if not accept_candidate(u):
                    continue
                (feed_like if _looks_feed_like_url(u) else pages).add(u)

        ddg_url = f"https://duckduckgo.com/html/?q={encoded_q}"
        r_ddg = fetch_url(session, ddg_url, timeout=timeout)
        if r_ddg and r_ddg.status_code < 400 and r_ddg.text:
            for u in _extract_duckduckgo_links(r_ddg.text[:300000]):
                if not accept_candidate(u):
                    continue
                (feed_like if _looks_feed_like_url(u) else pages).add(u)

    return feed_like, pages


def discover_domain(domain: str, timeout: float = REQUEST_TIMEOUT) -> Dict[str, object]:
    session = requests.Session()
    session.headers.update(HEADERS)

    candidate_weights: Dict[str, int] = {}

    def add_candidate(url: str, weight: int) -> None:
        try:
            n = normalize_url(url)
        except Exception:
            return
        if any(n.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".pdf", ".js", ".css"]):
            return
        candidate_weights[n] = max(weight, candidate_weights.get(n, 0))

    # Step 1: search engine discovery
    search_feed_links, search_pages = search_engine_candidates(session, domain, timeout=timeout)
    for link in search_feed_links:
        add_candidate(link, 120)

    # Step 2: scrape search-result pages for rel=alternate/rss links
    for page_url in list(search_pages)[:MAX_SEARCH_RESULT_PAGES]:
        r = fetch_url(session, page_url, timeout=timeout)
        if not r or r.status_code >= 400:
            continue
        ct = (r.headers.get("Content-Type") or "").lower()
        if "html" not in ct and "text" not in ct:
            continue
        for feed_link in extract_feed_links_from_html(r.text[:300000], r.url):
            add_candidate(feed_link, 100)

    # Step 3: fallback to common feed paths
    base_hosts = [f"https://{domain}", f"https://www.{domain}"]
    for host in base_hosts:
        for p in COMMON_FEED_PATHS:
            add_candidate(urljoin(host, p), 50)

    # Step 4: fallback to site pages
    for host in base_hosts:
        for page in DISCOVERY_PAGES:
            page_url = urljoin(host, page)
            r = fetch_url(session, page_url, timeout=timeout)
            if not r or r.status_code >= 400:
                continue
            ct = (r.headers.get("Content-Type") or "").lower()
            if "html" not in ct and "xml" not in ct and "text" not in ct:
                continue
            feed_links = extract_feed_links_from_html(r.text[:300000], r.url)
            for feed_link in feed_links:
                add_candidate(feed_link, 90 if page == "/" else 70)

    ordered_candidates = sorted(candidate_weights.items(), key=lambda x: (-x[1], x[0]))

    tried: List[str] = []
    failures: List[Dict[str, str]] = []
    for candidate, _weight in ordered_candidates[:MAX_CANDIDATES_PER_DOMAIN]:
        tried.append(candidate)
        v = validate_feed(session, candidate)
        if v.get("ok"):
            return {
                "domain": domain,
                "found": True,
                "feed_url": v.get("feed_url"),
                "entries_count": v.get("entries_count"),
                "http_status": v.get("http_status"),
                "content_type": v.get("content_type"),
                "tried_count": len(tried),
                "total_candidates": len(ordered_candidates),
                "search_feed_candidates": len(search_feed_links),
                "search_page_candidates": len(search_pages),
            }
        failures.append({"url": candidate, "reason": str(v.get("reason"))})

    return {
        "domain": domain,
        "found": False,
        "reason": "no_valid_feed_found",
        "tried_count": len(tried),
        "total_candidates": len(ordered_candidates),
        "search_feed_candidates": len(search_feed_links),
        "search_page_candidates": len(search_pages),
        "sample_failures": failures[:6],
    }


def load_previous_found_map() -> Dict[str, dict]:
    path = Path(PREVIOUS_RESULTS_FILE)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    domain_results = data.get("domain_results", [])
    found_map: Dict[str, dict] = {}
    for row in domain_results:
        d = row.get("domain")
        if d and row.get("found"):
            found_map[d] = row
    return found_map


def main() -> None:
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = data.get("results", [])
    failed_entries = [r for r in results if r.get("status") != "working"]

    domain_to_entries: Dict[str, List[dict]] = defaultdict(list)
    for item in failed_entries:
        host = urlparse(item.get("rss_url", "")).hostname or ""
        d = root_domain(host)
        if d:
            domain_to_entries[d].append(item)

    domains = sorted(domain_to_entries.keys())
    previous_found_map = load_previous_found_map()

    domains_to_check = [d for d in domains if d not in previous_found_map]
    domain_results: Dict[str, dict] = dict(previous_found_map)

    started = time.time()
    if domains_to_check:
        with ThreadPoolExecutor(max_workers=8) as ex:
            fut_to_domain = {ex.submit(discover_domain, d): d for d in domains_to_check}
            for i, fut in enumerate(as_completed(fut_to_domain), 1):
                d = fut_to_domain[fut]
                try:
                    r = fut.result()
                except Exception as e:
                    r = {"domain": d, "found": False, "reason": f"exception:{e}"}
                domain_results[d] = r
                if i % 20 == 0 or i == len(domains_to_check):
                    print(f"progress: {i}/{len(domains_to_check)} domains checked (search+fallback)")

    elapsed = round(time.time() - started, 2)

    updates = []
    for d, entries in domain_to_entries.items():
        dr = domain_results.get(d, {})
        if not dr.get("found"):
            continue
        new_feed = dr.get("feed_url")
        for e in entries:
            updates.append(
                {
                    "id": e.get("id"),
                    "name": e.get("name"),
                    "category": e.get("category"),
                    "old_rss_url": e.get("rss_url"),
                    "new_rss_url": new_feed,
                    "domain": d,
                    "discovered_entries_count": dr.get("entries_count"),
                }
            )

    found_domains = sum(1 for d in domains if domain_results.get(d, {}).get("found"))
    unresolved_domains = len(domains) - found_domains

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": INPUT_FILE,
        "stats": {
            "failed_entries": len(failed_entries),
            "unique_domains": len(domains),
            "previous_found_domains_reused": len(previous_found_map),
            "newly_checked_domains": len(domains_to_check),
            "found_domains": found_domains,
            "unresolved_domains": unresolved_domains,
            "entry_updates": len(updates),
            "elapsed_seconds": elapsed,
        },
        "domain_results": [domain_results[d] for d in sorted(domain_results.keys())],
        "entry_updates": sorted(updates, key=lambda x: x["id"] or 0),
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_CSV, "w", encoding="utf-8") as f:
        f.write("id,name,category,domain,old_rss_url,new_rss_url,discovered_entries_count\n")
        for u in out["entry_updates"]:
            vals = [
                str(u.get("id", "")),
                u.get("name", ""),
                u.get("category", ""),
                u.get("domain", ""),
                u.get("old_rss_url", ""),
                u.get("new_rss_url", ""),
                str(u.get("discovered_entries_count", "")),
            ]
            escaped = []
            for v in vals:
                s = str(v).replace('"', '""')
                escaped.append(f'"{s}"')
            f.write(",".join(escaped) + "\n")

    print(json.dumps(out["stats"], ensure_ascii=False, indent=2))
    print(f"wrote: {OUTPUT_FILE}")
    print(f"wrote: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
