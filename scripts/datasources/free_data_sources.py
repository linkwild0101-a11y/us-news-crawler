#!/usr/bin/env python3
"""
免费数据源客户端
FRED, GDELT, USGS, World Bank
"""

import asyncio
import aiohttp
import os
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from config.independent_signal_config import INDEPENDENT_SIGNAL_CONFIG
from config.watchlist_config import WATCHLIST_SENTINELS
from scripts.datasources.independent_signal_sources import fetch_independent_signal_data
from scripts.datasources.signal_endpoint_sources import get_worldmonitor_no_auth_sources


DEFAULT_WORLDMONITOR_ENDPOINTS = (
    "/api/earthquakes",
    "/api/ucdp-events",
    "/api/ucdp",
    "/api/unhcr-population",
    "/api/hapi",
    "/api/macro-signals",
    "/api/yahoo-finance",
    "/api/etf-flows",
    "/api/worldbank",
    "/api/faa-status",
    "/api/service-status",
    "/api/climate-anomalies",
    "/api/nga-warnings",
)


class FREDClient:
    """FRED (Federal Reserve Economic Data) 客户端"""

    BASE_URL = "https://api.stlouisfed.org/fred"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def get_series(self, series_id: str, limit: int = 10) -> List[Dict]:
        """
        获取经济指标数据

        Args:
            series_id: 指标ID (如 'FEDFUNDS', 'CPIAUCSL')
            limit: 返回数据点数

        Returns:
            数据点列表
        """
        url = f"{self.BASE_URL}/series/observations"
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "limit": limit,
            "sort_order": "desc",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("observations", [])
                else:
                    return []

    async def get_latest_value(self, series_id: str) -> Optional[Dict]:
        """获取最新值"""
        data = await self.get_series(series_id, limit=1)
        return data[0] if data else None


class GDELTClient:
    """GDELT (Global Database of Events, Language, and Tone) 客户端"""

    BASE_URL = "https://api.gdeltproject.org/api/v2"

    async def query_events(
        self, query: str, days: int = 7, mode: str = "ArtList"
    ) -> List[Dict]:
        """
        查询全球事件

        Args:
            query: 查询关键词
            days: 查询天数
            mode: 查询模式 (ArtList/ ToneChart/ etc.)

        Returns:
            事件列表
        """
        url = f"{self.BASE_URL}/doc/doc"

        # 计算时间范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        params = {
            "query": query,
            "mode": mode,
            "startdatetime": start_date.strftime("%Y%m%d%H%M%S"),
            "enddatetime": end_date.strftime("%Y%m%d%H%M%S"),
            "format": "json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    try:
                        data = await resp.json()
                        return data.get("articles", [])
                    except:
                        return []
                else:
                    return []


class USGSClient:
    """USGS (U.S. Geological Survey) 地震数据客户端"""

    BASE_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary"

    async def get_recent_earthquakes(
        self, min_magnitude: float = 4.5, days: int = 1
    ) -> List[Dict]:
        """
        获取最近地震数据

        Args:
            min_magnitude: 最小震级
            days: 查询天数

        Returns:
            地震列表
        """
        # 根据震级选择端点
        if min_magnitude >= 4.5:
            endpoint = "4.5_day.geojson"
        elif min_magnitude >= 2.5:
            endpoint = "2.5_day.geojson"
        else:
            endpoint = "1.0_day.geojson"

        url = f"{self.BASE_URL}/{endpoint}"

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    features = data.get("features", [])

                    # 格式化数据
                    earthquakes = []
                    for feature in features:
                        props = feature.get("properties", {})
                        coords = feature.get("geometry", {}).get("coordinates", [])

                        earthquakes.append(
                            {
                                "magnitude": props.get("mag"),
                                "place": props.get("place"),
                                "time": props.get("time"),
                                "latitude": coords[1] if len(coords) > 1 else None,
                                "longitude": coords[0] if len(coords) > 0 else None,
                                "depth": coords[2] if len(coords) > 2 else None,
                                "url": props.get("url"),
                            }
                        )

                    return earthquakes
                else:
                    return []


