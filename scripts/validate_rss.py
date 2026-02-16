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

# 测试配置
TEST_TIMEOUT = 20  # 请求超时时间
MAX_SOURCES = None  # None=测试全部，设置为数字限制测试数量


class RSSValidator:
    def __init__(self):
        if not SUPABASE_KEY:
            print("❌ 错误: 未设置 SUPABASE_KEY 环境变量")
            sys.exit(1)

        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.results = []
        self.stats = {"total": 0, "working": 0, "failed": 0, "by_category": {}}

    async def test_source(self, source: Dict, session: aiohttp.ClientSession) -> Dict:
        """测试单个RSS源"""
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
        }

        start_time = datetime.now()

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
                        # 记录最新文章标题
                        result["latest_article"] = feed.entries[0].get("title", "N/A")[
                            :60
                        ]
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

        return result

    async def validate_all(self):
        """验证所有RSS源"""
        print("=" * 70)
        print("🧪 RSS源可用性验证")
        print("=" * 70)
        print(f"⏱️  超时设置: {TEST_TIMEOUT}秒")
        print(f"🗄️  数据库: {SUPABASE_URL}")
        print()

        # 获取所有源
        print("📊 正在获取RSS源列表...")
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
                    print(
                        f"{status_icon} {result['name'][:40]:<40} | {result['status']:<10} | {result.get('articles_count', 0):>3} articles"
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
        if working_sources:
            print(f"\n✅ 可用的源示例 ({len(working_sources)}个中的前5个):")
            for r in working_sources[:5]:
                print(f"  - {r['name'][:40]:<40} | {r['articles_count']:>3} articles")
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
