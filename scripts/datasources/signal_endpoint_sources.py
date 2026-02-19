#!/usr/bin/env python3
"""Signal endpoint catalog for enhanced analysis and worldmonitor candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class SignalEndpointSource:
    """信号端点定义。"""

    key: str
    provider: str
    endpoint: str
    source_kind: str
    auth_required: bool
    env_keys: Tuple[str, ...]
    priority: int
    signal_focus: str
    signal_meaning: str
    signal_role: str


# 现有增强分析已接入端点（生产在用）
# - 说明: 这些端点已经在 free_data_sources.py 里有请求逻辑。
ENHANCED_ANALYZER_SIGNAL_ENDPOINTS: Tuple[SignalEndpointSource, ...] = (
    SignalEndpointSource(
        key="fred_core_indicators",
        provider="FRED",
        endpoint="https://api.stlouisfed.org/fred/series/observations",
        source_kind="external_api",
        auth_required=True,
        env_keys=("FRED_API_KEY",),
        priority=1,
        signal_focus="economic_indicator_alert",
        signal_meaning="利率/CPI/失业率变化，反映宏观经济冷热与政策方向。",
        signal_role="给经济类聚类提供硬指标锚点，降低纯新闻叙事偏差。",
    ),
    SignalEndpointSource(
        key="gdelt_doc_events",
        provider="GDELT",
        endpoint="https://api.gdeltproject.org/api/v2/doc/doc",
        source_kind="external_api",
        auth_required=False,
        env_keys=(),
        priority=1,
        signal_focus="geopolitical_intensity",
        signal_meaning="冲突/抗议事件密度变化，反映地缘风险强弱。",
        signal_role="与政治类聚类交叉验证，提升地缘信号置信度。",
    ),
    SignalEndpointSource(
        key="usgs_earthquake_feed",
        provider="USGS",
        endpoint="https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson",
        source_kind="external_api",
        auth_required=False,
        env_keys=(),
        priority=1,
        signal_focus="natural_disaster_signal",
        signal_meaning="中强震及地理位置变化，反映自然灾害风险。",
        signal_role="和灾害相关新闻聚类对齐，筛出高影响事件。",
    ),
    SignalEndpointSource(
        key="worldbank_macro",
        provider="WorldBank",
        endpoint="https://api.worldbank.org/v2/country/USA/indicator/NY.GDP.MKTP.CD",
        source_kind="external_api",
        auth_required=False,
        env_keys=(),
        priority=2,
        signal_focus="economic_indicator_alert",
        signal_meaning="长期宏观指标（GDP）变化，反映结构性经济状态。",
        signal_role="作为慢变量背景，校准短期经济新闻噪声。",
    ),
)


# worldmonitor 抽取的无鉴权优先端点（候选，默认按 no-auth 优先接入）
# - 说明: 当前系统尚未全部接入执行，仅统一收口在目录中。
WORLDMONITOR_NO_AUTH_SIGNAL_ENDPOINTS: Tuple[SignalEndpointSource, ...] = (
    SignalEndpointSource(
        key="wm_gdelt_doc",
        provider="worldmonitor",
        endpoint="/api/gdelt-doc",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=1,
        signal_focus="geopolitical_intensity",
        signal_meaning="媒体事件层冲突/抗议热度。",
        signal_role="补充地缘冲突事件覆盖，支持跨区域对比。",
    ),
    SignalEndpointSource(
        key="wm_gdelt_geo",
        provider="worldmonitor",
        endpoint="/api/gdelt-geo",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=1,
        signal_focus="geopolitical_intensity",
        signal_meaning="地理网格维度的事件聚集强度。",
        signal_role="定位热点区域，辅助聚类定位与升级。",
    ),
    SignalEndpointSource(
        key="wm_earthquakes",
        provider="worldmonitor",
        endpoint="/api/earthquakes",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=1,
        signal_focus="natural_disaster_signal",
        signal_meaning="地震活动变化。",
        signal_role="作为灾害触发器，提升自然灾害信号实时性。",
    ),
    SignalEndpointSource(
        key="wm_ucdp_events",
        provider="worldmonitor",
        endpoint="/api/ucdp-events",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=1,
        signal_focus="geopolitical_intensity",
        signal_meaning="武装冲突事件与伤亡相关结构化记录。",
        signal_role="补足 GDELT 的事件口径，提升冲突识别鲁棒性。",
    ),
    SignalEndpointSource(
        key="wm_ucdp",
        provider="worldmonitor",
        endpoint="/api/ucdp",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=1,
        signal_focus="geopolitical_intensity",
        signal_meaning="冲突数据库历史与分层信息。",
        signal_role="支持冲突背景解释与趋势判定。",
    ),
    SignalEndpointSource(
        key="wm_unhcr_population",
        provider="worldmonitor",
        endpoint="/api/unhcr-population",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=1,
        signal_focus="humanitarian_pressure",
        signal_meaning="难民/流离失所人群变化。",
        signal_role="用于人道风险和区域稳定性预警。",
    ),
    SignalEndpointSource(
        key="wm_hapi",
        provider="worldmonitor",
        endpoint="/api/hapi",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=1,
        signal_focus="humanitarian_pressure",
        signal_meaning="人道主义事件与需求指标。",
        signal_role="作为灾害/冲突后续影响佐证。",
    ),
    SignalEndpointSource(
        key="wm_worldbank",
        provider="worldmonitor",
        endpoint="/api/worldbank",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=2,
        signal_focus="economic_indicator_alert",
        signal_meaning="宏观发展指标变化。",
        signal_role="补充经济慢变量，做宏观背景校准。",
    ),
    SignalEndpointSource(
        key="wm_yahoo_finance",
        provider="worldmonitor",
        endpoint="/api/yahoo-finance",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=2,
        signal_focus="market_volatility",
        signal_meaning="股指与关键资产价格波动。",
        signal_role="增强市场异常检测与情绪映射。",
    ),
    SignalEndpointSource(
        key="wm_etf_flows",
        provider="worldmonitor",
        endpoint="/api/etf-flows",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=2,
        signal_focus="market_volatility",
        signal_meaning="ETF 资金流向变化。",
        signal_role="识别风险偏好切换与板块轮动。",
    ),
    SignalEndpointSource(
        key="wm_macro_signals",
        provider="worldmonitor",
        endpoint="/api/macro-signals",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=2,
        signal_focus="economic_indicator_alert",
        signal_meaning="跨资产宏观综合指标。",
        signal_role="形成多维经济压力面板，辅助信号归因。",
    ),
    SignalEndpointSource(
        key="wm_faa_status",
        provider="worldmonitor",
        endpoint="/api/faa-status",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=2,
        signal_focus="infrastructure_disruption",
        signal_meaning="美国航管系统状态变化。",
        signal_role="检测航空基础设施异常，补充突发事件信号。",
    ),
    SignalEndpointSource(
        key="wm_nga_warnings",
        provider="worldmonitor",
        endpoint="/api/nga-warnings",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=2,
        signal_focus="maritime_risk",
        signal_meaning="海事航行警告与地理风险。",
        signal_role="补充海上冲突与供应链风险监测。",
    ),
    SignalEndpointSource(
        key="wm_service_status",
        provider="worldmonitor",
        endpoint="/api/service-status",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=2,
        signal_focus="infrastructure_disruption",
        signal_meaning="主要云/平台服务可用性波动。",
        signal_role="识别大规模服务中断，辅助科技/经济信号。",
    ),
    SignalEndpointSource(
        key="wm_climate_anomalies",
        provider="worldmonitor",
        endpoint="/api/climate-anomalies",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=2,
        signal_focus="climate_risk",
        signal_meaning="气候异常指标变化。",
        signal_role="补充极端天气相关风险背景。",
    ),
    SignalEndpointSource(
        key="wm_worldpop_exposure",
        provider="worldmonitor",
        endpoint="/api/worldpop-exposure",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=2,
        signal_focus="humanitarian_pressure",
        signal_meaning="人口暴露度变化。",
        signal_role="评估灾害/冲突潜在影响范围。",
    ),
    SignalEndpointSource(
        key="wm_coingecko",
        provider="worldmonitor",
        endpoint="/api/coingecko",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=3,
        signal_focus="crypto_risk",
        signal_meaning="加密资产市场波动。",
        signal_role="补充风险偏好与资金避险线索。",
    ),
    SignalEndpointSource(
        key="wm_stablecoin_markets",
        provider="worldmonitor",
        endpoint="/api/stablecoin-markets",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=3,
        signal_focus="crypto_risk",
        signal_meaning="稳定币规模与流动性变化。",
        signal_role="识别链上流动性压力与传导风险。",
    ),
    SignalEndpointSource(
        key="wm_polymarket",
        provider="worldmonitor",
        endpoint="/api/polymarket",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=3,
        signal_focus="market_expectation",
        signal_meaning="事件概率的市场化预期。",
        signal_role="作为新闻叙事的预期侧对照。",
    ),
    SignalEndpointSource(
        key="wm_tech_events",
        provider="worldmonitor",
        endpoint="/api/tech-events",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=3,
        signal_focus="innovation_cycle",
        signal_meaning="科技会议与发布事件密度。",
        signal_role="辅助 tech 热点形成背景判断。",
    ),
    SignalEndpointSource(
        key="wm_data_military_hex_db",
        provider="worldmonitor",
        endpoint="/api/data/military-hex-db",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=3,
        signal_focus="military_posture",
        signal_meaning="军事部署相关静态数据库。",
        signal_role="作为态势说明素材，非高频触发源。",
    ),
    SignalEndpointSource(
        key="wm_pizzint_gdelt_batch",
        provider="worldmonitor",
        endpoint="/api/pizzint/gdelt/batch",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=3,
        signal_focus="geopolitical_intensity",
        signal_meaning="聚合后的批量 GDELT 视图。",
        signal_role="用于快速拉取区域风险快照。",
    ),
    SignalEndpointSource(
        key="wm_og_story",
        provider="worldmonitor",
        endpoint="/api/og-story",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=4,
        signal_focus="content_enrichment",
        signal_meaning="网页 OG 元信息抓取。",
        signal_role="用于描述补全，不直接作为信号触发。",
    ),
    SignalEndpointSource(
        key="wm_rss_proxy",
        provider="worldmonitor",
        endpoint="/api/rss-proxy",
        source_kind="worldmonitor_api",
        auth_required=False,
        env_keys=(),
        priority=4,
        signal_focus="ingestion_support",
        signal_meaning="RSS 代理通道。",
        signal_role="用于采集连通性兜底，不直接生成信号。",
    ),
)


def get_signal_endpoint_catalog(include_auth: bool = True) -> List[Dict[str, object]]:
    """返回统一端点目录（无鉴权优先排序）。"""

    items = list(ENHANCED_ANALYZER_SIGNAL_ENDPOINTS) + list(
        WORLDMONITOR_NO_AUTH_SIGNAL_ENDPOINTS
    )
    if not include_auth:
        items = [item for item in items if not item.auth_required]

    items.sort(key=lambda item: (item.auth_required, item.priority, item.provider, item.key))
    return [asdict(item) for item in items]


def get_enhanced_analyzer_sources() -> List[Dict[str, object]]:
    """返回当前增强分析已使用的数据源目录。"""

    return [asdict(item) for item in ENHANCED_ANALYZER_SIGNAL_ENDPOINTS]


def get_worldmonitor_no_auth_sources() -> List[Dict[str, object]]:
    """返回 worldmonitor 无鉴权优先候选端点。"""

    items = sorted(
        WORLDMONITOR_NO_AUTH_SIGNAL_ENDPOINTS,
        key=lambda item: (item.priority, item.key),
    )
    return [asdict(item) for item in items]
