#!/usr/bin/env python3
"""
免费数据源客户端
FRED, GDELT, USGS, World Bank
"""

import aiohttp
import json
from typing import List, Dict, Optional
from datetime import datetime, timedelta


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
                    except:
                        return []
                else:
                    return []


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
        "usgs": [],
        "worldbank": {},
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
