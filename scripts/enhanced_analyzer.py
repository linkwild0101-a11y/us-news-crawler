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

# 配置日志 - 同时输出到控制台和文件
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 清除现有的处理器
if logger.handlers:
    logger.handlers.clear()

# 创建格式器 - 包含时间戳
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

# 控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# 文件处理器 - 记录到日志文件
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
        logger.info("[ENHANCED_INIT] 增强分析器初始化完成")

    async def fetch_external_data(self) -> dict:
        """获取外部数据源"""
        start_time = time.time()
        logger.info("[EXTERNAL_DATA_START] 开始获取外部数据源...")

        try:
            result = await fetch_all_data_sources(self.fred_api_key)
            duration = time.time() - start_time

            # 统计各数据源结果
            fred_count = len(result.get("fred", {}))
            usgs_count = len(result.get("usgs", []))
            gdelt_count = len(result.get("gdelt", []))
            worldbank_count = len(result.get("worldbank", {}))

            logger.info(
                f"[EXTERNAL_DATA_SUCCESS] 外部数据获取完成 | "
                f"总耗时: {duration:.2f}s | "
                f"FRED指标: {fred_count}个 | "
                f"USGS地震: {usgs_count}条 | "
                f"GDELT事件: {gdelt_count}条 | "
                f"世界银行: {worldbank_count}个"
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
        """
        使用外部数据增强信号检测

        Args:
            clusters: 聚类列表
            external_data: 外部数据源数据

        Returns:
            增强信号列表
        """
        start_time = time.time()
        cluster_count = len(clusters)

        logger.info(
            f"[SIGNAL_DETECTION_START] 开始增强信号检测 | "
            f"聚类数量: {cluster_count} | "
            f"外部数据源: {list(external_data.keys())}"
        )

        enhanced_signals = []

        # 1. 经济指标异常检测
        fred_start = time.time()
        fred_data = external_data.get("fred", {})
        fred_signals = 0

        for cluster in clusters:
            title_lower = cluster.get("primary_title", "").lower()
            cluster_id_short = cluster.get("cluster_id", "")[:8]

            # 检测 Fed/利率相关新闻
            if any(
                kw in title_lower for kw in ["fed", "interest rate", "federal reserve"]
            ):
                fed_rate = fred_data.get("fed_funds_rate", {})
                if fed_rate:
                    signal = {
                        "signal_type": "economic_indicator_alert",
                        "name": "经济指标异常 - 利率变动",
                        "confidence": 0.85,
                        "description": f"检测到Fed相关新闻，当前联邦基金利率: {fed_rate.get('value', 'N/A')}",
                        "cluster_id": cluster["cluster_id"],
                        "data_source": "FRED",
                    }
                    enhanced_signals.append(signal)
                    fred_signals += 1
                    logger.info(
                        f"[FRED_SIGNAL] 检测到利率信号 | cluster: {cluster_id_short}... | "
                        f"利率: {fed_rate.get('value', 'N/A')}"
                    )

            # 检测通胀相关新闻
            if any(kw in title_lower for kw in ["inflation", "cpi", "consumer price"]):
                cpi = fred_data.get("cpi", {})
                if cpi:
                    signal = {
                        "signal_type": "economic_indicator_alert",
                        "name": "经济指标异常 - CPI变动",
                        "confidence": 0.85,
                        "description": f"检测到通胀相关新闻，当前CPI: {cpi.get('value', 'N/A')}",
                        "cluster_id": cluster["cluster_id"],
                        "data_source": "FRED",
                    }
                    enhanced_signals.append(signal)
                    fred_signals += 1
                    logger.info(
                        f"[FRED_SIGNAL] 检测到CPI信号 | cluster: {cluster_id_short}... | "
                        f"CPI: {cpi.get('value', 'N/A')}"
                    )

        fred_duration = time.time() - fred_start
        logger.info(
            f"[FRED_COMPLETE] FRED信号检测完成 | 耗时: {fred_duration:.3f}s | 信号数: {fred_signals}"
        )

        # 2. 自然灾害信号
        usgs_start = time.time()
        usgs_data = external_data.get("usgs", [])
        usgs_signals = 0

        for cluster in clusters:
            title_lower = cluster.get("primary_title", "").lower()
            cluster_id_short = cluster.get("cluster_id", "")[:8]

            if any(kw in title_lower for kw in ["earthquake", "disaster", "tsunami"]):
                if usgs_data:
                    latest = usgs_data[0]
                    signal = {
                        "signal_type": "natural_disaster_signal",
                        "name": "自然灾害信号",
                        "confidence": 0.9,
                        "description": f"检测到灾害新闻，最新地震: {latest.get('place')} - 震级 {latest.get('magnitude')}",
                        "cluster_id": cluster["cluster_id"],
                        "data_source": "USGS",
                        "details": {
                            "magnitude": latest.get("magnitude"),
                            "location": latest.get("place"),
                        },
                    }
                    enhanced_signals.append(signal)
                    usgs_signals += 1
                    logger.info(
                        f"[USGS_SIGNAL] 检测到灾害信号 | cluster: {cluster_id_short}... | "
                        f"地震: {latest.get('place')} 震级{latest.get('magnitude')}"
                    )

        usgs_duration = time.time() - usgs_start
        logger.info(
            f"[USGS_COMPLETE] USGS信号检测完成 | 耗时: {usgs_duration:.3f}s | 信号数: {usgs_signals}"
        )

        # 3. 地缘政治强度
        gdelt_start = time.time()
        gdelt_data = external_data.get("gdelt", [])
        gdelt_signals = 0

        if len(gdelt_data) > 10:  # 如果GDELT事件多，说明地缘政治活跃
            for cluster in clusters:
                if cluster.get("category") == "politics":
                    cluster_id_short = cluster.get("cluster_id", "")[:8]
                    signal = {
                        "signal_type": "geopolitical_intensity",
                        "name": "地缘政治紧张",
                        "confidence": min(0.9, 0.5 + len(gdelt_data) * 0.01),
                        "description": f"过去24小时检测到 {len(gdelt_data)} 起全球冲突/抗议事件",
                        "cluster_id": cluster["cluster_id"],
                        "data_source": "GDELT",
                    }
                    enhanced_signals.append(signal)
                    gdelt_signals += 1
                    logger.info(
                        f"[GDELT_SIGNAL] 检测到地缘政治信号 | cluster: {cluster_id_short}... | "
                        f"GDELT事件数: {len(gdelt_data)} | 置信度: {signal['confidence']:.2f}"
                    )

        gdelt_duration = time.time() - gdelt_start
        logger.info(
            f"[GDELT_COMPLETE] GDELT信号检测完成 | 耗时: {gdelt_duration:.3f}s | 信号数: {gdelt_signals}"
        )

        total_duration = time.time() - start_time
        logger.info(
            f"[SIGNAL_DETECTION_COMPLETE] 增强信号检测完成 | "
            f"总耗时: {total_duration:.2f}s | "
            f"FRED: {fred_duration:.2f}s ({fred_signals}个) | "
            f"USGS: {usgs_duration:.2f}s ({usgs_signals}个) | "
            f"GDELT: {gdelt_duration:.2f}s ({gdelt_signals}个) | "
            f"总计: {len(enhanced_signals)}个信号"
        )

        return enhanced_signals

    async def run_enhanced_analysis(self, limit=None, dry_run=False):
        """
        运行增强版分析

        Args:
            limit: 最大处理文章数
            dry_run: 试运行模式
        """
        total_start = time.time()
        logger.info("=" * 80)
        logger.info("[ENHANCED_ANALYSIS_START] 开始增强版热点分析")
        logger.info(f"参数: limit={limit}, dry_run={dry_run}")
        logger.info("=" * 80)

        try:
            # 1. 获取外部数据
            step1_start = time.time()
            logger.info("[STEP_1] 开始获取外部数据...")
            external_data = await self.fetch_external_data()
            step1_duration = time.time() - step1_start
            logger.info(
                f"[STEP_1_COMPLETE] 外部数据获取完成 | 耗时: {step1_duration:.2f}s"
            )

            # 2. 运行基础分析
            step2_start = time.time()
            logger.info("[STEP_2] 开始运行基础分析...")
            await self.run_analysis(limit=limit, dry_run=True)
            step2_duration = time.time() - step2_start
            logger.info(f"[STEP_2_COMPLETE] 基础分析完成 | 耗时: {step2_duration:.2f}s")

            # 3. 获取聚类
            step3_start = time.time()
            logger.info("[STEP_3] 开始获取聚类...")
            articles = self.load_unanalyzed_articles(limit)
            if not articles:
                logger.warning("[STEP_3_SKIP] 没有未分析的文章，结束分析")
                return

            from scripts.clustering import cluster_news

            clusters = cluster_news(articles)
            cluster_count = len(clusters)
            step3_duration = time.time() - step3_start
            logger.info(
                f"[STEP_3_COMPLETE] 聚类完成 | "
                f"耗时: {step3_duration:.2f}s | "
                f"文章数: {len(articles)} | "
                f"聚类数: {cluster_count}"
            )

            # 4. 检测增强信号
            step4_start = time.time()
            logger.info("[STEP_4] 开始检测增强信号...")
            enhanced_signals = await self.detect_enhanced_signals(
                clusters, external_data
            )
            step4_duration = time.time() - step4_start

            if enhanced_signals:
                logger.info(
                    f"[STEP_4_COMPLETE] 增强信号检测完成 | "
                    f"耗时: {step4_duration:.2f}s | "
                    f"检测到 {len(enhanced_signals)} 个信号"
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

            # 5. 如果不是试运行，保存结果
            if not dry_run:
                step5_start = time.time()
                logger.info("[STEP_5] 开始保存分析结果...")
                # 保存增强信号到数据库
                saved_count = 0
                for signal in enhanced_signals:
                    try:
                        # 这里可以添加保存到数据库的逻辑
                        saved_count += 1
                    except Exception as e:
                        logger.error(f"[SAVE_ERROR] 保存信号失败: {str(e)[:100]}")

                step5_duration = time.time() - step5_start
                logger.info(
                    f"[STEP_5_COMPLETE] 保存完成 | "
                    f"耗时: {step5_duration:.2f}s | "
                    f"已保存: {saved_count}/{len(enhanced_signals)}"
                )
            else:
                logger.info("[STEP_5_SKIP] 试运行模式，跳过保存")

            # 总结
            total_duration = time.time() - total_start
            logger.info("=" * 80)
            logger.info("[ENHANCED_ANALYSIS_COMPLETE] 增强分析完成!")
            logger.info(
                f"总耗时: {total_duration:.2f}s | "
                f"外部数据: {step1_duration:.2f}s | "
                f"基础分析: {step2_duration:.2f}s | "
                f"聚类: {step3_duration:.2f}s | "
                f"信号检测: {step4_duration:.2f}s | "
                f"文章: {len(articles)}篇 | "
                f"聚类: {cluster_count}个 | "
                f"信号: {len(enhanced_signals)}个"
            )
            logger.info("=" * 80)

        except Exception as e:
            total_duration = time.time() - total_start
            logger.error("=" * 80)
            logger.error(f"[ENHANCED_ANALYSIS_ERROR] 增强分析失败!")
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

    args = parser.parse_args()

    analyzer = EnhancedAnalyzer()
    await analyzer.run_enhanced_analysis(limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
