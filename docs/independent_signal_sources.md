# 独立信号源清单

- 生成时间: 2026-02-20 00:09:30
- 默认启用层级: priority, second
- 总数: 24

## 优先接入 (12)

| key | endpoint | signal_focus | 备注 |
| --- | --- | --- | --- |
| wm_earthquakes | /api/earthquakes | natural_disaster_signal |  |
| wm_gdelt_doc | /api/gdelt-doc | geopolitical_intensity |  |
| wm_gdelt_geo | /api/gdelt-geo | geopolitical_intensity |  |
| wm_hapi | /api/hapi | humanitarian_pressure |  |
| wm_ucdp | /api/ucdp | geopolitical_intensity |  |
| wm_ucdp_events | /api/ucdp-events | geopolitical_intensity | 上游偶发限流，建议轮询间隔>=5分钟。 |
| wm_unhcr_population | /api/unhcr-population | humanitarian_pressure | 上游分页接口，建议控制抓取频率。 |
| wm_climate_anomalies | /api/climate-anomalies | climate_risk | 依赖 open-meteo 历史数据，适合低频更新。 |
| wm_faa_status | /api/faa-status | infrastructure_disruption |  |
| wm_nga_warnings | /api/nga-warnings | maritime_risk |  |
| wm_service_status | /api/service-status | infrastructure_disruption | 多上游聚合，建议允许部分失败。 |
| wm_worldbank | /api/worldbank | economic_indicator_alert |  |

## 第二批接入 (7)

| key | endpoint | signal_focus | 备注 |
| --- | --- | --- | --- |
| wm_etf_flows | /api/etf-flows | market_volatility |  |
| wm_macro_signals | /api/macro-signals | economic_indicator_alert |  |
| wm_yahoo_finance | /api/yahoo-finance | market_volatility |  |
| wm_coingecko | /api/coingecko | crypto_risk |  |
| wm_pizzint_gdelt_batch | /api/pizzint/gdelt/batch | geopolitical_intensity |  |
| wm_stablecoin_markets | /api/stablecoin-markets | crypto_risk |  |
| wm_tech_events | /api/tech-events | innovation_cycle |  |

## 延后接入 (5)

| key | endpoint | signal_focus | 备注 |
| --- | --- | --- | --- |
| wm_worldpop_exposure | /api/worldpop-exposure | humanitarian_pressure | 估算模型接口，建议作为补充解释而非主触发。 |
| wm_data_military_hex_db | /api/data/military-hex-db | military_posture | 静态知识底座数据，非实时信号端点。 |
| wm_polymarket | /api/polymarket | market_expectation | 服务端访问可能被 Cloudflare 拦截，默认延后接入。 |
| wm_og_story | /api/og-story | content_enrichment | 内容增强用途，不直接产生信号。 |
| wm_rss_proxy | /api/rss-proxy | ingestion_support | 原设计依赖 worldmonitor 域名白名单代理，默认延后。 |
