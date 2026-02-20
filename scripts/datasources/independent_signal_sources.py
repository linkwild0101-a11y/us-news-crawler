#!/usr/bin/env python3
"""Independent signal source client for enhanced analysis."""

from __future__ import annotations

import asyncio
import base64
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

import aiohttp

from config.independent_signal_config import (
    INDEPENDENT_SIGNAL_CONFIG,
    INDEPENDENT_SIGNAL_NOTES,
    INDEPENDENT_SIGNAL_TIERS,
    INDEPENDENT_SUPPORTED_KEYS,
)
from scripts.datasources.signal_endpoint_sources import get_worldmonitor_no_auth_sources


class IndependentSignalClient:
    """独立信号源抓取客户端。"""

    def __init__(self, timeout_seconds: int = 12, max_concurrency: int = 6):
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.max_concurrency = max(1, int(max_concurrency))

    @staticmethod
    def _estimate_record_count(payload: object) -> int:
        if isinstance(payload, list):
            return len(payload)
        if not isinstance(payload, dict):
            return 0

        for key in (
            "data",
            "results",
            "items",
            "events",
            "articles",
            "features",
            "rows",
            "records",
            "series",
            "Result",
            "countries",
            "conflicts",
            "anomalies",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
            if isinstance(value, dict):
                return len(value)

        return len(payload)

    @staticmethod
    def _build_sample(payload: object) -> str:
        if isinstance(payload, list) and payload:
            first = payload[0]
        elif isinstance(payload, dict):
            first = payload
            for key in (
                "data",
                "events",
                "articles",
                "features",
                "Result",
                "conflicts",
                "countries",
                "anomalies",
            ):
                value = payload.get(key)
                if isinstance(value, list) and value:
                    first = value[0]
                    break
        else:
            return ""

        if isinstance(first, dict):
            for key in (
                "title",
                "name",
                "event_name",
                "place",
                "country",
                "symbol",
                "zone",
                "location",
                "side_b",
            ):
                value = first.get(key)
                if value:
                    return str(value)[:80]
            return str(first)[:80]
        return str(first)[:80]

    @staticmethod
    def _build_output(
        *,
        source: Dict[str, Any],
        ok: bool,
        status: Optional[int],
        record_count: int,
        sample: str,
        error: str = "",
    ) -> Dict[str, Any]:
        key = str(source.get("key", ""))
        tier = str(source.get("tier", "defer"))
        endpoint = str(source.get("endpoint", ""))
        return {
            "endpoint": endpoint,
            "ok": ok,
            "status": status,
            "record_count": int(record_count),
            "sample": sample,
            "fetched_at": datetime.now().isoformat(),
            "error": error,
            "source_key": key,
            "tier": tier,
            "independent": True,
        }

    async def _get_json(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> tuple[bool, Optional[int], object, str]:
        try:
            async with session.get(
                url,
                params=params,
                headers=headers,
                timeout=self.timeout,
            ) as resp:
                status = resp.status
                if status != 200:
                    return False, status, {}, f"HTTP {status}"
                payload = await resp.json(content_type=None)
                return True, status, payload, ""
        except Exception as e:
            return False, None, {}, str(e)[:160]

    async def _get_text(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> tuple[bool, Optional[int], str, str]:
        try:
            async with session.get(
                url,
                params=params,
                headers=headers,
                timeout=self.timeout,
            ) as resp:
                status = resp.status
                if status != 200:
                    return False, status, "", f"HTTP {status}"
                text = await resp.text()
                return True, status, text, ""
        except Exception as e:
            return False, None, "", str(e)[:160]

    async def _fetch_gdelt_doc(
        self, session: aiohttp.ClientSession, source: Dict[str, Any]
    ) -> Dict[str, Any]:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=1)
        params = {
            "query": "(conflict OR protest OR military OR taiwan)",
            "mode": "ArtList",
            "format": "json",
            "startdatetime": start_date.strftime("%Y%m%d%H%M%S"),
            "enddatetime": end_date.strftime("%Y%m%d%H%M%S"),
        }
        ok, status, payload, error = await self._get_json(
            session,
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params=params,
        )
        count = self._estimate_record_count(payload)
        return self._build_output(
            source=source,
            ok=ok,
            status=status,
            record_count=count,
            sample=self._build_sample(payload),
            error=error,
        )

    async def _fetch_gdelt_geo(
        self, session: aiohttp.ClientSession, source: Dict[str, Any]
    ) -> Dict[str, Any]:
        params = {
            "query": "(taiwan OR china OR south china sea OR military)",
            "format": "json",
            "timespan": "7d",
        }
        ok, status, payload, error = await self._get_json(
            session,
            "https://api.gdeltproject.org/api/v2/geo/geo",
            params=params,
        )
        count = self._estimate_record_count(payload)
        return self._build_output(
            source=source,
            ok=ok,
            status=status,
            record_count=count,
            sample=self._build_sample(payload),
            error=error,
        )

    async def _fetch_earthquakes(
        self, session: aiohttp.ClientSession, source: Dict[str, Any]
    ) -> Dict[str, Any]:
        ok, status, payload, error = await self._get_json(
            session,
            "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson",
        )
        count = self._estimate_record_count(payload)
        return self._build_output(
            source=source,
            ok=ok,
            status=status,
            record_count=count,
            sample=self._build_sample(payload),
            error=error,
        )

    async def _fetch_ucdp_events(
        self, session: aiohttp.ClientSession, source: Dict[str, Any]
    ) -> Dict[str, Any]:
        versions = [
            f"{datetime.utcnow().year - 2000}.1",
            f"{datetime.utcnow().year - 2001}.1",
            "25.1",
            "24.1",
        ]
        for version in versions:
            ok, status, payload, error = await self._get_json(
                session,
                f"https://ucdpapi.pcr.uu.se/api/gedevents/{version}",
                params={"pagesize": 200, "page": 0},
            )
            if ok and isinstance(payload, dict) and isinstance(payload.get("Result"), list):
                count = len(payload.get("Result") or [])
                return self._build_output(
                    source=source,
                    ok=True,
                    status=status,
                    record_count=count,
                    sample=self._build_sample(payload),
                    error="",
                )
            if ok:
                return self._build_output(
                    source=source,
                    ok=False,
                    status=status,
                    record_count=0,
                    sample="",
                    error="invalid_payload",
                )

        return self._build_output(
            source=source,
            ok=False,
            status=None,
            record_count=0,
            sample="",
            error="ucdp_version_discovery_failed",
        )

    async def _fetch_ucdp(
        self, session: aiohttp.ClientSession, source: Dict[str, Any]
    ) -> Dict[str, Any]:
        ok, status, payload, error = await self._get_json(
            session,
            "https://ucdpapi.pcr.uu.se/api/ucdpprioconflict/24.1",
            params={"pagesize": 100, "page": 0},
        )
        count = 0
        if ok and isinstance(payload, dict):
            result = payload.get("Result")
            if isinstance(result, list):
                count = len(result)
            else:
                ok = False
                error = "invalid_payload"

        return self._build_output(
            source=source,
            ok=ok,
            status=status,
            record_count=count,
            sample=self._build_sample(payload),
            error=error,
        )

    async def _fetch_unhcr_population(
        self, session: aiohttp.ClientSession, source: Dict[str, Any]
    ) -> Dict[str, Any]:
        params = {"year": datetime.utcnow().year - 1, "limit": 100, "page": 1}
        ok, status, payload, error = await self._get_json(
            session,
            "https://api.unhcr.org/population/v1/population/",
            params=params,
        )

        if ok and isinstance(payload, dict):
            items = payload.get("items")
            if isinstance(items, list):
                count = len(items)
            else:
                count = self._estimate_record_count(payload)
        else:
            count = 0

        return self._build_output(
            source=source,
            ok=ok,
            status=status,
            record_count=count,
            sample=self._build_sample(payload),
            error=error,
        )

    async def _fetch_hapi(
        self, session: aiohttp.ClientSession, source: Dict[str, Any]
    ) -> Dict[str, Any]:
        app_id = base64.b64encode(b"us-monitor:monitor@local").decode("utf-8")
        url = "https://hapi.humdata.org/api/v2/coordination-context/conflict-events"
        params = {
            "output_format": "json",
            "limit": 500,
            "offset": 0,
            "app_identifier": app_id,
        }
        ok, status, payload, error = await self._get_json(session, url, params=params)
        count = self._estimate_record_count(payload)
        return self._build_output(
            source=source,
            ok=ok,
            status=status,
            record_count=count,
            sample=self._build_sample(payload),
            error=error,
        )

    async def _fetch_worldbank(
        self, session: aiohttp.ClientSession, source: Dict[str, Any]
    ) -> Dict[str, Any]:
        current_year = datetime.utcnow().year
        url = "https://api.worldbank.org/v2/country/USA/indicator/NY.GDP.MKTP.CD"
        ok, status, payload, error = await self._get_json(
            session,
            url,
            params={
                "format": "json",
                "date": f"{current_year - 6}:{current_year}",
                "per_page": 30,
            },
        )

        count = 0
        sample = ""
        if ok and isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], list):
            count = len(payload[1])
            sample = self._build_sample(payload[1])
        elif ok:
            ok = False
            error = "invalid_payload"

        return self._build_output(
            source=source,
            ok=ok,
            status=status,
            record_count=count,
            sample=sample,
            error=error,
        )

    async def _fetch_yahoo_finance(
        self, session: aiohttp.ClientSession, source: Dict[str, Any]
    ) -> Dict[str, Any]:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC"
        ok, status, payload, error = await self._get_json(
            session,
            url,
            params={"range": "5d", "interval": "1d"},
        )
        count = 0
        sample = ""
        if ok and isinstance(payload, dict):
            result = payload.get("chart", {}).get("result", [])
            if result:
                ts = result[0].get("timestamp", [])
                count = len(ts) if isinstance(ts, list) else 0
                sample = "^GSPC"
            else:
                ok = False
                error = "invalid_payload"

        return self._build_output(
            source=source,
            ok=ok,
            status=status,
            record_count=count,
            sample=sample,
            error=error,
        )

    async def _fetch_etf_flows(
        self, session: aiohttp.ClientSession, source: Dict[str, Any]
    ) -> Dict[str, Any]:
        tickers = ["SPY", "QQQ", "IWM"]
        success = 0
        for ticker in tickers:
            ok, _, payload, _ = await self._get_json(
                session,
                f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
                params={"range": "5d", "interval": "1d"},
            )
            if not ok or not isinstance(payload, dict):
                continue
            result = payload.get("chart", {}).get("result", [])
            if isinstance(result, list) and result:
                success += 1

        return self._build_output(
            source=source,
            ok=success > 0,
            status=200 if success > 0 else None,
            record_count=success,
            sample="SPY/QQQ/IWM",
            error="" if success > 0 else "all_tickers_failed",
        )

    async def _fetch_macro_signals(
        self, session: aiohttp.ClientSession, source: Dict[str, Any]
    ) -> Dict[str, Any]:
        checks = [
            ("https://api.alternative.me/fng/", {"limit": 10, "format": "json"}),
            ("https://mempool.space/api/v1/mining/hashrate/1m", None),
            (
                "https://query1.finance.yahoo.com/v8/finance/chart/QQQ",
                {"range": "3mo", "interval": "1d"},
            ),
        ]

        success = 0
        for url, params in checks:
            ok, _, _, _ = await self._get_json(session, url, params=params)
            if ok:
                success += 1

        return self._build_output(
            source=source,
            ok=success > 0,
            status=200 if success > 0 else None,
            record_count=success,
            sample="macro_bundle",
            error="" if success > 0 else "all_macro_checks_failed",
        )

    async def _fetch_faa_status(
        self, session: aiohttp.ClientSession, source: Dict[str, Any]
    ) -> Dict[str, Any]:
        ok, status, payload, error = await self._get_json(
            session,
            "https://nasstatus.faa.gov/api/airport-status-information",
        )
        count = self._estimate_record_count(payload)
        return self._build_output(
            source=source,
            ok=ok,
            status=status,
            record_count=count,
            sample=self._build_sample(payload),
            error=error,
        )

    async def _fetch_nga_warnings(
        self, session: aiohttp.ClientSession, source: Dict[str, Any]
    ) -> Dict[str, Any]:
        ok, status, payload, error = await self._get_json(
            session,
            "https://msi.nga.mil/api/publications/broadcast-warn",
            params={"output": "json", "status": "A"},
        )
        count = self._estimate_record_count(payload)
        return self._build_output(
            source=source,
            ok=ok,
            status=status,
            record_count=count,
            sample=self._build_sample(payload),
            error=error,
        )

    async def _fetch_service_status(
        self, session: aiohttp.ClientSession, source: Dict[str, Any]
    ) -> Dict[str, Any]:
        status_urls = [
            "https://www.githubstatus.com/api/v2/status.json",
            "https://www.cloudflarestatus.com/api/v2/status.json",
            "https://discordstatus.com/api/v2/status.json",
        ]
        success = 0
        for url in status_urls:
            ok, _, payload, _ = await self._get_json(session, url)
            if ok and isinstance(payload, dict):
                success += 1

        return self._build_output(
            source=source,
            ok=success > 0,
            status=200 if success > 0 else None,
            record_count=success,
            sample="status_bundle",
            error="" if success > 0 else "all_status_sources_failed",
        )

    async def _fetch_climate_anomalies(
        self, session: aiohttp.ClientSession, source: Dict[str, Any]
    ) -> Dict[str, Any]:
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=14)
        params = {
            "latitude": 24.0,
            "longitude": 120.0,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "daily": "temperature_2m_mean,precipitation_sum",
            "timezone": "UTC",
        }
        ok, status, payload, error = await self._get_json(
            session,
            "https://archive-api.open-meteo.com/v1/archive",
            params=params,
        )
        count = 0
        if ok and isinstance(payload, dict):
            daily = payload.get("daily", {})
            temps = daily.get("temperature_2m_mean", [])
            if isinstance(temps, list):
                count = len(temps)
            else:
                ok = False
                error = "invalid_payload"

        return self._build_output(
            source=source,
            ok=ok,
            status=status,
            record_count=count,
            sample="taiwan_strait",
            error=error,
        )

    async def _fetch_coingecko(
        self, session: aiohttp.ClientSession, source: Dict[str, Any]
    ) -> Dict[str, Any]:
        params = {
            "ids": "bitcoin,ethereum,tether",
            "vs_currencies": "usd",
            "include_24hr_change": "true",
        }
        ok, status, payload, error = await self._get_json(
            session,
            "https://api.coingecko.com/api/v3/simple/price",
            params=params,
        )
        count = len(payload) if ok and isinstance(payload, dict) else 0
        return self._build_output(
            source=source,
            ok=ok,
            status=status,
            record_count=count,
            sample=self._build_sample(payload),
            error=error,
        )

    async def _fetch_stablecoin_markets(
        self, session: aiohttp.ClientSession, source: Dict[str, Any]
    ) -> Dict[str, Any]:
        params = {
            "vs_currency": "usd",
            "ids": "tether,usd-coin,dai",
            "order": "market_cap_desc",
            "sparkline": "false",
            "price_change_percentage": "7d",
        }
        ok, status, payload, error = await self._get_json(
            session,
            "https://api.coingecko.com/api/v3/coins/markets",
            params=params,
        )
        count = len(payload) if ok and isinstance(payload, list) else 0
        return self._build_output(
            source=source,
            ok=ok,
            status=status,
            record_count=count,
            sample=self._build_sample(payload),
            error=error,
        )

    async def _fetch_tech_events(
        self, session: aiohttp.ClientSession, source: Dict[str, Any]
    ) -> Dict[str, Any]:
        rss_ok, rss_status, rss_text, rss_error = await self._get_text(
            session,
            "https://dev.events/rss.xml",
        )
        ics_ok, ics_status, ics_text, ics_error = await self._get_text(
            session,
            "https://www.techmeme.com/newsy_events.ics",
        )
        rss_count = len(re.findall(r"<item\b", rss_text, flags=re.IGNORECASE)) if rss_ok else 0
        ics_count = len(re.findall(r"BEGIN:VEVENT", ics_text)) if ics_ok else 0
        ok = rss_ok or ics_ok
        status = rss_status if rss_ok else ics_status
        error = ""
        if not ok:
            error = ";".join([x for x in [rss_error, ics_error] if x])[:160]

        return self._build_output(
            source=source,
            ok=ok,
            status=status,
            record_count=rss_count + ics_count,
            sample="dev.events/techmeme",
            error=error,
        )

    async def _fetch_pizzint_batch(
        self, session: aiohttp.ClientSession, source: Dict[str, Any]
    ) -> Dict[str, Any]:
        params = {
            "pairs": "usa_russia,russia_ukraine,usa_china,china_taiwan",
            "method": "gpr",
        }
        ok, status, payload, error = await self._get_json(
            session,
            "https://www.pizzint.watch/api/gdelt/batch",
            params=params,
            headers={"Accept": "application/json", "User-Agent": "US-Monitor/1.0"},
        )
        count = self._estimate_record_count(payload)
        return self._build_output(
            source=source,
            ok=ok,
            status=status,
            record_count=count,
            sample=self._build_sample(payload),
            error=error,
        )

    async def _fetch_not_supported(self, source: Dict[str, Any]) -> Dict[str, Any]:
        note = INDEPENDENT_SIGNAL_NOTES.get(str(source.get("key", "")), "not_supported")
        return self._build_output(
            source=source,
            ok=False,
            status=None,
            record_count=0,
            sample="",
            error=note,
        )

    async def _fetch_source(
        self,
        source: Dict[str, Any],
        session: aiohttp.ClientSession,
    ) -> Dict[str, Any]:
        key = str(source.get("key", ""))
        if key not in INDEPENDENT_SUPPORTED_KEYS:
            return await self._fetch_not_supported(source)

        handlers = {
            "wm_gdelt_doc": self._fetch_gdelt_doc,
            "wm_gdelt_geo": self._fetch_gdelt_geo,
            "wm_earthquakes": self._fetch_earthquakes,
            "wm_ucdp_events": self._fetch_ucdp_events,
            "wm_ucdp": self._fetch_ucdp,
            "wm_unhcr_population": self._fetch_unhcr_population,
            "wm_hapi": self._fetch_hapi,
            "wm_worldbank": self._fetch_worldbank,
            "wm_yahoo_finance": self._fetch_yahoo_finance,
            "wm_etf_flows": self._fetch_etf_flows,
            "wm_macro_signals": self._fetch_macro_signals,
            "wm_faa_status": self._fetch_faa_status,
            "wm_nga_warnings": self._fetch_nga_warnings,
            "wm_service_status": self._fetch_service_status,
            "wm_climate_anomalies": self._fetch_climate_anomalies,
            "wm_coingecko": self._fetch_coingecko,
            "wm_stablecoin_markets": self._fetch_stablecoin_markets,
            "wm_tech_events": self._fetch_tech_events,
            "wm_pizzint_gdelt_batch": self._fetch_pizzint_batch,
        }

        handler = handlers.get(key)
        if handler is None:
            return await self._fetch_not_supported(source)

        try:
            return await handler(session, source)
        except Exception as e:
            return self._build_output(
                source=source,
                ok=False,
                status=None,
                record_count=0,
                sample="",
                error=str(e)[:160],
            )

    async def fetch_sources(
        self,
        sources: Sequence[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        results: Dict[str, Dict[str, Any]] = {}
        if not sources:
            return results

        semaphore = asyncio.Semaphore(self.max_concurrency)

        async with aiohttp.ClientSession() as session:

            async def _job(source: Dict[str, Any]) -> None:
                endpoint = str(source.get("endpoint", "")).strip()
                if not endpoint:
                    return
                async with semaphore:
                    results[endpoint] = await self._fetch_source(source, session)

            await asyncio.gather(*[_job(source) for source in sources])

        return results


def get_independent_signal_catalog() -> List[Dict[str, Any]]:
    """返回独立信号源目录（含分层与备注）。"""

    catalog = []
    tier_order = {"priority": 1, "second": 2, "defer": 3}
    for item in get_worldmonitor_no_auth_sources():
        key = str(item.get("key", ""))
        tier = INDEPENDENT_SIGNAL_TIERS.get(key, "defer")
        note = INDEPENDENT_SIGNAL_NOTES.get(key, "")
        entry = dict(item)
        entry["tier"] = tier
        entry["independent_supported"] = key in INDEPENDENT_SUPPORTED_KEYS
        entry["independent_note"] = note
        entry["enabled_by_default"] = tier in INDEPENDENT_SIGNAL_CONFIG.get("enabled_tiers", [])
        catalog.append(entry)

    catalog.sort(
        key=lambda row: (
            tier_order.get(str(row.get("tier", "defer")), 99),
            int(row.get("priority", 9)),
            str(row.get("key", "")),
        )
    )
    return catalog


def get_enabled_independent_sources(
    enabled_tiers: Optional[Sequence[str]] = None,
    enabled_keys: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """根据分层与白名单返回启用的数据源。"""

    tiers = set(enabled_tiers or INDEPENDENT_SIGNAL_CONFIG.get("enabled_tiers", []))
    key_set = set(enabled_keys or [])
    use_key_filter = len(key_set) > 0

    enabled: List[Dict[str, Any]] = []
    for item in get_independent_signal_catalog():
        key = str(item.get("key", ""))
        tier = str(item.get("tier", "defer"))
        if tier not in tiers:
            continue
        if use_key_filter and key not in key_set:
            continue
        enabled.append(item)

    return enabled


async def fetch_independent_signal_data(
    enabled_tiers: Optional[Sequence[str]] = None,
    enabled_keys: Optional[Sequence[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """抓取独立信号源数据。"""

    if not INDEPENDENT_SIGNAL_CONFIG.get("enabled", True):
        return {}

    sources = get_enabled_independent_sources(
        enabled_tiers=enabled_tiers,
        enabled_keys=enabled_keys,
    )
    client = IndependentSignalClient(
        timeout_seconds=int(INDEPENDENT_SIGNAL_CONFIG.get("request_timeout_seconds", 12)),
        max_concurrency=int(INDEPENDENT_SIGNAL_CONFIG.get("max_concurrency", 6)),
    )
    return await client.fetch_sources(sources)
