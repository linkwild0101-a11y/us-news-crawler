#!/usr/bin/env python3
"""
爬虫测试脚本 - 限制处理数量
"""

import asyncio
import aiohttp
import feedparser
import os
from datetime import datetime
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://lwigqxyfxevldfjdeokp.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
WORKER_URL = os.getenv(
    "WORKER_URL", "https://content-extractor.linkwild0101.workers.dev"
)


class TestCrawler:
    def __init__(self, limit=5):
        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.limit = limit
        self.session = None
        self.stats = {"processed": 0, "articles": 0, "errors": 0}

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def test_crawl(self):
        print("🚀 开始测试爬取...")
        print(f"📊 限制处理: {self.limit} 个源\n")

        # 获取RSS源
        sources = (
            self.supabase.table("rss_sources")
            .select("*")
            .eq("status", "active")
            .limit(self.limit)
            .execute()
            .data
        )
        print(f"✅ 获取到 {len(sources)} 个源\n")

        for source in sources:
            print(f"📰 处理: {source['name']} ({source['category']})")
            try:
                # 抓取RSS
                async with self.session.get(
                    source["rss_url"],
                    headers={"User-Agent": "Mozilla/5.0 (compatible; TestCrawler/1.0)"},
                ) as resp:
                    if resp.status != 200:
                        print(f"   ⚠️  HTTP {resp.status}")
                        continue

                    content = await resp.text()
                    feed = feedparser.parse(content)

                    if not feed.entries:
                        print(f"   ℹ️  无文章")
                        continue

                    entry = feed.entries[0]  # 只测试第一条
                    print(
                        f"   ✅ 获取RSS成功，文章: {entry.get('title', 'N/A')[:50]}..."
                    )

                    # 测试内容提取
                    url = entry.get("link", "")
                    if url:
                        extracted = await self.extract_content(
                            url, source.get("anti_scraping", "None")
                        )
                        if extracted:
                            print(
                                f"   ✅ 内容提取成功 ({extracted.get('extraction_method', 'local')})"
                            )
                            print(
                                f"   📝 标题: {extracted.get('title', 'N/A')[:40]}..."
                            )
                            self.stats["articles"] += 1
                        else:
                            print(f"   ⚠️  内容提取失败")

                    self.stats["processed"] += 1

            except Exception as e:
                print(f"   ❌ 错误: {str(e)[:60]}")
                self.stats["errors"] += 1

            print()

        print("=" * 60)
        print("📊 测试统计")
        print("=" * 60)
        print(f"处理的源: {self.stats['processed']}")
        print(f"成功提取: {self.stats['articles']}")
        print(f"错误数: {self.stats['errors']}")
        print(f"\n✅ 测试完成！")

    async def extract_content(self, url, anti_scraping):
        try:
            # 尝试本地提取
            async with self.session.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
            ) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    # 简单提取标题
                    import re

                    title_match = re.search(r"<title[^>]*>([^<]*)</title>", html, re.I)
                    title = title_match.group(1).strip() if title_match else ""
                    return {"title": title, "extraction_method": "local"}
        except Exception as e:
            print(f"   ⚠️  本地提取失败: {str(e)[:40]}")

        return None


async def main():
    async with TestCrawler(limit=5) as crawler:
        await crawler.test_crawl()


if __name__ == "__main__":
    import sys

    # 设置环境变量
    if not os.getenv("SUPABASE_KEY"):
        os.environ["SUPABASE_KEY"] = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx3aWdxeHlmeGV2bGRmamRlb2twIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTE3MzYxMiwiZXhwIjoyMDg2NzQ5NjEyfQ.-JCEODgYe83EugQeTxLHsxBXikXbz_btei9-qsUxb1M"
        )

    asyncio.run(main())
