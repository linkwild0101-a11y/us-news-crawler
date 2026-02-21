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
import re
from datetime import datetime
from typing import List, Dict, Optional
from supabase import create_client
from urllib.parse import quote, urlparse, urlunparse

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
WORKER_URL = os.getenv("WORKER_URL")
RAILWAY_URL = os.getenv("RAILWAY_URL")


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

    def _log(self, message: str):
        """统一日志输出，确保CI环境实时刷新"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}", flush=True)

    def _normalize_article_url(self, url: str) -> str:
        """修复部分RSS源返回的异常链接（如 .twtw）。"""
        if not url:
            return ""

        normalized = str(url).strip()
        if not normalized:
            return ""

        if normalized.startswith("//"):
            normalized = f"https:{normalized}"

        parsed = urlparse(normalized)
        if not parsed.scheme:
            if normalized.startswith("/"):
                return normalized
            parsed = urlparse(f"https://{normalized.lstrip('/')}")

        host = parsed.hostname or ""
        if not host:
            return normalized

        # 例如 www.ydn.com.twtw -> www.ydn.com.tw
        fixed_host = re.sub(r"\.([a-z]{2})\1$", r".\1", host)
        if fixed_host == host:
            return normalized

        netloc = fixed_host
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"

        fixed_url = urlunparse(
            (
                parsed.scheme or "https",
                netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )
        self._log(f"🔧 修正异常链接: {normalized} -> {fixed_url}")
        return fixed_url

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
                rss_url = source["rss_url"]
                anti_scraping = source.get("anti_scraping", "None")

                # 1) 先尝试直接抓取
                content = await self._fetch_rss_direct(rss_url)

                # 2) 直接失败后，根据策略走代理重试
                if not content:
                    if anti_scraping == "railway":
                        content = await self._fetch_rss_via_railway(rss_url)
                        if not content:
                            content = await self._fetch_rss_via_worker(rss_url)
                    elif anti_scraping in ["Cloudflare", "Paywall", "Partial Paywall"]:
                        content = await self._fetch_rss_via_worker(rss_url)
                        if not content:
                            content = await self._fetch_rss_via_railway(rss_url)

                if not content:
                    raise Exception("RSS内容为空")

                feed = feedparser.parse(content)
                if not feed.entries:
                    raise Exception("RSS无有效条目")

                fetch_method = "direct"
                if anti_scraping == "railway" and WORKER_URL and RAILWAY_URL:
                    fetch_method = "railway/worker-fallback"
                elif anti_scraping in ["Cloudflare", "Paywall", "Partial Paywall"]:
                    fetch_method = "worker/railway-fallback"

                self._log(
                    f"✅ RSS抓取成功 {source['name']} | 条目: {len(feed.entries[:10])} | "
                    f"策略: {fetch_method}"
                )

                return {
                    "source_id": source["id"],
                    "category": source["category"],
                    "anti_scraping": anti_scraping,
                    "entries": feed.entries[:10],  # 只取前10条
                }
            except Exception as e:
                self._log(f"⚠️  RSS抓取失败 {source['name']}: {e}")
                self.stats["errors"] += 1
                return None

    async def _fetch_rss_direct(self, rss_url: str) -> Optional[str]:
        """直接抓取RSS内容"""
        try:
            async with self.session.get(
                rss_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; RSSCrawler/1.0)"},
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.text()
        except Exception:
            return None

    async def _fetch_rss_via_worker(self, rss_url: str) -> Optional[str]:
        """通过Cloudflare Worker抓取RSS内容"""
        if not WORKER_URL:
            return None
        try:
            async with self.session.post(
                f"{WORKER_URL}/extract",
                json={"url": rss_url, "raw": True},
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if not data.get("success"):
                    return None
                return data.get("content", "")
        except Exception:
            return None

    async def _fetch_rss_via_railway(self, rss_url: str) -> Optional[str]:
        """通过Railway代理抓取RSS内容"""
        if not RAILWAY_URL:
            return None
        try:
            encoded_url = quote(rss_url, safe="")
            async with self.session.get(
                f"{RAILWAY_URL}/rss?url={encoded_url}",
                headers={"Accept": "application/xml"},
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.text()
        except Exception:
            return None

    async def extract_content(self, url: str, anti_scraping: str) -> Optional[Dict]:
        """混合内容提取"""
        # 跳过 Twitter/X 链接（已知会有 header 过长问题）
        if "twitter.com" in url or "x.com" in url:
            print(f"  ⏭️  跳过 Twitter/X 链接")
            return None

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
            self._log(f"⚠️  去重检查失败: {e}")
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
            self._log(f"⚠️  保存文章失败: {e}")
            return False

    async def process_entry(self, entry, source_info: Dict) -> Optional[Dict]:
        """处理单个RSS条目"""
        raw_url = entry.get("link", "")
        url = self._normalize_article_url(raw_url)
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

        # 处理 published_parsed (time.struct_time -> ISO format)
        published_at = None
        if entry.get("published_parsed"):
            try:
                from time import mktime

                published_at = datetime.fromtimestamp(
                    mktime(entry["published_parsed"])
                ).isoformat()
            except:
                published_at = None

        article = {
            "title": title,
            "content": content,
            "url": url,
            "source_id": source_info["source_id"],
            "published_at": published_at,
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
        self._log("🚀 开始爬取RSS源...")

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

        self._log(f"📊 共 {len(sources)} 个RSS源")

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

        total_entries = len(all_entries)
        self._log(f"📰 获取到 {total_entries} 个条目，开始处理...")

        # 处理条目（限制并发）
        semaphore = asyncio.Semaphore(10)
        progress_lock = asyncio.Lock()
        processed_entries = 0
        start_time = datetime.now()

        async def process_with_limit(entry, source_info):
            nonlocal processed_entries
            async with semaphore:
                result = await self.process_entry(entry, source_info)
            async with progress_lock:
                processed_entries += 1
                if processed_entries % 50 == 0 or processed_entries == total_entries:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    rate = processed_entries / elapsed if elapsed > 0 else 0
                    self._log(
                        f"⏳ 条目处理进度: {processed_entries}/{total_entries} | "
                        f"新增: {self.stats['articles_new']} | "
                        f"去重: {self.stats['articles_deduped']} | "
                        f"速率: {rate:.2f} 条/s"
                    )
            return result

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
        self._log("=" * 60)
        self._log("📊 爬取完成统计")
        self._log("=" * 60)
        self._log(f"处理的源: {self.stats['sources_processed']}")
        self._log(f"获取条目: {len(all_entries)}")
        self._log(f"新增文章: {self.stats['articles_new']}")
        self._log(f"去重跳过: {self.stats['articles_deduped']}")
        self._log(f"错误数: {self.stats['errors']}")


async def main():
    async with RSSCrawler() as crawler:
        await crawler.crawl_sources()


if __name__ == "__main__":
    asyncio.run(main())
