#!/usr/bin/env python3
"""
增强分析器
集成免费数据源的增强信号检测
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.analyzer import HotspotAnalyzer
from scripts.datasources.free_data_sources import fetch_all_data_sources


class EnhancedAnalyzer(HotspotAnalyzer):
    """增强版分析器，集成外部数据源"""

    def __init__(self):
        super().__init__()
        self.fred_api_key = os.getenv("FRED_API_KEY")

    async def fetch_external_data(self) -> dict:
        """获取外部数据源"""
        print("🌐 获取外部数据源...")
        return await fetch_all_data_sources(self.fred_api_key)

    async def detect_enhanced_signals(self, clusters, external_data):
        """
        使用外部数据增强信号检测

        Args:
            clusters: 聚类列表
            external_data: 外部数据源数据

        Returns:
            增强信号列表
        """
        enhanced_signals = []

        # 1. 经济指标异常检测
        fred_data = external_data.get("fred", {})
        for cluster in clusters:
            title_lower = cluster.get("primary_title", "").lower()

            # 检测 Fed/利率相关新闻
            if any(
                kw in title_lower for kw in ["fed", "interest rate", "federal reserve"]
            ):
                fed_rate = fred_data.get("fed_funds_rate", {})
                if fed_rate:
                    enhanced_signals.append(
                        {
                            "signal_type": "economic_indicator_alert",
                            "name": "经济指标异常 - 利率变动",
                            "confidence": 0.85,
                            "description": f"检测到Fed相关新闻，当前联邦基金利率: {fed_rate.get('value', 'N/A')}",
                            "cluster_id": cluster["cluster_id"],
                            "data_source": "FRED",
                        }
                    )

            # 检测通胀相关新闻
            if any(kw in title_lower for kw in ["inflation", "cpi", "consumer price"]):
                cpi = fred_data.get("cpi", {})
                if cpi:
                    enhanced_signals.append(
                        {
                            "signal_type": "economic_indicator_alert",
                            "name": "经济指标异常 - CPI变动",
                            "confidence": 0.85,
                            "description": f"检测到通胀相关新闻，当前CPI: {cpi.get('value', 'N/A')}",
                            "cluster_id": cluster["cluster_id"],
                            "data_source": "FRED",
                        }
                    )

        # 2. 自然灾害信号
        usgs_data = external_data.get("usgs", [])
        for cluster in clusters:
            title_lower = cluster.get("primary_title", "").lower()

            if any(kw in title_lower for kw in ["earthquake", "disaster", "tsunami"]):
                if usgs_data:
                    latest = usgs_data[0]
                    enhanced_signals.append(
                        {
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
                    )

        # 3. 地缘政治强度
        gdelt_data = external_data.get("gdelt", [])
        if len(gdelt_data) > 10:  # 如果GDELT事件多，说明地缘政治活跃
            for cluster in clusters:
                if cluster.get("category") == "politics":
                    enhanced_signals.append(
                        {
                            "signal_type": "geopolitical_intensity",
                            "name": "地缘政治紧张",
                            "confidence": min(0.9, 0.5 + len(gdelt_data) * 0.01),
                            "description": f"过去24小时检测到 {len(gdelt_data)} 起全球冲突/抗议事件",
                            "cluster_id": cluster["cluster_id"],
                            "data_source": "GDELT",
                        }
                    )

        return enhanced_signals

    async def run_enhanced_analysis(self, limit=None, dry_run=False):
        """
        运行增强版分析

        Args:
            limit: 最大处理文章数
            dry_run: 试运行模式
        """
        print("=" * 60)
        print("开始增强版热点分析")
        print("=" * 60)

        # 1. 获取外部数据
        external_data = await self.fetch_external_data()

        # 2. 运行基础分析
        await self.run_analysis(limit=limit, dry_run=True)  # 先试运行获取聚类

        # 3. 获取聚类
        articles = self.load_unanalyzed_articles(limit)
        if not articles:
            print("没有未分析的文章")
            return

        from scripts.clustering import cluster_news

        clusters = cluster_news(articles)

        # 4. 检测增强信号
        print("🔍 检测增强信号...")
        enhanced_signals = await self.detect_enhanced_signals(clusters, external_data)

        if enhanced_signals:
            print(f"检测到 {len(enhanced_signals)} 个增强信号:")
            for s in enhanced_signals:
                print(f"  📊 {s['name']}: {s['description'][:60]}...")

        # 5. 如果不是试运行，保存结果
        if not dry_run:
            print("💾 保存分析结果...")
            # 保存增强信号到数据库（可以创建新表或添加到现有信号表）

        print("=" * 60)
        print("增强分析完成!")
        print("=" * 60)


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
