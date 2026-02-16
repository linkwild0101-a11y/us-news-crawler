#!/usr/bin/env python3
"""
RSS爬虫核心 - 异步抓取RSS并提取内容
"""

import asyncio
import aiohttp
import feedparser
import json
import os
import hashlib
from datetime import datetime
from typing import List, Dict, Optional
from supabase import create_client
from urllib.parse import urljoin, urlparse

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
WORKER_URL = os.getenv("WORKER_URL")


class RSSCrawler:
    def __init__(self):
        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.session: Optional[aiohttp.ClientSession] = None
        self.semaphore = asyncio.Semaphore(20)  # 限制并发数
        self.stats = {
            "sources_processed": 0,
            "articles_fetched": 0,
            "articles_new": 0,
            "articles_deduped": 0,
            "errors": 0,
        }

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def fetch_rss(self, source: Dict) -> Optional[Dict]:
        """抓取单个RSS源"""
        async with self.semaphore:
            try:
                async with self.session.get(
                    source["rss_url"],
                    headers={"User-Agent": "Mozilla/5.0 (compatible; RSSCrawler/1.0)"},
                ) as resp:
                    if resp.status != 200:
                        raise Exception(f"HTTP {resp.status}")

                    content = await resp.text()
                    feed = feedparser.parse(content)

                    return {
                        "source_id": source["id"],
                        "category": source["category"],
                        "anti_scraping": source.get("anti_scraping", "None"),
                        "entries": feed.entries[:10],  # 只取前10条
                    }
            except Exception as e:
                print(f"  ⚠️  RSS抓取失败 {source['name']}: {e}")
                self.stats["errors"] += 1
                return None

    async def extract_content(self, url: str, anti_scraping: str) -> Optional[Dict]:
        """混合内容提取"""
        try:
            if anti_scraping in ["Cloudflare", "Paywall"] and WORKER_URL:
                # 使用Cloudflare Worker
                async with self.session.post(
                    f"{WORKER_URL}/extract",
                    json={"url": url},
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("success"):
                            data["extraction_method"] = "cloudflare"
                            return data

            # 本地提取（简化版）
            async with self.session.get(
                url, headers={"User-Agent": "Mozilla/5.0 (compatible; RSSCrawler/1.0)"}
            ) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    # 简单提取标题和正文
                    title = self._extract_title(html)
                    content = self._extract_content_simple(html)
                    return {
                        "title": title,
                        "content": content,
                        "extraction_method": "local",
                    }
        except Exception as e:
            print(f"  ⚠️  内容提取失败: {e}")

        return None

    def _extract_title(self, html: str) -> str:
        """从HTML中提取标题"""
        import re

        match = re.search(r"<title[^>]*>([^<]*)</title>", html, re.I)
        return match.group(1).strip() if match else ""

    def _extract_content_simple(self, html: str) -> str:
        """简单提取正文"""
        import re

        # 移除script和style
        html = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.I)
        html = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", html, flags=re.I)
        # 提取文本
        text = re.sub(r"<[^>]+>", " ", html)
        # 清理
        text = " ".join(text.split())
        return text[:5000]  # 限制长度

    def compute_simhash(self, text: str) -> str:
        """计算SimHash"""
        try:
            from simhash import Simhash

            if not text:
                return "0"
            return str(Simhash(text[:1000]))
        except ImportError:
            # 如果没有simhash库，使用MD5作为fallback
            return hashlib.md5(text[:1000].encode()).hexdigest()

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
            from datetime import timedelta

            cutoff = (datetime.now() - timedelta(days=7)).isoformat()

            result = (
                self.supabase.table("articles")
                .select("id, simhash")
                .gte("fetched_at", cutoff)
                .execute()
            )

            for article in result.data:
                if (
                    article.get("simhash")
                    and self._hamming_distance(simhash, article["simhash"]) <= 3
                ):
                    return True

            return False
        except Exception as e:
            print(f"  ⚠️  去重检查失败: {e}")
            return False

    def _hamming_distance(self, hash1: str, hash2: str) -> int:
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
            return 100  # 如果转换失败，返回大数表示不相似

    async def save_article(self, article: Dict) -> bool:
        """保存文章到数据库"""
        try:
            result = (
                self.supabase.table("articles")
                .insert(
                    {
                        "title": article["title"][:500],
                        "content": article.get("content", "")[:10000],
                        "url": article["url"],
                        "source_id": article["source_id"],
                        "published_at": article.get("published_at"),
                        "fetched_at": datetime.now().isoformat(),
                        "simhash": article.get("simhash"),
                        "category": article.get("category"),
                        "author": article.get("author", "")[:255],
                        "extraction_method": article.get("extraction_method", "local"),
                    }
                )
                .execute()
            )

            return bool(result.data)
        except Exception as e:
            print(f"  ⚠️  保存文章失败: {e}")
            return False

    async def process_entry(self, entry, source_info: Dict) -> Optional[Dict]:
        """处理单个RSS条目"""
        url = entry.get("link", "")
        if not url:
            return None

        # 检查是否已存在
        result = self.supabase.table("articles").select("id").eq("url", url).execute()
        if result.data:
            return None

        # 提取内容
        extracted = await self.extract_content(url, source_info["anti_scraping"])
        if not extracted:
            return None

        # 准备文章数据
        title = entry.get("title", extracted.get("title", "Untitled"))
        content = extracted.get("content", entry.get("summary", ""))

        article = {
            "title": title,
            "content": content,
            "url": url,
            "source_id": source_info["source_id"],
            "published_at": entry.get("published_parsed"),
            "category": source_info["category"],
            "author": entry.get("author", extracted.get("author", "")),
            "extraction_method": extracted.get("extraction_method", "local"),
            "simhash": self.compute_simhash(title + " " + content[:500]),
        }

        # 检查SimHash去重
        if await self.check_duplicate(article["simhash"], url):
            self.stats["articles_deduped"] += 1
            return None

        # 保存
        if await self.save_article(article):
            self.stats["articles_new"] += 1
            return article

        return None

    async def crawl_sources(self, limit: Optional[int] = None):
        """主爬取流程"""
        print("🚀 开始爬取RSS源...")

        # 获取所有active的sources
        sources = (
            self.supabase.table("rss_sources")
            .select("*")
            .eq("status", "active")
            .execute()
            .data
        )

        if limit:
            sources = sources[:limit]

        print(f"📊 共 {len(sources)} 个RSS源")

        # 创建日志记录
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

        # 并发抓取RSS
        tasks = [self.fetch_rss(source) for source in sources]
        rss_results = await asyncio.gather(*tasks)

        # 处理每个源的条目
        all_entries = []
        for source, rss_data in zip(sources, rss_results):
            if rss_data and rss_data["entries"]:
                self.stats["sources_processed"] += 1
                for entry in rss_data["entries"]:
                    all_entries.append(
                        (
                            entry,
                            {
                                "source_id": source["id"],
                                "category": source["category"],
                                "anti_scraping": source.get("anti_scraping", "None"),
                            },
                        )
                    )

        print(f"📰 获取到 {len(all_entries)} 个条目，开始处理...")

        # 处理条目（限制并发）
        semaphore = asyncio.Semaphore(10)

        async def process_with_limit(entry, source_info):
            async with semaphore:
                return await self.process_entry(entry, source_info)

        entry_tasks = [process_with_limit(e, s) for e, s in all_entries]
        await asyncio.gather(*entry_tasks)

        # 更新日志
        if log_id:
            self.supabase.table("crawl_logs").update(
                {
                    "completed_at": datetime.now().isoformat(),
                    "articles_fetched": len(all_entries),
                    "articles_new": self.stats["articles_new"],
                    "articles_deduped": self.stats["articles_deduped"],
                    "errors_count": self.stats["errors"],
                    "status": "completed",
                }
            ).eq("id", log_id).execute()

        # 打印统计
        print("\n" + "=" * 60)
        print("📊 爬取完成统计")
        print("=" * 60)
        print(f"处理的源: {self.stats['sources_processed']}")
        print(f"获取条目: {len(all_entries)}")
        print(f"新增文章: {self.stats['articles_new']}")
        print(f"去重跳过: {self.stats['articles_deduped']}")
        print(f"错误数: {self.stats['errors']}")


async def main():
    async with RSSCrawler() as crawler:
        await crawler.crawl_sources()


if __name__ == "__main__":
    asyncio.run(main())
