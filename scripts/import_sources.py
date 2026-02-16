#!/usr/bin/env python3
"""
导入RSS源到Supabase数据库
"""

import json
import os
from pathlib import Path
from supabase import create_client


def import_sources():
    """导入sources.json到Supabase"""

    # 读取环境变量
    supabase_url = os.getenv("SUPABASE_URL", "https://lwigqxyfxevldfjdeokp.supabase.co")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_key:
        print("❌ 错误: 未设置SUPABASE_KEY环境变量")
        print("请设置: export SUPABASE_KEY='your-service-role-key'")
        return

    # 创建Supabase客户端
    try:
        supabase = create_client(supabase_url, supabase_key)
        print("✅ Supabase连接成功")
    except Exception as e:
        print(f"❌ Supabase连接失败: {e}")
        return

    # 读取sources.json
    base_dir = Path("/Users/nobody1/Documents/US_newslist")
    sources_file = base_dir / "data" / "sources.json"

    try:
        with open(sources_file, "r", encoding="utf-8") as f:
            sources = json.load(f)
        print(f"📄 读取到 {len(sources)} 个源")
    except Exception as e:
        print(f"❌ 读取sources.json失败: {e}")
        return

    # 批量导入
    success = 0
    failed = 0
    skipped = 0

    print("\n🚀 开始导入...")

    for source in sources:
        try:
            # 检查是否已存在
            existing = (
                supabase.table("rss_sources")
                .select("id")
                .eq("rss_url", source["rss_url"])
                .execute()
            )

            if existing.data:
                skipped += 1
                continue

            # 插入新记录
            result = (
                supabase.table("rss_sources")
                .insert(
                    {
                        "name": source["name"],
                        "rss_url": source["rss_url"],
                        "listing_url": source.get("listing_url", ""),
                        "category": source["category"],
                        "anti_scraping": source.get("anti_scraping", "None"),
                        "status": "active",
                    }
                )
                .execute()
            )

            if result.data:
                success += 1
                if success % 50 == 0:
                    print(f"   已导入 {success} 个源...")
            else:
                failed += 1

        except Exception as e:
            failed += 1
            print(f"   ⚠️  导入失败 {source['name']}: {e}")

    # 统计
    print("\n" + "=" * 60)
    print("📊 导入统计")
    print("=" * 60)
    print(f"成功: {success}")
    print(f"跳过(已存在): {skipped}")
    print(f"失败: {failed}")
    print(f"总计: {success + skipped + failed}")

    # 验证数据库中的数量
    try:
        count_result = (
            supabase.table("rss_sources").select("id", count="exact").execute()
        )
        db_count = count_result.count
        print(f"\n✅ 数据库中共有 {db_count} 个RSS源")
    except Exception as e:
        print(f"⚠️ 无法验证数据库数量: {e}")


if __name__ == "__main__":
    import_sources()
