#!/usr/bin/env python3
"""
增强分析器
集成免费数据源的增强信号检测
"""

import asyncio
import sys
import os
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.analyzer import HotspotAnalyzer
from scripts.datasources.free_data_sources import fetch_all_data_sources
from scripts.datasources.signal_endpoint_sources import (
    get_enhanced_analyzer_sources,
    get_worldmonitor_no_auth_sources,
)
from scripts.signal_detector import generate_dedupe_key
from config.analysis_config import SIGNAL_COOLDOWN_HOURS

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if logger.handlers:
    logger.handlers.clear()

formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

log_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(log_dir, "..", "logs", "enhanced_analyzer.log")
os.makedirs(os.path.dirname(log_file), exist_ok=True)

file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


class EnhancedAnalyzer(HotspotAnalyzer):
    """增强版分析器，集成外部数据源"""

    def __init__(self):
        super().__init__()
        self.fred_api_key = os.getenv("FRED_API_KEY")
        self.enhanced_signal_sources = get_enhanced_analyzer_sources()
        self.no_auth_candidate_sources = get_worldmonitor_no_auth_sources()
        logger.info("[ENHANCED_INIT] 增强分析器初始化完成")
        logger.info(
            f"[SIGNAL_ENDPOINTS] 在用端点: {len(self.enhanced_signal_sources)} | "
            f"无鉴权候选: {len(self.no_auth_candidate_sources)}"
        )

    async def fetch_external_data(self) -> dict:
        """获取外部数据源"""
        start_time = time.time()
        logger.info("[EXTERNAL_DATA_START] 开始获取外部数据源...")

        try:
            result = await fetch_all_data_sources(self.fred_api_key)
            duration = time.time() - start_time

            fred_count = len(result.get("fred", {}))
            usgs_count = len(result.get("usgs", []))
            gdelt_count = len(result.get("gdelt", []))
            worldbank_count = len(result.get("worldbank", {}))
            worldmonitor_rows = result.get("worldmonitor", {})
            worldmonitor_ok = len(
                [row for row in worldmonitor_rows.values() if row.get("ok")]
            )

            logger.info(
                f"[EXTERNAL_DATA_SUCCESS] 外部数据获取完成 | "
                f"总耗时: {duration:.2f}s | "
                f"FRED指标: {fred_count}个 | "
                f"USGS地震: {usgs_count}条 | "
                f"GDELT事件: {gdelt_count}条 | "
                f"世界银行: {worldbank_count}个 | "
                f"worldmonitor: {worldmonitor_ok}/{len(worldmonitor_rows)}"
            )
            return result
        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"[EXTERNAL_DATA_ERROR] 外部数据获取失败 | "
                f"耗时: {duration:.2f}s | 错误: {str(e)}"
            )
            return {}

    async def detect_enhanced_signals(self, clusters, external_data):
        """使用外部数据增强信号检测"""
        start_time = time.time()
        cluster_count = len(clusters)

        logger.info(
            f"[SIGNAL_DETECTION_START] 开始增强信号检测 | "
            f"聚类数量: {cluster_count} | "
            f"外部数据源: {list(external_data.keys())}"
        )

        enhanced_signals = []
        now = datetime.now()
        expires_at = (now + timedelta(hours=SIGNAL_COOLDOWN_HOURS)).isoformat()
        created_at = now.isoformat()

        hour_bucket = int(now.timestamp() // 3600)
        max_affected_clusters = 20

        def _collect_clusters(keywords: List[str]) -> List[Dict[str, Any]]:
            matched = []
            for cluster in clusters:
                title_lower = cluster.get("primary_title", "").lower()
                if any(keyword in title_lower for keyword in keywords):
                    matched.append(cluster)
            return matched

        def _build_aggregated_signal(
            *,
            signal_type: str,
            subtype: str,
            name: str,
            description: str,
            related_clusters: List[Dict[str, Any]],
            data_source: str,
            details: Dict[str, Any],
            confidence: float,
            category: str = "unknown",
        ) -> Dict[str, Any]:
            unique_ids = list(
                dict.fromkeys(
                    [
                        cluster.get("cluster_id", "")
                        for cluster in related_clusters
                        if cluster.get("cluster_id")
                    ]
                )
            )[:max_affected_clusters]
            top_titles = [
                cluster.get("primary_title", "")[:80]
                for cluster in related_clusters[:3]
                if cluster.get("primary_title")
            ]
            merged_details = dict(details)
            merged_details.update(
                {
                    "cluster_count": len(unique_ids),
                    "top_titles": top_titles,
                    "hour_bucket": hour_bucket,
                    "subtype": subtype,
                }
            )

            return {
                "signal_id": generate_dedupe_key(signal_type, subtype, hour_bucket),
                "signal_type": signal_type,
                "name": name,
                "confidence": confidence,
                "description": description,
                "cluster_id": unique_ids[0] if unique_ids else None,
                "affected_clusters": unique_ids,
                "category": category,
                "details": merged_details,
                "data_source": data_source,
                "expires_at": expires_at,
                "created_at": created_at,
            }

        fred_start = time.time()
        fred_data = external_data.get("fred", {})
        fred_signals = 0

        fed_rate = fred_data.get("fed_funds_rate", {})
        fed_clusters = _collect_clusters(["fed", "interest rate", "federal reserve"])
        if fed_rate and fed_clusters:
            fed_ids = list(
                dict.fromkeys(
                    [c.get("cluster_id") for c in fed_clusters if c.get("cluster_id")]
                )
            )
            confidence = min(0.92, 0.72 + 0.03 * min(len(fed_ids), 6))
            top_titles = "；".join(
                [c.get("primary_title", "")[:36] for c in fed_clusters[:3]]
            )
            signal = _build_aggregated_signal(
                signal_type="economic_indicator_alert",
                subtype="fed_funds_rate",
                name="经济指标异常 - 利率变动",
                description=(
                    f"联邦基金利率当前值 {fed_rate.get('value', 'N/A')}，"
                    f"关联 {len(fed_ids)} 个聚类。重点: {top_titles}"
                ),
                related_clusters=fed_clusters,
                data_source="FRED",
                details={"indicator": "fed_funds_rate", "value": fed_rate.get("value")},
                confidence=confidence,
                category="economy",
            )
            enhanced_signals.append(signal)
            fred_signals += 1

        cpi = fred_data.get("cpi", {})
        cpi_clusters = _collect_clusters(["inflation", "cpi", "consumer price"])
        if cpi and cpi_clusters:
            cpi_ids = list(
                dict.fromkeys(
                    [c.get("cluster_id") for c in cpi_clusters if c.get("cluster_id")]
                )
            )
            confidence = min(0.92, 0.72 + 0.03 * min(len(cpi_ids), 6))
            top_titles = "；".join(
                [c.get("primary_title", "")[:36] for c in cpi_clusters[:3]]
            )
            signal = _build_aggregated_signal(
                signal_type="economic_indicator_alert",
                subtype="cpi",
                name="经济指标异常 - CPI变动",
                description=(
                    f"CPI当前值 {cpi.get('value', 'N/A')}，关联 {len(cpi_ids)} 个聚类。"
                    f"重点: {top_titles}"
                ),
                related_clusters=cpi_clusters,
                data_source="FRED",
                details={"indicator": "cpi", "value": cpi.get("value")},
                confidence=confidence,
                category="economy",
            )
            enhanced_signals.append(signal)
            fred_signals += 1

        fred_duration = time.time() - fred_start
        logger.info(
            f"[FRED_COMPLETE] FRED信号检测完成 | 耗时: {fred_duration:.3f}s | 信号数: {fred_signals}"
        )

        usgs_start = time.time()
        usgs_data = external_data.get("usgs", [])
        usgs_signals = 0

        disaster_clusters = _collect_clusters(["earthquake", "disaster", "tsunami"])
        if usgs_data and disaster_clusters:
            latest = usgs_data[0]
            disaster_ids = list(
                dict.fromkeys(
                    [c.get("cluster_id") for c in disaster_clusters if c.get("cluster_id")]
                )
            )
            signal = _build_aggregated_signal(
                signal_type="natural_disaster_signal",
                subtype="usgs",
                name="自然灾害信号",
                description=(
                    f"最新地震: {latest.get('place')} (M{latest.get('magnitude')})，"
                    f"关联 {len(disaster_ids)} 个灾害相关聚类。"
                ),
                related_clusters=disaster_clusters,
                data_source="USGS",
                details={
                    "magnitude": latest.get("magnitude"),
                    "location": latest.get("place"),
                },
                confidence=min(0.93, 0.78 + 0.03 * min(len(disaster_ids), 5)),
                category=disaster_clusters[0].get("category", "unknown"),
            )
            enhanced_signals.append(signal)
            usgs_signals += 1

        usgs_duration = time.time() - usgs_start
        logger.info(
            f"[USGS_COMPLETE] USGS信号检测完成 | 耗时: {usgs_duration:.3f}s | 信号数: {usgs_signals}"
        )

        gdelt_start = time.time()
        gdelt_data = external_data.get("gdelt", [])
        gdelt_signals = 0

        geopolitical_clusters = [c for c in clusters if c.get("category") == "politics"]
        if len(gdelt_data) > 10 and geopolitical_clusters:
            geo_ids = list(
                dict.fromkeys(
                    [c.get("cluster_id") for c in geopolitical_clusters if c.get("cluster_id")]
                )
            )
            signal = _build_aggregated_signal(
                signal_type="geopolitical_intensity",
                subtype="gdelt",
                name="地缘政治紧张",
                description=(
                    f"过去24小时检测到 {len(gdelt_data)} 起全球冲突/抗议事件，"
                    f"关联 {len(geo_ids)} 个政治类聚类。"
                ),
                related_clusters=geopolitical_clusters,
                data_source="GDELT",
                details={"gdelt_event_count": len(gdelt_data)},
                confidence=min(0.9, 0.58 + len(gdelt_data) * 0.008),
                category="politics",
            )
            enhanced_signals.append(signal)
            gdelt_signals += 1

        gdelt_duration = time.time() - gdelt_start
        logger.info(
            f"[GDELT_COMPLETE] GDELT信号检测完成 | 耗时: {gdelt_duration:.3f}s | 信号数: {gdelt_signals}"
        )

        wm_start = time.time()
        worldmonitor_data = external_data.get("worldmonitor", {})
        wm_signals = 0

        def _wm_count(endpoint: str) -> int:
            row = worldmonitor_data.get(endpoint, {})
            if not row or not row.get("ok"):
                return 0
            return int(row.get("record_count") or 0)

        wm_ucdp_count = _wm_count("/api/ucdp-events")
        if wm_ucdp_count > 0 and geopolitical_clusters:
            geo_ids = list(
                dict.fromkeys(
                    [c.get("cluster_id") for c in geopolitical_clusters if c.get("cluster_id")]
                )
            )
            signal = _build_aggregated_signal(
                signal_type="geopolitical_intensity",
                subtype="worldmonitor_ucdp",
                name="地缘政治紧张 - 冲突库事件",
                description=(
                    f"worldmonitor/UCDP 返回 {wm_ucdp_count} 条冲突事件，"
                    f"关联 {len(geo_ids)} 个政治类聚类。"
                ),
                related_clusters=geopolitical_clusters,
                data_source="worldmonitor:ucdp-events",
                details={"ucdp_event_count": wm_ucdp_count},
                confidence=min(0.88, 0.58 + 0.02 * min(wm_ucdp_count, 12)),
                category="politics",
            )
            enhanced_signals.append(signal)
            wm_signals += 1

        wm_quake_count = _wm_count("/api/earthquakes")
        if wm_quake_count > 0 and disaster_clusters:
            signal = _build_aggregated_signal(
                signal_type="natural_disaster_signal",
                subtype="worldmonitor_earthquakes",
                name="自然灾害信号 - worldmonitor 地震",
                description=(
                    f"worldmonitor 地震端点返回 {wm_quake_count} 条事件，"
                    f"关联 {len(disaster_clusters)} 个灾害相关聚类。"
                ),
                related_clusters=disaster_clusters,
                data_source="worldmonitor:earthquakes",
                details={"worldmonitor_earthquake_count": wm_quake_count},
                confidence=min(0.9, 0.62 + 0.02 * min(wm_quake_count, 12)),
                category=disaster_clusters[0].get("category", "unknown"),
            )
            enhanced_signals.append(signal)
            wm_signals += 1

        wm_econ_count = sum(
            [
                _wm_count("/api/macro-signals"),
                _wm_count("/api/yahoo-finance"),
                _wm_count("/api/etf-flows"),
                _wm_count("/api/worldbank"),
            ]
        )
        economy_clusters = [c for c in clusters if c.get("category") in ("economy", "tech")]
        if wm_econ_count > 0 and economy_clusters:
            economy_ids = list(
                dict.fromkeys(
                    [c.get("cluster_id") for c in economy_clusters if c.get("cluster_id")]
                )
            )
            signal = _build_aggregated_signal(
                signal_type="economic_indicator_alert",
                subtype="worldmonitor_macro_mix",
                name="经济指标异常 - worldmonitor 市场面板",
                description=(
                    "worldmonitor 宏观/市场端点返回 "
                    f"{wm_econ_count} 条数据，关联 {len(economy_ids)} 个经济/科技聚类。"
                ),
                related_clusters=economy_clusters,
                data_source="worldmonitor:macro-mix",
                details={
                    "macro_signals": _wm_count("/api/macro-signals"),
                    "yahoo_finance": _wm_count("/api/yahoo-finance"),
                    "etf_flows": _wm_count("/api/etf-flows"),
                    "worldbank": _wm_count("/api/worldbank"),
                    "total": wm_econ_count,
                },
                confidence=min(0.89, 0.6 + 0.015 * min(wm_econ_count, 16)),
                category="economy",
            )
            enhanced_signals.append(signal)
            wm_signals += 1

        wm_duration = time.time() - wm_start
        logger.info(
            f"[WORLDMONITOR_COMPLETE] worldmonitor信号检测完成 | "
            f"耗时: {wm_duration:.3f}s | 信号数: {wm_signals}"
        )

        total_duration = time.time() - start_time
        logger.info(
            f"[SIGNAL_DETECTION_COMPLETE] 增强信号检测完成 | "
            f"总耗时: {total_duration:.2f}s | "
            f"FRED: {fred_duration:.2f}s ({fred_signals}个) | "
            f"USGS: {usgs_duration:.2f}s ({usgs_signals}个) | "
            f"GDELT: {gdelt_duration:.2f}s ({gdelt_signals}个) | "
            f"WORLDMONITOR: {wm_duration:.2f}s ({wm_signals}个) | "
            f"总计: {len(enhanced_signals)}个信号"
        )

        return enhanced_signals

    async def run_enhanced_analysis(
        self,
        limit: int = None,
        dry_run: bool = False,
        enrich_signals_after_run: bool = False,
        enrich_hours: int = 24,
        enrich_limit: int = 30,
        enrich_workers: int = 3,
    ):
        """运行增强版分析（全量完整分析并发）"""
        total_start = time.time()
        logger.info("=" * 80)
        logger.info("[ENHANCED_ANALYSIS_START] 开始增强版新闻分析")
        logger.info(
            f"参数: limit={limit}, dry_run={dry_run}, "
            f"enrich_signals_after_run={enrich_signals_after_run}, "
            f"enrich_hours={enrich_hours}, enrich_limit={enrich_limit}, "
            f"enrich_workers={enrich_workers}"
        )
        logger.info("=" * 80)

        try:
            step1_start = time.time()
            logger.info("[STEP_1] 开始获取外部数据...")
            external_data = await self.fetch_external_data()
            step1_duration = time.time() - step1_start
            logger.info(
                f"[STEP_1_COMPLETE] 外部数据获取完成 | 耗时: {step1_duration:.2f}s"
            )

            step2_start = time.time()
            logger.info("[STEP_2] 开始运行基础分析（全量完整分析并发）...")

            articles = self.load_unanalyzed_articles(
                limit=limit if limit else 500, hours=None
            )
            if not articles:
                logger.warning("[STEP_2_SKIP] 没有未分析的文章，结束分析")
                if enrich_signals_after_run and not dry_run:
                    logger.info("[SIGNAL_ENRICH] 开始补充待处理信号解释（无新文章场景）")
                    self.enrich_pending_signal_rationales(
                        hours=enrich_hours,
                        limit=enrich_limit,
                        max_workers=enrich_workers,
                    )
                return

            from scripts.clustering import cluster_news

            clusters = cluster_news(articles)
            self.stats["clusters_created"] = len(clusters)

            hot_clusters = [
                c for c in clusters if c.get("article_count", 0) >= self.hot_threshold
            ]

            logger.info(
                f"[FULL_ANALYSIS] 聚类统计: 总计 {len(clusters)} 个, 信号目标 {len(hot_clusters)} 个"
            )

            reused_clusters = self._reuse_existing_cluster_summaries(clusters)
            clusters_to_analyze = [c for c in clusters if not c.get("summary")]
            logger.info(
                f"[CACHE_REUSE] 复用 {reused_clusters} 个聚类摘要 | "
                f"待分析 {len(clusters_to_analyze)} 个"
            )

            if clusters_to_analyze:
                logger.info(
                    f"[CONCURRENT] 开始并发处理 {len(clusters_to_analyze)} 个聚类..."
                )
                self._process_clusters_concurrent(clusters_to_analyze, dry_run=dry_run)

            step2_duration = time.time() - step2_start
            logger.info(
                f"[STEP_2_COMPLETE] 基础分析完成 | "
                f"耗时: {step2_duration:.2f}s | "
                f"LLM调用: {self.stats['llm_calls']}次"
            )

            step3_start = time.time()
            logger.info("[STEP_3] 开始基础信号检测...")
            from scripts.signal_detector import detect_all_signals

            base_signals = detect_all_signals(hot_clusters)
            step3_duration = time.time() - step3_start
            logger.info(
                f"[STEP_3_COMPLETE] 基础信号检测完成 | "
                f"耗时: {step3_duration:.2f}s | 信号数: {len(base_signals)}"
            )

            step4_start = time.time()
            logger.info("[STEP_4] 开始检测增强信号...")
            enhanced_signals = await self.detect_enhanced_signals(
                clusters, external_data
            )
            step4_duration = time.time() - step4_start

            if enhanced_signals:
                logger.info(
                    f"[STEP_4_COMPLETE] 增强信号检测完成 | "
                    f"耗时: {step4_duration:.2f}s | 检测到 {len(enhanced_signals)} 个信号"
                )
                for i, s in enumerate(enhanced_signals[:5], 1):
                    logger.info(
                        f"  [SIGNAL_{i}] {s['name']} | "
                        f"类型: {s['signal_type']} | "
                        f"置信度: {s['confidence']:.2f} | "
                        f"数据源: {s['data_source']}"
                    )
            else:
                logger.info(
                    f"[STEP_4_COMPLETE] 未检测到增强信号 | 耗时: {step4_duration:.2f}s"
                )

            all_signals = base_signals + enhanced_signals

            if not dry_run:
                step5_start = time.time()
                logger.info("[STEP_5] 开始保存分析结果...")

                self.save_analysis_results(clusters, all_signals)

                article_ids = [a["id"] for a in articles]
                self.mark_articles_analyzed(article_ids)

                if enrich_signals_after_run:
                    logger.info("[SIGNAL_ENRICH] 开始补充待处理信号解释")
                    self.enrich_pending_signal_rationales(
                        hours=enrich_hours,
                        limit=enrich_limit,
                        max_workers=enrich_workers,
                    )

                step5_duration = time.time() - step5_start
                logger.info(f"[STEP_5_COMPLETE] 保存完成 | 耗时: {step5_duration:.2f}s")
            else:
                logger.info("[STEP_5_SKIP] 试运行模式，跳过保存")

            total_duration = time.time() - total_start
            logger.info("=" * 80)
            logger.info("[ENHANCED_ANALYSIS_COMPLETE] 增强分析完成!")
            logger.info(
                f"总耗时: {total_duration:.2f}s | "
                f"文章: {len(articles)}篇 | "
                f"聚类: {len(clusters)}个 | "
                f"信号: {len(all_signals)}个 | "
                f"LLM调用: {self.stats['llm_calls']}次"
            )
            logger.info("=" * 80)

        except Exception as e:
            total_duration = time.time() - total_start
            logger.error("=" * 80)
            logger.error("[ENHANCED_ANALYSIS_ERROR] 增强分析失败!")
            logger.error(f"总耗时: {total_duration:.2f}s")
            logger.error(f"错误: {str(e)}")
            logger.error("=" * 80)
            raise


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="US-Monitor 增强分析器")
    parser.add_argument("--limit", type=int, default=None, help="最大处理文章数")
    parser.add_argument("--dry-run", action="store_true", help="试运行模式")
    parser.add_argument(
        "--enrich-signals-after-run",
        action="store_true",
        help="分析完成后补充信号 LLM 解释",
    )
    parser.add_argument(
        "--enrich-hours",
        type=int,
        default=24,
        help="信号解释回看窗口（小时）",
    )
    parser.add_argument(
        "--enrich-limit",
        type=int,
        default=30,
        help="本轮最多补充解释的信号数",
    )
    parser.add_argument(
        "--enrich-workers",
        type=int,
        default=3,
        help="信号解释并发 worker 数",
    )

    args = parser.parse_args()

    analyzer = EnhancedAnalyzer()
    await analyzer.run_enhanced_analysis(
        limit=args.limit,
        dry_run=args.dry_run,
        enrich_signals_after_run=args.enrich_signals_after_run,
        enrich_hours=args.enrich_hours,
        enrich_limit=args.enrich_limit,
        enrich_workers=args.enrich_workers,
    )


if __name__ == "__main__":
    asyncio.run(main())
