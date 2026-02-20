#!/usr/bin/env python3
"""独立信号源配置。"""

from typing import Dict, List

INDEPENDENT_SIGNAL_CONFIG = {
    "enabled": True,
    "request_timeout_seconds": 12,
    "max_concurrency": 6,
    "enabled_tiers": ["priority", "second"],
}

INDEPENDENT_SIGNAL_TIERS: Dict[str, str] = {
    "wm_gdelt_doc": "priority",
    "wm_gdelt_geo": "priority",
    "wm_earthquakes": "priority",
    "wm_ucdp_events": "priority",
    "wm_ucdp": "priority",
    "wm_unhcr_population": "priority",
    "wm_hapi": "priority",
    "wm_worldbank": "priority",
    "wm_faa_status": "priority",
    "wm_nga_warnings": "priority",
    "wm_service_status": "priority",
    "wm_climate_anomalies": "priority",
    "wm_yahoo_finance": "second",
    "wm_etf_flows": "second",
    "wm_macro_signals": "second",
    "wm_coingecko": "second",
    "wm_stablecoin_markets": "second",
    "wm_tech_events": "second",
    "wm_pizzint_gdelt_batch": "second",
    "wm_worldpop_exposure": "defer",
    "wm_polymarket": "defer",
    "wm_data_military_hex_db": "defer",
    "wm_og_story": "defer",
    "wm_rss_proxy": "defer",
}

INDEPENDENT_SIGNAL_NOTES: Dict[str, str] = {
    "wm_ucdp_events": "上游偶发限流，建议轮询间隔>=5分钟。",
    "wm_unhcr_population": "上游分页接口，建议控制抓取频率。",
    "wm_climate_anomalies": "依赖 open-meteo 历史数据，适合低频更新。",
    "wm_service_status": "多上游聚合，建议允许部分失败。",
    "wm_polymarket": "服务端访问可能被 Cloudflare 拦截，默认延后接入。",
    "wm_rss_proxy": "原设计依赖 worldmonitor 域名白名单代理，默认延后。",
    "wm_og_story": "内容增强用途，不直接产生信号。",
    "wm_data_military_hex_db": "静态知识底座数据，非实时信号端点。",
    "wm_worldpop_exposure": "估算模型接口，建议作为补充解释而非主触发。",
}

INDEPENDENT_SUPPORTED_KEYS: List[str] = [
    "wm_gdelt_doc",
    "wm_gdelt_geo",
    "wm_earthquakes",
    "wm_ucdp_events",
    "wm_ucdp",
    "wm_unhcr_population",
    "wm_hapi",
    "wm_worldbank",
    "wm_yahoo_finance",
    "wm_etf_flows",
    "wm_macro_signals",
    "wm_faa_status",
    "wm_nga_warnings",
    "wm_service_status",
    "wm_climate_anomalies",
    "wm_coingecko",
    "wm_stablecoin_markets",
    "wm_tech_events",
    "wm_pizzint_gdelt_batch",
]