class WorldBankClient:
    """世界银行数据客户端"""

    BASE_URL = "https://api.worldbank.org/v2"

    async def get_indicator(
        self, indicator: str, country: str = "USA", limit: int = 10
    ) -> List[Dict]:
        """
        获取国家指标数据

        Args:
            indicator: 指标代码 (如 'NY.GDP.MKTP.CD' GDP)
            country: 国家代码
            limit: 返回年数

        Returns:
            年度数据列表
        """
        url = f"{self.BASE_URL}/country/{country}/indicator/{indicator}"
        params = {
            "format": "json",
            "date": f"{datetime.now().year - limit}:{datetime.now().year}",
            "per_page": limit,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    try:
                        data = await resp.json()
                        # 返回第二个元素（第一个是分页信息）
                        return data[1] if len(data) > 1 else []
                    except Exception:
                        return []
                else:
                    return []


class WorldMonitorClient:
    """worldmonitor 无鉴权信号端点客户端"""

    def __init__(self, base_url: str):
        self.base_url = (base_url or "").rstrip("/")
        self.request_timeout = aiohttp.ClientTimeout(total=12)

    @staticmethod
    def _estimate_record_count(payload: object) -> int:
        """估算返回结果中的记录条数。"""
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
        ):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
            if isinstance(value, dict):
                return len(value)

        return len(payload)

    @staticmethod
    def _build_sample(payload: object) -> str:
        """提取简要样本，便于日志和信号描述。"""
        if isinstance(payload, list) and payload:
            first = payload[0]
        elif isinstance(payload, dict):
            if isinstance(payload.get("data"), list) and payload["data"]:
                first = payload["data"][0]
            elif isinstance(payload.get("events"), list) and payload["events"]:
                first = payload["events"][0]
            elif isinstance(payload.get("articles"), list) and payload["articles"]:
                first = payload["articles"][0]
            elif isinstance(payload.get("features"), list) and payload["features"]:
                first = payload["features"][0]
            else:
                first = payload
        else:
            return ""

        if isinstance(first, dict):
            for key in ("title", "name", "event_name", "place", "country", "symbol"):
                value = first.get(key)
                if value:
                    return str(value)[:80]
            return str(first)[:80]
        return str(first)[:80]

    async def _fetch_endpoint(
        self, endpoint: str, session: aiohttp.ClientSession
    ) -> Dict[str, object]:
        """请求单个 worldmonitor 端点。"""
        url = f"{self.base_url}{endpoint}"
        now_iso = datetime.now().isoformat()
        output: Dict[str, object] = {
            "endpoint": endpoint,
            "ok": False,
            "status": None,
            "record_count": 0,
            "sample": "",
            "fetched_at": now_iso,
            "error": "",
        }

        try:
            async with session.get(url, timeout=self.request_timeout) as resp:
                output["status"] = resp.status
                if resp.status != 200:
                    output["error"] = f"HTTP {resp.status}"
                    return output

                content_type = resp.headers.get("Content-Type", "")
                if "application/json" in content_type.lower():
                    payload = await resp.json()
                else:
                    text = await resp.text()
                    output["error"] = f"non_json:{text[:80]}"
                    return output

                output["ok"] = True
                output["record_count"] = self._estimate_record_count(payload)
                output["sample"] = self._build_sample(payload)
                return output
        except Exception as e:
            output["error"] = str(e)[:120]
            return output

    async def fetch_no_auth_endpoints(
        self,
        max_priority: int = 2,
        enabled_endpoints: Optional[List[str]] = None,
    ) -> Dict[str, Dict]:
        """抓取 worldmonitor 无鉴权优先端点。"""
        catalog = get_worldmonitor_no_auth_sources()
        enabled_set = set(enabled_endpoints or DEFAULT_WORLDMONITOR_ENDPOINTS)
        endpoints = []
        for item in catalog:
            if int(item.get("priority", 9)) <= max_priority:
                endpoint = str(item.get("endpoint", "")).strip()
                if endpoint and endpoint in enabled_set:
                    endpoints.append(endpoint)

        results: Dict[str, Dict] = {}
        if not endpoints:
            return results

        semaphore = asyncio.Semaphore(6)
        async with aiohttp.ClientSession() as session:
            async def _job(endpoint: str) -> None:
                async with semaphore:
                    results[endpoint] = await self._fetch_endpoint(endpoint, session)

            await asyncio.gather(*[_job(endpoint) for endpoint in endpoints])

        return results


def _build_watchlist_gdelt_queries() -> Dict[str, str]:
    """根据哨兵配置生成 GDELT 查询模板。"""
    queries: Dict[str, str] = {}
    for sentinel in WATCHLIST_SENTINELS:
        sentinel_id = str(sentinel.get("id", "")).strip()
        if not sentinel_id:
            continue

        keyword_groups = sentinel.get("keyword_groups", {})
        collected: List[str] = []
        if isinstance(keyword_groups, dict):
            for keywords in keyword_groups.values():
                if not isinstance(keywords, list):
                    continue
                for keyword in keywords:
                    token = str(keyword or "").strip()
                    if not token:
                        continue
                    if token in collected:
                        continue
                    collected.append(token)
                    if len(collected) >= 8:
                        break
                if len(collected) >= 8:
                    break

        if not collected:
            collected = ["taiwan", "military", "export control"]

        queries[sentinel_id] = " OR ".join(collected)

    return queries


