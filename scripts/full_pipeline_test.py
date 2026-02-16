#!/usr/bin/env python3
"""
完整流程测试 - 基于验证可用的源
测试 RSS抓取 -> 内容提取 -> SimHash去重 -> 清洗 -> 入库 全流程
"""

import asyncio
import aiohttp
import feedparser
import os
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from supabase import create_client

# 配置
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://lwigqxyfxevldfjdeokp.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
WORKER_URL = os.getenv(
    "WORKER_URL", "https://content-extractor.linkwild0101.workers.dev"
)

# 测试配置
MAX_SOURCES = 20  # 测试20个源
MAX_ARTICLES_PER_SOURCE = 5  # 每个源最多处理5篇文章
CONCURRENT_LIMIT = 10  # 并发限制


class FullPipelineTest:
    def __init__(self):
        if not SUPABASE_KEY:
            raise ValueError("未设置 SUPABASE_KEY")

        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.session: Optional[aiohttp.ClientSession] = None
        self.stats = {
            "sources_total": 0,
            "sources_processed": 0,
            "sources_failed": 0,
            "articles_fetched": 0,
            "articles_extracted": 0,
            "articles_deduped": 0,
            "articles_saved": 0,
            "errors": [],
        }

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    def compute_simhash(self, text: str) -> str:
        """计算SimHash"""
        try:
            from simhash import Simhash

            if not text:
                return "0"
            return str(Simhash(text[:1000].lower()))
        except ImportError:
            # Fallback to MD5
            return hashlib.md5(text[:1000].encode()).hexdigest()[:16]

    def hamming_distance(self, hash1: str, hash2: str) -> int:
        """计算汉明距离"""
        try:
            h1 = int(hash1)
            h2 = int(hash2)
            x = h1 ^ h2
            distance = 0
            while x:
                distance += 1
                x &= x - 1
            return distance
        except:
            return 100

    async def check_duplicate(self, simhash: str, url: str) -> bool:
        """检查是否重复"""
        try:
            # 检查URL是否已存在
            result = (
                self.supabase.table("articles").select("id").eq("url", url).execute()
            )
            if result.data:
                return True

            # SimHash检查（最近7天）
            cutoff = (datetime.now() - timedelta(days=7)).isoformat()
            result = (
                self.supabase.table("articles")
                .select("id, simhash")
                .gte("fetched_at", cutoff)
                .execute()
            )

            for article in result.data:
                if article.get("simhash"):
                    if self.hamming_distance(simhash, article["simhash"]) <= 3:
                        return True

            return False
        except Exception as e:
            print(f"    ⚠️  去重检查失败: {e}")
            return False

    async def extract_content(self, url: str, anti_scraping: str) -> Optional[Dict]:
        """提取文章内容"""
        try:
            # 对于反爬站点，尝试使用Worker
            if anti_scraping in ["Cloudflare", "Paywall"] and WORKER_URL:
                try:
                    async with self.session.post(
                        f"{WORKER_URL}/extract",
                        json={"url": url},
                        headers={"Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=20),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("success"):
                                return {
                                    "title": data.get("title", ""),
                                    "content": data.get("content", ""),
                                    "excerpt": data.get("excerpt", ""),
                                    "author": data.get("author", ""),
                                    "published_time": data.get("published_time", ""),
                                    "extraction_method": "cloudflare",
                                }
                except Exception as e:
                    print(f"    ⚠️  Worker提取失败: {e}")

            # 本地提取
            async with self.session.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    html = await resp.text()

                    # 简单提取
                    import re

                    title_match = re.search(r"<title[^>]*>([^<]*)</title>", html, re.I)
                    title = title_match.group(1).strip() if title_match else ""

                    # 清理HTML
                    text = re.sub(
                        r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.I
                    )
                    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=re.I)
                    text = re.sub(r"<[^>]+>", " ", text)
                    text = " ".join(text.split())

                    return {
                        "title": title,
                        "content": text[:5000],
                        "excerpt": text[:200] + "..." if len(text) > 200 else text,
                        "author": "",
                        "published_time": None,
                        "extraction_method": "local",
                    }
        except Exception as e:
            print(f"    ⚠️  内容提取失败: {str(e)[:50]}")

        return None

    def clean_text(self, text: str) -> str:
        """清洗文本"""
        if not text:
            return ""

        # 解码HTML实体
        import html

        text = html.unescape(text)

        # 规范化空白
        text = " ".join(text.split())

        return text.strip()

    async def process_article(self, entry: Dict, source: Dict) -> bool:
        """处理单篇文章"""
        url = entry.get("link", "")
        if not url:
            return False

        # 检查URL是否已存在
        result = self.supabase.table("articles").select("id").eq("url", url).execute()
        if result.data:
            print(f"    ⏭️  已存在，跳过")
            return False

        # 提取内容
        print(f"    📝 提取内容...")
        extracted = await self.extract_content(url, source.get("anti_scraping", "None"))
        if not extracted:
            print(f"    ❌ 内容提取失败")
            return False

        self.stats["articles_extracted"] += 1

        # 准备数据
        title = extracted.get("title") or entry.get("title", "Untitled")
        content = self.clean_text(extracted.get("content", ""))

        # 计算SimHash
        simhash = self.compute_simhash(title + " " + content[:500])

        # 检查重复
        print(f"    🔍 SimHash去重检查...")
        if await self.check_duplicate(simhash, url):
            print(f"    ⏭️  重复文章，跳过")
            self.stats["articles_deduped"] += 1
            return False

        # 保存到数据库
        print(f"    💾 保存到数据库...")
        try:
            # 处理 published_parsed (time.struct_time -> ISO format)
            published_at = None
            if entry.get("published_parsed"):
                try:
                    from time import mktime
                    from datetime import datetime as dt

                    published_at = dt.fromtimestamp(
                        mktime(entry["published_parsed"])
                    ).isoformat()
                except:
                    published_at = None

            article_data = {
                "title": title[:500],
                "content": content[:10000],
                "url": url,
                "source_id": source["id"],
                "published_at": published_at,
                "fetched_at": datetime.now().isoformat(),
                "simhash": simhash,
                "category": source["category"],
                "author": extracted.get("author", "")[:255],
                "summary": extracted.get("excerpt", "")[:500],
                "extraction_method": extracted.get("extraction_method", "local"),
            }

            result = self.supabase.table("articles").insert(article_data).execute()
            if result.data:
                print(f"    ✅ 保存成功")
                self.stats["articles_saved"] += 1
                return True
        except Exception as e:
            print(f"    ❌ 保存失败: {e}")

        return False

    async def process_source(self, source: Dict) -> int:
        """处理单个RSS源"""
        print(f"\n📰 {source['name']} ({source['category']})")
        print(f"   URL: {source['rss_url'][:60]}...")

        try:
            # 抓取RSS
            async with self.session.get(
                source["rss_url"],
                headers={"User-Agent": "Mozilla/5.0 (compatible; RSSCrawler/1.0)"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status != 200:
                    print(f"   ❌ HTTP {resp.status}")
                    self.stats["sources_failed"] += 1
                    return 0

                content = await resp.text()
                feed = feedparser.parse(content)

                if not feed.entries:
                    print(f"   ⚠️  无文章")
                    return 0

                entries = feed.entries[:MAX_ARTICLES_PER_SOURCE]
                print(
                    f"   ✅ 获取 {len(feed.entries)} 篇文章，处理前 {len(entries)} 篇"
                )

                saved_count = 0
                for i, entry in enumerate(entries, 1):
                    print(
                        f"\n   [{i}/{len(entries)}] {entry.get('title', 'N/A')[:50]}..."
                    )
                    if await self.process_article(entry, source):
                        saved_count += 1
                    self.stats["articles_fetched"] += 1

                self.stats["sources_processed"] += 1
                return saved_count

        except Exception as e:
            print(f"   ❌ 错误: {str(e)[:60]}")
            self.stats["sources_failed"] += 1
            return 0

    async def run_test(self):
        """运行完整测试"""
        print("=" * 80)
        print("🚀 完整流程测试")
        print("=" * 80)
        print(f"⏱️  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        # 获取验证可用的源
        print("📊 获取验证可用的RSS源...")
        sources = (
            self.supabase.table("rss_sources")
            .select("*")
            .eq("status", "active")
            .execute()
            .data
        )

        if MAX_SOURCES:
            sources = sources[:MAX_SOURCES]

        self.stats["sources_total"] = len(sources)
        print(f"✅ 获取到 {len(sources)} 个验证可用的源")
        print()

        # 创建爬取日志
        log_result = (
            self.supabase.table("crawl_logs")
            .insert(
                {
                    "started_at": datetime.now().isoformat(),
                    "sources_count": len(sources),
                    "status": "running",
                }
            )
            .execute()
        )
        log_id = log_result.data[0]["id"] if log_result.data else None

        # 并发处理源
        semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)

        async def process_with_limit(source):
            async with semaphore:
                return await self.process_source(source)

        tasks = [process_with_limit(s) for s in sources]
        results = await asyncio.gather(*tasks)

        total_saved = sum(results)

        # 更新日志
        if log_id:
            self.supabase.table("crawl_logs").update(
                {
                    "completed_at": datetime.now().isoformat(),
                    "articles_fetched": self.stats["articles_fetched"],
                    "articles_new": self.stats["articles_saved"],
                    "articles_deduped": self.stats["articles_deduped"],
                    "errors_count": len(self.stats["errors"]),
                    "status": "completed",
                }
            ).eq("id", log_id).execute()

        # 打印统计
        self._print_summary(total_saved)

    def _print_summary(self, total_saved: int):
        """打印统计"""
        print("\n" + "=" * 80)
        print("📊 完整流程测试报告")
        print("=" * 80)
        print()
        print("【源统计】")
        print(f"  总源数: {self.stats['sources_total']}")
        print(f"  处理成功: {self.stats['sources_processed']}")
        print(f"  处理失败: {self.stats['sources_failed']}")
        print()
        print("【文章统计】")
        print(f"  获取文章数: {self.stats['articles_fetched']}")
        print(f"  成功提取: {self.stats['articles_extracted']}")
        print(f"  SimHash去重: {self.stats['articles_deduped']}")
        print(f"  成功保存: {self.stats['articles_saved']}")
        print()
        print("【成功率】")
        if self.stats["articles_fetched"] > 0:
            extraction_rate = (
                self.stats["articles_extracted"] / self.stats["articles_fetched"] * 100
            )
            save_rate = (
                self.stats["articles_saved"] / self.stats["articles_fetched"] * 100
            )
            print(f"  内容提取率: {extraction_rate:.1f}%")
            print(f"  最终入库率: {save_rate:.1f}%")
        print()
        print(f"⏱️  结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)


async def main():
    async with FullPipelineTest() as tester:
        await tester.run_test()


if __name__ == "__main__":
    import sys

    # 设置环境变量
    if not os.getenv("SUPABASE_KEY"):
        print("❌ 请设置 SUPABASE_KEY 环境变量")
        sys.exit(1)

    asyncio.run(main())
