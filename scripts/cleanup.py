#!/usr/bin/env python3
"""
90天数据自动清理脚本
"""

import os
from datetime import datetime, timedelta
from supabase import create_client


def cleanup_old_articles(dry_run: bool = False):
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_key:
        print("❌ 错误: 未设置SUPABASE_KEY")
        return

    supabase = create_client(supabase_url, supabase_key)

    cutoff_date = (datetime.now() - timedelta(days=90)).isoformat()

    try:
        count_result = (
            supabase.table("articles")
            .select("id", count="exact")
            .lt("fetched_at", cutoff_date)
            .execute()
        )

        count = count_result.count

        if dry_run:
            print(f"[DRY RUN] 将删除 {count} 篇文章 (90天前)")
            return

        if count == 0:
            print("✅ 没有需要清理的旧数据")
            return

        result = (
            supabase.table("articles").delete().lt("fetched_at", cutoff_date).execute()
        )

        print(f"✅ 已删除 {count} 篇文章")

        supabase.table("cleanup_logs").insert(
            {"deleted_count": count, "cutoff_date": cutoff_date}
        ).execute()

    except Exception as e:
        print(f"❌ 清理失败: {e}")


if __name__ == "__main__":
    import sys

    dry_run = "--dry-run" in sys.argv
    cleanup_old_articles(dry_run)
