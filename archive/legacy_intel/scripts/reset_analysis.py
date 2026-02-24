#!/usr/bin/env python3
"""
重置文章分析状态
用于重新分析之前失败的文章
"""

import os
import sys
from datetime import datetime, timedelta
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client


def _fetch_all_rows(
    supabase, table_name: str, columns: str, apply_filters=None, page_size: int = 1000
) -> List[dict]:
    """分页读取全部行，避免 PostgREST 默认分页导致遗漏"""
    all_rows: List[dict] = []
    offset = 0

    while True:
        query = (
            supabase.table(table_name)
            .select(columns)
            .range(offset, offset + page_size - 1)
        )
        if apply_filters:
            query = apply_filters(query)
        result = query.execute()
        rows = result.data or []
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size

    return all_rows


def _reset_articles_by_ids(supabase, article_ids: List[int], batch_size: int = 200) -> int:
    """按批次重置文章 analyzed_at 字段，避免单条更新过慢"""
    if not article_ids:
        return 0

    reset_count = 0
    for i in range(0, len(article_ids), batch_size):
        batch_ids = article_ids[i : i + batch_size]
        supabase.table("articles").update({"analyzed_at": None}).in_("id", batch_ids).execute()
        reset_count += len(batch_ids)

    return reset_count


def _cleanup_entities_for_clusters(supabase, cluster_ids: List[int]) -> int:
    """清理指定聚类关联的实体，并删除失去关联的孤立实体"""
    if not cluster_ids:
        return 0

    candidate_entity_ids = set()
    batch_size = 200
    for i in range(0, len(cluster_ids), batch_size):
        batch_cluster_ids = cluster_ids[i : i + batch_size]

        relations = (
            supabase.table("entity_cluster_relations")
            .select("entity_id")
            .in_("cluster_id", batch_cluster_ids)
            .execute()
        )
        for row in relations.data or []:
            candidate_entity_ids.add(row["entity_id"])

        # 先删聚类关联
        supabase.table("entity_cluster_relations").delete().in_(
            "cluster_id", batch_cluster_ids
        ).execute()

    deleted_entities = 0
    for entity_id in candidate_entity_ids:
        left_relations = (
            supabase.table("entity_cluster_relations")
            .select("id")
            .eq("entity_id", entity_id)
            .limit(1)
            .execute()
        )
        if not left_relations.data:
            supabase.table("entities").delete().eq("id", entity_id).execute()
            deleted_entities += 1

    return deleted_entities


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
        analyzed_count_result = (
            supabase.table("articles")
            .select("id", count="exact")
            .not_.is_("analyzed_at", "null")
            .limit(1)
            .execute()
        )
        reset_count = analyzed_count_result.count or 0
        supabase.table("articles").update({"analyzed_at": None}).not_.is_(
            "analyzed_at", "null"
        ).execute()
        print(f"✅ 已重置 {reset_count} 篇文章")

        # 删除所有分析聚类
        print("⚠️  删除所有分析聚类...")
        supabase.table("analysis_clusters").delete().neq("id", 0).execute()
        print("✅ 已删除所有聚类")

        # 删除所有信号
        print("⚠️  删除所有信号...")
        supabase.table("analysis_signals").delete().neq("id", 0).execute()
        print("✅ 已删除所有信号")

        # 删除所有实体关联
        print("⚠️  删除所有实体关联...")
        supabase.table("entity_cluster_relations").delete().neq("id", 0).execute()
        print("✅ 已删除所有实体关联")

        # 删除所有实体档案
        print("⚠️  删除所有实体档案...")
        supabase.table("entities").delete().neq("id", 0).execute()
        print("✅ 已删除所有实体档案")

    else:
        # 只重置最近 N 小时的文章
        cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()

        print(f"📝 重置最近 {hours} 小时内分析的文章...")

        # 统计这些文章
        result = (
            supabase.table("articles")
            .select("id", count="exact")
            .gte("analyzed_at", cutoff_time)
            .limit(1)
            .execute()
        )

        reset_count = result.count or 0

        if not reset_count:
            print("✅ 没有找到需要重置的文章")
            return

        print(f"📊 找到 {reset_count} 篇文章需要重置")

        # 重置文章状态
        supabase.table("articles").update({"analyzed_at": None}).gte(
            "analyzed_at", cutoff_time
        ).execute()
        print(f"✅ 已重置 {reset_count} 篇文章的分析状态")

        # 删除相关的聚类
        print("🗑️  删除相关的聚类...")
        clusters = _fetch_all_rows(
            supabase,
            "analysis_clusters",
            "id",
            apply_filters=lambda q: q.gte("created_at", cutoff_time),
        )
        cluster_ids = [c["id"] for c in clusters]

        # 删除相关信号
        supabase.table("analysis_signals").delete().gte("created_at", cutoff_time).execute()
        print("✅ 已删除时间窗口内的信号")

        # 删除关联实体（仅清理无关联的孤立实体）
        deleted_entities = _cleanup_entities_for_clusters(supabase, cluster_ids)
        if cluster_ids:
            print(f"✅ 已清理 {len(cluster_ids)} 个聚类关联，并删除 {deleted_entities} 个孤立实体")

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
    clusters = _fetch_all_rows(
        supabase,
        "analysis_clusters",
        "id",
        apply_filters=lambda q: q.eq("analysis_depth", "shallow"),
    )

    if not clusters:
        print("✅ 没有浅层分析的聚类")
        return

    print(f"📊 找到 {len(clusters)} 个浅层分析聚类")

    # 获取关联的文章ID
    cluster_ids = [c["id"] for c in clusters]
    article_ids = set()
    batch_size = 200
    for i in range(0, len(cluster_ids), batch_size):
        batch_cluster_ids = cluster_ids[i : i + batch_size]
        relations = (
            supabase.table("article_analyses")
            .select("article_id")
            .in_("cluster_id", batch_cluster_ids)
            .execute()
        )
        for row in relations.data or []:
            article_ids.add(row["article_id"])

    print(f"📊 涉及 {len(article_ids)} 篇文章")

    # 重置文章状态
    reset_count = _reset_articles_by_ids(supabase, list(article_ids))
    print(f"✅ 已重置 {reset_count} 篇文章")

    # 清理实体关联并删除孤立实体
    deleted_entities = _cleanup_entities_for_clusters(supabase, cluster_ids)
    print(f"✅ 已删除 {deleted_entities} 个孤立实体")

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