async def _fetch_watchlist_gdelt_templates(gdelt: GDELTClient) -> Dict[str, Dict]:
    """按哨兵模板抓取 GDELT 事件数据。"""
    results: Dict[str, Dict] = {}
    query_map = _build_watchlist_gdelt_queries()

    async def _job(sentinel_id: str, query: str) -> None:
        try:
            events = await gdelt.query_events(query, days=2)
            sample_title = ""
            if events and isinstance(events[0], dict):
                sample_title = str(events[0].get("title", ""))[:120]
            results[sentinel_id] = {
                "query": query,
                "event_count": len(events),
                "sample_title": sample_title,
            }
        except Exception as e:
            results[sentinel_id] = {
                "query": query,
                "event_count": 0,
                "sample_title": "",
                "error": str(e)[:120],
            }

    await asyncio.gather(
        *[
            _job(sentinel_id, query)
            for sentinel_id, query in query_map.items()
        ]
    )
    return results


# 便捷函数
async def fetch_all_data_sources(fred_api_key: Optional[str] = None) -> Dict:
    """
    获取所有数据源的最新数据

    Returns:
        包含所有数据源数据的字典
    """
    results = {
        "timestamp": datetime.now().isoformat(),
        "fred": {},
        "gdelt": [],
        "watchlist_gdelt": {},
        "usgs": [],
        "worldbank": {},
        "independent_signals": {},
        "worldmonitor": {},
    }

    # FRED (需要API key)
    if fred_api_key:
        fred = FREDClient(fred_api_key)
        try:
            results["fred"]["fed_funds_rate"] = await fred.get_latest_value("FEDFUNDS")
            results["fred"]["cpi"] = await fred.get_latest_value("CPIAUCSL")
            results["fred"]["unemployment"] = await fred.get_latest_value("UNRATE")
        except Exception as e:
            print(f"FRED数据获取失败: {e}")

    # GDELT
    gdelt = GDELTClient()
    try:
        results["gdelt"] = await gdelt.query_events("conflict OR protest", days=1)
        results["watchlist_gdelt"] = await _fetch_watchlist_gdelt_templates(gdelt)
    except Exception as e:
        print(f"GDELT数据获取失败: {e}")

    # USGS
    usgs = USGSClient()
    try:
        results["usgs"] = await usgs.get_recent_earthquakes(min_magnitude=4.5)
    except Exception as e:
        print(f"USGS数据获取失败: {e}")

    # World Bank
    wb = WorldBankClient()
    try:
        results["worldbank"]["gdp"] = await wb.get_indicator("NY.GDP.MKTP.CD", limit=1)
    except Exception as e:
        print(f"World Bank数据获取失败: {e}")

    # 独立信号源（默认启用 priority + second）
    independent_defaults = INDEPENDENT_SIGNAL_CONFIG
    enable_independent = (
        os.getenv(
            "ENABLE_INDEPENDENT_SIGNAL_SOURCES",
            str(independent_defaults.get("enabled", True)).lower(),
        ).lower()
        == "true"
    )
    enabled_tiers_env = os.getenv("INDEPENDENT_SIGNAL_TIERS", "").strip()
    enabled_keys_env = os.getenv("INDEPENDENT_SIGNAL_KEYS", "").strip()
    enabled_tiers = (
        [part.strip() for part in enabled_tiers_env.split(",") if part.strip()]
        if enabled_tiers_env
        else list(independent_defaults.get("enabled_tiers", ["priority", "second"]))
    )
    enabled_keys = (
        [part.strip() for part in enabled_keys_env.split(",") if part.strip()]
        if enabled_keys_env
        else None
    )

    if enable_independent:
        try:
            independent_rows = await fetch_independent_signal_data(
                enabled_tiers=enabled_tiers,
                enabled_keys=enabled_keys,
            )
            results["independent_signals"] = independent_rows
            # 保持历史兼容，旧逻辑仍读取 worldmonitor 键。
            results["worldmonitor"] = independent_rows
        except Exception as e:
            print(f"独立信号源获取失败: {e}")

    return results


# 测试
if __name__ == "__main__":
    import asyncio

    async def test():
        print("测试免费数据源...")

        # USGS (不需要API key)
        print("\n1. 测试USGS地震数据:")
        usgs = USGSClient()
        quakes = await usgs.get_recent_earthquakes()
        print(f"   获取到 {len(quakes)} 条地震记录")
        if quakes:
            print(f"   最新: {quakes[0]['place']} - 震级 {quakes[0]['magnitude']}")

        # GDELT (不需要API key)
        print("\n2. 测试GDELT事件数据:")
        gdelt = GDELTClient()
        events = await gdelt.query_events("protest", days=1)
        print(f"   获取到 {len(events)} 条事件记录")

        # World Bank (不需要API key)
        print("\n3. 测试World Bank数据:")
        wb = WorldBankClient()
        gdp = await wb.get_indicator("NY.GDP.MKTP.CD", limit=1)
        print(f"   获取到 {len(gdp)} 条GDP记录")
        if gdp:
            print(f"   最新: {gdp[0].get('value')} ({gdp[0].get('date')})")

        print("\n测试完成!")

    asyncio.run(test())
