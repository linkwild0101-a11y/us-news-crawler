-- US-Monitor 热点分析系统数据库表结构
-- 创建时间: 2025-02-17
-- 说明: 存储热点分析结果的数据库表

-- ============================================
-- 1. 分析聚类表 (analysis_clusters)
-- 存储Jaccard聚类结果
-- ============================================
CREATE TABLE IF NOT EXISTS analysis_clusters (
    id SERIAL PRIMARY KEY,
    cluster_key VARCHAR(64) UNIQUE NOT NULL,  -- 聚类内容哈希值，用于去重
    category VARCHAR(50) NOT NULL,            -- 分类: military/politics/economy
    primary_title TEXT NOT NULL,              -- 主要文章标题（英文）
    primary_link TEXT,                        -- 主要文章链接（英文原文）
    summary TEXT NOT NULL,                    -- 中文摘要（LLM生成）
    summary_en TEXT,                          -- 英文摘要（可选）
    article_count INTEGER DEFAULT 0,          -- 聚类中的文章数量
    key_entities JSONB DEFAULT '[]'::jsonb,   -- 关键实体列表（JSON数组）
    impact TEXT,                              -- 影响分析
    trend TEXT,                               -- 趋势判断
    data_sources JSONB DEFAULT '{}'::jsonb,   -- 关联的数据源（FRED/GDELT等）
    confidence FLOAT DEFAULT 0.0,             -- 置信度评分(0-1)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 聚类表索引
CREATE INDEX IF NOT EXISTS idx_clusters_category ON analysis_clusters(category);
CREATE INDEX IF NOT EXISTS idx_clusters_cluster_key ON analysis_clusters(cluster_key);
CREATE INDEX IF NOT EXISTS idx_clusters_created_at ON analysis_clusters(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_clusters_confidence ON analysis_clusters(confidence DESC);

-- ============================================
-- 2. 分析信号表 (analysis_signals)
-- 存储检测到的信号
-- ============================================
CREATE TABLE IF NOT EXISTS analysis_signals (
    id SERIAL PRIMARY KEY,
    signal_type VARCHAR(50) NOT NULL,         -- 信号类型: velocity_spike/convergence/triangulation/hotspot_escalation/economic_indicator_alert/natural_disaster_signal/geopolitical_intensity
    signal_key VARCHAR(128) UNIQUE NOT NULL,  -- 信号去重键
    cluster_id INTEGER REFERENCES analysis_clusters(id) ON DELETE SET NULL,
    category VARCHAR(50) NOT NULL,            -- 分类
    confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    description TEXT NOT NULL,                -- 信号描述（中文）
    description_en TEXT,                      -- 信号描述（英文）
    rationale TEXT,                           -- 判断理由
    actionable_insight TEXT,                  -- 可执行建议
    data_source VARCHAR(50),                  -- 数据来源: direct/worker/railway/FRED/GDELT/USGS/WorldBank
    related_entities JSONB DEFAULT '[]'::jsonb, -- 相关实体
    expires_at TIMESTAMP WITH TIME ZONE,      -- 信号过期时间（冷却期）
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 信号表索引
CREATE INDEX IF NOT EXISTS idx_signals_type ON analysis_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_signals_category ON analysis_signals(category);
CREATE INDEX IF NOT EXISTS idx_signals_created_at ON analysis_signals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_expires ON analysis_signals(expires_at);
CREATE INDEX IF NOT EXISTS idx_signals_cluster ON analysis_signals(cluster_id);

-- ============================================
-- 3. 文章-聚类关联表 (article_analyses)
-- 多对多关联表
-- ============================================
CREATE TABLE IF NOT EXISTS article_analyses (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL,              -- 引用articles表的id（不创建外键约束，避免阻塞）
    cluster_id INTEGER REFERENCES analysis_clusters(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(article_id, cluster_id)            -- 避免重复关联
);

-- 关联表索引
CREATE INDEX IF NOT EXISTS idx_aa_article ON article_analyses(article_id);
CREATE INDEX IF NOT EXISTS idx_aa_cluster ON article_analyses(cluster_id);

-- ============================================
-- 4. 为articles表添加analyzed_at列
-- 用于增量处理
-- ============================================
ALTER TABLE articles 
ADD COLUMN IF NOT EXISTS analyzed_at TIMESTAMP WITH TIME ZONE;

-- articles表索引
CREATE INDEX IF NOT EXISTS idx_articles_analyzed_at ON articles(analyzed_at) 
WHERE analyzed_at IS NULL;

-- ============================================
-- 5. 创建更新触发器函数
-- 自动更新updated_at字段
-- ============================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 为analysis_clusters创建触发器
DROP TRIGGER IF EXISTS update_clusters_updated_at ON analysis_clusters;
CREATE TRIGGER update_clusters_updated_at
    BEFORE UPDATE ON analysis_clusters
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- 注释
-- ============================================
COMMENT ON TABLE analysis_clusters IS '热点分析聚类结果表';
COMMENT ON TABLE analysis_signals IS '热点检测信号表';
COMMENT ON TABLE article_analyses IS '文章与聚类的关联表';
COMMENT ON COLUMN analysis_clusters.summary IS 'LLM生成的中文摘要';
COMMENT ON COLUMN analysis_clusters.primary_link IS '英文原文链接，用于溯源';
COMMENT ON COLUMN articles.analyzed_at IS '文章分析时间戳，用于增量处理';
