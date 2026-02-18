#!/usr/bin/env python3
"""
重置文章分析状态
用于重新分析之前失败的文章
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client


def reset_analysis_status(hours: int = 24, reset_all: bool = False):
    """
    重置文章分析状态

    Args:
        hours: 重置最近多少小时内的文章
        reset_all: 是否重置所有已分析的文章
    """
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        print("❌ 缺少 Supabase 配置")
        return

    supabase = create_client(supabase_url, supabase_key)

    if reset_all:
        # 重置所有已分析的文章
        print("⚠️  重置所有已分析的文章...")
        result = (
            supabase.table("articles")
            .update({"analyzed_at": None})
            .neq("analyzed_at", "null")
            .execute()
        )
        print(f"✅ 已重置 {len(result.data)} 篇文章")

        # 删除所有分析聚类
        print("⚠️  删除所有分析聚类...")
        supabase.table("analysis_clusters").delete().neq("id", 0).execute()
        print("✅ 已删除所有聚类")

        # 删除所有信号
        print("⚠️  删除所有信号...")
        supabase.table("analysis_signals").delete().neq("id", 0).execute()
        print("✅ 已删除所有信号")

    else:
        # 只重置最近 N 小时的文章
        cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()

        print(f"📝 重置最近 {hours} 小时内分析的文章...")

        # 获取这些文章
        result = (
            supabase.table("articles")
            .select("id")
            .gte("analyzed_at", cutoff_time)
            .execute()
        )

        article_ids = [r["id"] for r in result.data]

        if not article_ids:
            print("✅ 没有找到需要重置的文章")
            return

        print(f"📊 找到 {len(article_ids)} 篇文章需要重置")

        # 重置文章状态
        for article_id in article_ids:
            supabase.table("articles").update({"analyzed_at": None}).eq(
                "id", article_id
            ).execute()

        print(f"✅ 已重置 {len(article_ids)} 篇文章的分析状态")

        # 删除相关的聚类
        print("🗑️  删除相关的聚类...")
        clusters = (
            supabase.table("analysis_clusters")
            .select("id")
            .gte("created_at", cutoff_time)
            .execute()
        )

        cluster_ids = [c["id"] for c in clusters.data]

        for cluster_id in cluster_ids:
            # 删除关联
            supabase.table("article_analyses").delete().eq(
                "cluster_id", cluster_id
            ).execute()
            # 删除聚类
            supabase.table("analysis_clusters").delete().eq("id", cluster_id).execute()

        print(f"✅ 已删除 {len(cluster_ids)} 个聚类")


def reset_shallow_analysis():
    """
    只重置浅层分析的文章（让热点进行深度分析）
    """
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        print("❌ 缺少 Supabase 配置")
        return

    supabase = create_client(supabase_url, supabase_key)

    print("📝 查找浅层分析的聚类...")

    # 获取浅层分析的聚类
    clusters = (
        supabase.table("analysis_clusters")
        .select("*")
        .eq("analysis_depth", "shallow")
        .execute()
    )

    if not clusters.data:
        print("✅ 没有浅层分析的聚类")
        return

    print(f"📊 找到 {len(clusters.data)} 个浅层分析聚类")

    # 获取关联的文章ID
    cluster_ids = [c["id"] for c in clusters.data]

    relations = (
        supabase.table("article_analyses")
        .select("article_id")
        .in_("cluster_id", cluster_ids)
        .execute()
    )

    article_ids = list(set([r["article_id"] for r in relations.data]))

    print(f"📊 涉及 {len(article_ids)} 篇文章")

    # 重置文章状态
    for article_id in article_ids:
        supabase.table("articles").update({"analyzed_at": None}).eq(
            "id", article_id
        ).execute()

    print(f"✅ 已重置 {len(article_ids)} 篇文章")

    # 删除浅层聚类
    for cluster_id in cluster_ids:
        supabase.table("article_analyses").delete().eq(
            "cluster_id", cluster_id
        ).execute()
        supabase.table("analysis_clusters").delete().eq("id", cluster_id).execute()

    print(f"✅ 已删除 {len(cluster_ids)} 个浅层聚类")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="重置文章分析状态")
    parser.add_argument(
        "--hours", type=int, default=24, help="重置最近多少小时内的文章 (默认: 24)"
    )
    parser.add_argument("--all", action="store_true", help="重置所有已分析的文章")
    parser.add_argument(
        "--shallow-only", action="store_true", help="只重置浅层分析的文章"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("🔧 重置文章分析状态")
    print("=" * 60)

    if args.shallow_only:
        reset_shallow_analysis()
    else:
        reset_analysis_status(hours=args.hours, reset_all=args.all)

    print("=" * 60)
    print("✅ 重置完成！现在可以重新运行 analyzer.py 了")
    print("=" * 60)
