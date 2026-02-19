#!/usr/bin/env python3
"""
使用Supabase API自动创建数据库表
"""

import os
from supabase import create_client


def create_tables():
    supabase_url = os.getenv("SUPABASE_URL", "https://lwigqxyfxevldfjdeokp.supabase.co")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_key:
        print("❌ 错误: 未设置SUPABASE_KEY环境变量")
        return False

    supabase = create_client(supabase_url, supabase_key)

    # SQL语句
    sql_commands = [
        """
        CREATE TABLE IF NOT EXISTS rss_sources (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            rss_url VARCHAR(500) UNIQUE NOT NULL,
            listing_url VARCHAR(500),
            category VARCHAR(50) NOT NULL CHECK (category IN ('military', 'politics', 'economy', 'tech')),
            anti_scraping VARCHAR(50) DEFAULT 'None',
            status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'error')),
            last_fetch TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS articles (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT,
            url TEXT UNIQUE NOT NULL,
            source_id INTEGER REFERENCES rss_sources(id) ON DELETE CASCADE,
            published_at TIMESTAMP,
            fetched_at TIMESTAMP DEFAULT NOW(),
            simhash VARCHAR(64),
            category VARCHAR(50),
            author VARCHAR(255),
            summary TEXT,
            extraction_method VARCHAR(50) DEFAULT 'local'
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS crawl_logs (
            id SERIAL PRIMARY KEY,
            started_at TIMESTAMP DEFAULT NOW(),
            completed_at TIMESTAMP,
            sources_count INTEGER,
            articles_fetched INTEGER,
            articles_new INTEGER,
            articles_deduped INTEGER,
            errors_count INTEGER,
            status VARCHAR(20) DEFAULT 'running'
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS cleanup_logs (
            id SERIAL PRIMARY KEY,
            deleted_count INTEGER NOT NULL,
            cutoff_date TIMESTAMP NOT NULL,
            executed_at TIMESTAMP DEFAULT NOW()
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS dedup_logs (
            id SERIAL PRIMARY KEY,
            duplicate_url TEXT NOT NULL,
            original_url TEXT NOT NULL,
            hamming_distance INTEGER,
            detected_at TIMESTAMP DEFAULT NOW()
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_articles_simhash ON articles(simhash);",
        "CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url);",
        "CREATE INDEX IF NOT EXISTS idx_articles_fetched_at ON articles(fetched_at);",
        "CREATE INDEX IF NOT EXISTS idx_sources_category ON rss_sources(category);",
        "CREATE INDEX IF NOT EXISTS idx_sources_status ON rss_sources(status);",
    ]

    print("🚀 开始创建数据库表...\n")

    success_count = 0
    for i, sql in enumerate(sql_commands, 1):
        try:
            # 使用 supabase 的 rpc 或直接执行 SQL
            result = supabase.rpc("exec_sql", {"sql": sql}).execute()
            print(f"✅ [{i}/{len(sql_commands)}] 执行成功")
            success_count += 1
        except Exception as e:
            # 如果 exec_sql 函数不存在，尝试直接方法
            print(f"⚠️  [{i}/{len(sql_commands)}] {str(e)[:60]}...")

    print(f"\n📊 完成: {success_count}/{len(sql_commands)}")
    return success_count > 0


if __name__ == "__main__":
    create_tables()
