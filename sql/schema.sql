-- Supabase Database Schema for RSS Crawler
-- Run this in Supabase SQL Editor

-- RSS源表
CREATE TABLE IF NOT EXISTS rss_sources (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    rss_url VARCHAR(500) UNIQUE NOT NULL,
    listing_url VARCHAR(500),
    category VARCHAR(50) NOT NULL CHECK (category IN ('military', 'politics', 'economy')),
    anti_scraping VARCHAR(50) DEFAULT 'None',
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'error')),
    last_fetch TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 文章表
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

-- 爬取日志表
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

-- 清理日志表
CREATE TABLE IF NOT EXISTS cleanup_logs (
    id SERIAL PRIMARY KEY,
    deleted_count INTEGER NOT NULL,
    cutoff_date TIMESTAMP NOT NULL,
    executed_at TIMESTAMP DEFAULT NOW()
);

-- 去重日志表（记录被SimHash判定为重复的文章）
CREATE TABLE IF NOT EXISTS dedup_logs (
    id SERIAL PRIMARY KEY,
    duplicate_url TEXT NOT NULL,
    original_url TEXT NOT NULL,
    hamming_distance INTEGER,
    detected_at TIMESTAMP DEFAULT NOW()
);

-- 索引优化
CREATE INDEX IF NOT EXISTS idx_articles_simhash ON articles(simhash);
CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url);
CREATE INDEX IF NOT EXISTS idx_articles_fetched_at ON articles(fetched_at);
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_articles_source_id ON articles(source_id);
CREATE INDEX IF NOT EXISTS idx_sources_category ON rss_sources(category);
CREATE INDEX IF NOT EXISTS idx_sources_status ON rss_sources(status);
CREATE INDEX IF NOT EXISTS idx_crawl_logs_started_at ON crawl_logs(started_at);

-- 启用RLS (Row Level Security)
ALTER TABLE rss_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE articles ENABLE ROW LEVEL SECURITY;
ALTER TABLE crawl_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE cleanup_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE dedup_logs ENABLE ROW LEVEL SECURITY;

-- 创建策略（仅服务账号可访问）
-- 注意：PostgreSQL不支持CREATE POLICY IF NOT EXISTS
-- 如果策略已存在，请先删除：DROP POLICY "Service only" ON table_name;
CREATE POLICY "Service only" ON rss_sources FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service only" ON articles FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service only" ON crawl_logs FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service only" ON cleanup_logs FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service only" ON dedup_logs FOR ALL USING (auth.role() = 'service_role');
