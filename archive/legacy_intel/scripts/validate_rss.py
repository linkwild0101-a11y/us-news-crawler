#!/usr/bin/env python3
"""
RSS源可用性验证工具
验证数据库中哪些RSS源是可访问的
支持本地和GitHub Actions运行
"""

import asyncio
import aiohttp
import feedparser
import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Optional
from supabase import create_client

# 配置
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://lwigqxyfxevldfjdeokp.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
WORKER_URL = os.getenv("WORKER_URL")  # Cloudflare Worker URL
RAILWAY_URL = os.getenv("RAILWAY_URL")  # Railway Proxy URL

# 测试配置
TEST_TIMEOUT = 20  # 请求超时时间
WORKER_TIMEOUT = 30  # Worker 请求超时时间（更长，因为需要代理访问）
RAILWAY_TIMEOUT = 30  # Railway 请求超时时间
MAX_SOURCES = None  # None=测试全部，设置为数字限制测试数量
VALIDATE_ALL = (
    os.getenv("VALIDATE_ALL", "false").lower() == "true"
)  # true=验证所有源，false=只验证active


class RSSValidator:
    def __init__(self):
        if not SUPABASE_KEY:
            print("❌ 错误: 未设置 SUPABASE_KEY 环境变量")
            sys.exit(1)

        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.results = []
        self.stats = {"total": 0, "working": 0, "failed": 0, "by_category": {}}

    async def test_source(self, source: Dict, session: aiohttp.ClientSession) -> Dict:
        """测试单个RSS源，支持直接访问和通过Worker访问"""
        result = {
            "id": source["id"],
            "name": source["name"],
            "category": source["category"],
            "rss_url": source["rss_url"],
            "status": "unknown",
            "http_status": None,
            "articles_count": 0,
            "error": None,
            "response_time": 0,
            "access_method": "direct",  # direct 或 worker
        }

        start_time = datetime.now()

        # 1. 首先尝试直接访问
        try:
            async with session.get(
                source["rss_url"],
                headers={"User-Agent": "Mozilla/5.0 (compatible; RSSValidator/1.0)"},
                timeout=aiohttp.ClientTimeout(total=TEST_TIMEOUT),
            ) as resp:
                result["http_status"] = resp.status
                result["response_time"] = (datetime.now() - start_time).total_seconds()

                if resp.status == 200:
                    content = await resp.text()
                    feed = feedparser.parse(content)

                    if feed.entries:
                        result["status"] = "working"
                        result["articles_count"] = len(feed.entries)
                        result["latest_article"] = feed.entries[0].get("title", "N/A")[
                            :60
                        ]
                        return result
                    else:
                        result["status"] = "empty"
                        result["error"] = "RSS parsed but no entries found"
                else:
                    result["status"] = "error"
                    result["error"] = f"HTTP {resp.status}"

        except asyncio.TimeoutError:
            result["status"] = "timeout"
            result["error"] = f"Timeout after {TEST_TIMEOUT}s"
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:100]

        # 2. 首次验证失败后，统一再尝试 Worker + Railway 各一次
        anti_scraping = source.get("anti_scraping", "None")
        prefer_railway_first = anti_scraping == "railway"

        retry_chain = []
        if prefer_railway_first:
            if RAILWAY_URL:
                retry_chain.append(("railway", self._test_via_railway))
            if WORKER_URL:
                retry_chain.append(("worker", self._test_via_worker))
        else:
            if WORKER_URL:
                retry_chain.append(("worker", self._test_via_worker))
            if RAILWAY_URL:
                retry_chain.append(("railway", self._test_via_railway))

        for method, retry_func in retry_chain:
            icon = "🌐" if method == "worker" else "🚂"
            print(
                f"  {icon} {source['name'][:40]:<40} | 首次失败，尝试 {method}..."
            )
            retry_result = await retry_func(source)
            if retry_result["status"] == "working":
                return retry_result
            result[f"{method}_error"] = retry_result.get("error", f"{method} failed")

        return result

    async def _test_via_worker(self, source: Dict) -> Dict:
        """通过 Cloudflare Worker 测试 RSS 源"""
        result = {
            "id": source["id"],
            "name": source["name"],
            "category": source["category"],
            "rss_url": source["rss_url"],
            "status": "unknown",
            "http_status": None,
            "articles_count": 0,
            "error": None,
            "response_time": 0,
            "access_method": "worker",
        }

        start_time = datetime.now()

        try:
            # 使用 aiohttp 直接请求 Worker
            timeout = aiohttp.ClientTimeout(total=WORKER_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as worker_session:
                async with worker_session.post(
                    f"{WORKER_URL}/extract",
                    json={
                        "url": source["rss_url"],
                        "raw": True,
                    },  # 使用 raw 模式获取原始 RSS XML
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    result["http_status"] = resp.status
                    result["response_time"] = (
                        datetime.now() - start_time
                    ).total_seconds()

                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("success"):
                            # Worker 返回了 HTML 内容，需要检查是否包含 RSS 特征
                            content = data.get("content", "")
                            # 简单检查是否包含 RSS/Feed 特征
                            if (
                                "<rss" in content.lower()
                                or "<feed" in content.lower()
                                or "<?xml" in content
                            ):
                                # 解析 RSS 内容
                                feed = feedparser.parse(content)
                                if feed.entries:
                                    result["status"] = "working"
                                    result["articles_count"] = len(feed.entries)
                                    result["latest_article"] = feed.entries[0].get(
                                        "title", "N/A"
                                    )[:60]
                                else:
                                    result["status"] = "empty"
                                    result["error"] = (
                                        "RSS parsed but no entries found via Worker"
                                    )
                            else:
                                # 可能返回的是文章页面而非 RSS feed
                                result["status"] = "working"
                                result["articles_count"] = 1
                                result["latest_article"] = data.get(
                                    "title", "Via Worker"
                                )[:60]
                                result["note"] = "Via Worker (HTML page)"
                        else:
                            result["status"] = "error"
                            result["error"] = (
                                f"Worker error: {data.get('error', 'Unknown')}"
                            )
                    else:
                        result["status"] = "error"
                        result["error"] = f"Worker HTTP {resp.status}"

        except asyncio.TimeoutError:
            result["status"] = "timeout"
            result["error"] = f"Worker timeout after {WORKER_TIMEOUT}s"
        except Exception as e:
            result["status"] = "error"
            result["error"] = f"Worker error: {str(e)[:100]}"

        return result

    async def _test_via_railway(self, source: Dict) -> Dict:
        """通过 Railway 代理测试 RSS 源"""
        result = {
            "id": source["id"],
            "name": source["name"],
            "category": source["category"],
            "rss_url": source["rss_url"],
            "status": "unknown",
            "http_status": None,
            "articles_count": 0,
            "error": None,
            "response_time": 0,
            "access_method": "railway",
        }

        start_time = datetime.now()

        try:
            timeout = aiohttp.ClientTimeout(total=RAILWAY_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as railway_session:
                async with railway_session.get(
                    f"{RAILWAY_URL}/rss",
                    params={"url": source["rss_url"]},
                    headers={"Accept": "application/xml"},
                ) as resp:
                    result["http_status"] = resp.status
                    result["response_time"] = (
                        datetime.now() - start_time
                    ).total_seconds()

                    if resp.status == 200:
                        content = await resp.text()
                        # 解析 RSS
                        feed = feedparser.parse(content)

                        if feed.entries:
                            result["status"] = "working"
                            result["articles_count"] = len(feed.entries)
                            result["latest_article"] = feed.entries[0].get(
                                "title", "N/A"
                            )[:60]
                        else:
                            result["status"] = "empty"
                            result["error"] = (
                                "RSS parsed but no entries found via Railway"
                            )
                    else:
                        result["status"] = "error"
                        result["error"] = f"Railway HTTP {resp.status}"

        except asyncio.TimeoutError:
            result["status"] = "timeout"
            result["error"] = f"Railway timeout after {RAILWAY_TIMEOUT}s"
        except Exception as e:
            result["status"] = "error"
            result["error"] = f"Railway error: {str(e)[:100]}"

        return result

    async def validate_all(self):
        """验证所有RSS源"""
        print("=" * 70)
        print("🧪 RSS源可用性验证")
        print("=" * 70)
        print(
            f"⏱️  超时设置: {TEST_TIMEOUT}秒 (直接) / {WORKER_TIMEOUT}秒 (Worker) / {RAILWAY_TIMEOUT}秒 (Railway)"
        )
        print(f"🗄️  数据库: {SUPABASE_URL}")
        if WORKER_URL:
            print(f"🌐 Worker: {WORKER_URL}")
        else:
            print("⚠️  Worker URL 未设置")
        if RAILWAY_URL:
            print(f"🚂 Railway: {RAILWAY_URL}")
        else:
            print("⚠️  Railway URL 未设置")
        print()

        # 获取源
        print("📊 正在获取RSS源列表...")

        if VALIDATE_ALL:
            # 验证所有源（包括之前标记为error的）
            print("🔄 模式: 验证所有源（包括之前标记为error的）")
            sources = self.supabase.table("rss_sources").select("*").execute().data
        else:
            # 只验证active的源
            print("🔄 模式: 只验证active状态的源")
            sources = (
                self.supabase.table("rss_sources")
                .select("*")
                .eq("status", "active")
                .execute()
                .data
            )

        if MAX_SOURCES:
            sources = sources[:MAX_SOURCES]

        self.stats["total"] = len(sources)
        print(f"✅ 获取到 {len(sources)} 个RSS源\n")

        # 并发测试
        print("🚀 开始测试...\n")
        timeout = aiohttp.ClientTimeout(total=TEST_TIMEOUT)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            # 使用 semaphore 限制并发
            semaphore = asyncio.Semaphore(10)

            async def test_with_limit(source):
                async with semaphore:
                    result = await self.test_source(source, session)
                    # 实时打印结果
                    status_icon = "✅" if result["status"] == "working" else "⚠️ "
                    access_method = result.get("access_method", "direct")
                    if access_method == "worker":
                        method_icon = "🌐"
                    elif access_method == "railway":
                        method_icon = "🚂"
                    else:
                        method_icon = ""
                    print(
                        f"{status_icon} {method_icon} {result['name'][:40]:<38} | {result['status']:<10} | {result.get('articles_count', 0):>3} articles"
                    )
                    return result

            tasks = [test_with_limit(s) for s in sources]
            self.results = await asyncio.gather(*tasks)

        # 统计
        self._calculate_stats()

        # 生成报告
        self._print_report()
        self._save_report()
        self._update_database()

    def _calculate_stats(self):
        """计算统计信息"""
        for result in self.results:
            if result["status"] == "working":
                self.stats["working"] += 1
            else:
                self.stats["failed"] += 1

            # 按分类统计
            cat = result["category"]
            if cat not in self.stats["by_category"]:
                self.stats["by_category"][cat] = {"total": 0, "working": 0}
            self.stats["by_category"][cat]["total"] += 1
            if result["status"] == "working":
                self.stats["by_category"][cat]["working"] += 1

    def _print_report(self):
        """打印报告"""
        print("\n" + "=" * 70)
        print("📊 验证报告")
        print("=" * 70)

        # 总体统计
        print(f"\n总体统计:")
        print(f"  总源数: {self.stats['total']}")
        print(
            f"  ✅ 可用: {self.stats['working']} ({self.stats['working'] / self.stats['total'] * 100:.1f}%)"
        )
        print(
            f"  ❌ 不可用: {self.stats['failed']} ({self.stats['failed'] / self.stats['total'] * 100:.1f}%)"
        )

        # 按分类统计
        print(f"\n按分类统计:")
        for cat, data in self.stats["by_category"].items():
            rate = data["working"] / data["total"] * 100 if data["total"] > 0 else 0
            print(
                f"  {cat:<12}: {data['working']:>3}/{data['total']:<3} ({rate:>5.1f}%)"
            )

        # 不可用的源
        failed_sources = [r for r in self.results if r["status"] != "working"]
        if failed_sources:
            print(f"\n❌ 不可用的源 ({len(failed_sources)}个):")
            for r in failed_sources[:10]:  # 只显示前10个
                print(
                    f"  - {r['name'][:40]:<40} | {r['status']:<10} | {r['error'][:40]}"
                )
            if len(failed_sources) > 10:
                print(f"  ... 还有 {len(failed_sources) - 10} 个")

        # 可用的源示例
        working_sources = [r for r in self.results if r["status"] == "working"]
        worker_sources = [
            r for r in working_sources if r.get("access_method") == "worker"
        ]

        if worker_sources:
            print(f"\n🌐 通过 Worker 访问的源 ({len(worker_sources)}个):")
            for r in worker_sources[:5]:
                print(f"  - {r['name'][:40]:<40} | {r['articles_count']:>3} articles")
                if len(worker_sources) > 5:
                    print(f"    ... 还有 {len(worker_sources) - 5} 个")

        if working_sources:
            print(f"\n✅ 可用的源示例 ({len(working_sources)}个中的前5个):")
            for r in working_sources[:5]:
                access_info = (
                    "[Worker]" if r.get("access_method") == "worker" else "[Direct]"
                )
                print(
                    f"  - {r['name'][:40]:<40} | {access_info:<10} | {r['articles_count']:>3} articles"
                )
                print(f"    Latest: {r.get('latest_article', 'N/A')}")

        print("\n" + "=" * 70)

    def _save_report(self):
        """保存详细报告到JSON"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "stats": self.stats,
            "results": self.results,
        }

        filename = (
            f"rss_validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"\n💾 详细报告已保存: {filename}")

        # 同时保存CSV格式
        csv_filename = (
            f"rss_validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        with open(csv_filename, "w", encoding="utf-8") as f:
            f.write(
                "id,name,category,rss_url,status,http_status,articles_count,error\n"
            )
            for r in self.results:
                f.write(
                    f'{r["id"]},{r["name"]},{r["category"]},{r["rss_url"]},{r["status"]},{r["http_status"]},{r["articles_count"]},"{r["error"] or ""}"\n'
                )

        print(f"💾 CSV报告已保存: {csv_filename}")

    def _update_database(self):
        """更新数据库中的源状态"""
        print("\n🔄 更新数据库状态...")

        updated = 0
        for result in self.results:
            try:
                status = "active" if result["status"] == "working" else "error"
                self.supabase.table("rss_sources").update(
                    {"status": status, "last_fetch": datetime.now().isoformat()}
                ).eq("id", result["id"]).execute()
                updated += 1
            except Exception as e:
                print(f"  ⚠️  更新源 {result['id']} 失败: {e}")

        print(f"✅ 已更新 {updated} 个源的状态")


async def main():
    validator = RSSValidator()
    await validator.validate_all()

    # 如果有可用源，返回成功
    if validator.stats["working"] > 0:
        print(f"\n✅ 验证完成！发现 {validator.stats['working']} 个可用源")
        return 0
    else:
        print(f"\n⚠️  警告：没有可用的RSS源")
        return 1


if __name__ == "__main__":
    # 设置事件循环策略（兼容性）
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    exit_code = asyncio.run(main())
    sys.exit(exit_code)
