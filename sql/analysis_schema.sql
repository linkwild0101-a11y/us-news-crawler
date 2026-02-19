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
    category VARCHAR(50) NOT NULL,            -- 分类: military/politics/economy/tech
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
    -- 分层分析新增字段
    analysis_depth VARCHAR(20) DEFAULT 'full', -- 分析深度: full(完整) / shallow(浅层)
    is_hot BOOLEAN DEFAULT FALSE,              -- 是否为热点聚类
    full_analysis_triggered BOOLEAN DEFAULT FALSE, -- 是否已触发完整分析（用于按需分析）
    processing_time FLOAT DEFAULT 0.0,         -- 处理耗时（秒）
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
-- 6. 新增分层分析相关索引
-- ============================================
CREATE INDEX IF NOT EXISTS idx_clusters_analysis_depth ON analysis_clusters(analysis_depth);
CREATE INDEX IF NOT EXISTS idx_clusters_is_hot ON analysis_clusters(is_hot) WHERE is_hot = TRUE;

-- ============================================
-- 7. 实体表 (entities)
-- 存储提取的关键实体用于热度追踪和档案
-- ============================================
CREATE TABLE IF NOT EXISTS entities (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,               -- 实体名称
    name_en VARCHAR(255),                     -- 英文名称
    entity_type VARCHAR(50) NOT NULL,         -- 实体类型: person/organization/location/event/concept
    category VARCHAR(50),                     -- 所属分类: military/politics/economy/tech
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),  -- 首次出现时间
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),   -- 最后出现时间
    mention_count_24h INTEGER DEFAULT 0,      -- 24小时内提及次数
    mention_count_7d INTEGER DEFAULT 0,       -- 7天内提及次数
    mention_count_total INTEGER DEFAULT 0,    -- 总提及次数
    related_clusters JSONB DEFAULT '[]'::jsonb,  -- 相关聚类ID列表
    related_entities JSONB DEFAULT '[]'::jsonb,  -- 相关实体列表（关联图谱）
    sentiment_score FLOAT DEFAULT 0.0,        -- 情感评分(-1到1)
    trend_direction VARCHAR(20) DEFAULT 'stable',  -- 趋势: rising/falling/stable
    metadata JSONB DEFAULT '{}'::jsonb,       -- 扩展元数据
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(name, entity_type)                 -- 同类型实体去重
);

-- 实体表索引
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_category ON entities(category);
CREATE INDEX IF NOT EXISTS idx_entities_last_seen ON entities(last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_entities_mention_count ON entities(mention_count_24h DESC);

-- 为entities表创建触发器
DROP TRIGGER IF EXISTS update_entities_updated_at ON entities;
CREATE TRIGGER update_entities_updated_at
    BEFORE UPDATE ON entities
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- 8. 实体-聚类关联表 (entity_cluster_relations)
-- 多对多关联表
-- ============================================
CREATE TABLE IF NOT EXISTS entity_cluster_relations (
    id SERIAL PRIMARY KEY,
    entity_id INTEGER REFERENCES entities(id) ON DELETE CASCADE,
    cluster_id INTEGER REFERENCES analysis_clusters(id) ON DELETE CASCADE,
    mention_count INTEGER DEFAULT 1,          -- 在该聚类中提及次数
    context TEXT,                             -- 提及上下文
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(entity_id, cluster_id)
);

-- 关联表索引
CREATE INDEX IF NOT EXISTS idx_ecr_entity ON entity_cluster_relations(entity_id);
CREATE INDEX IF NOT EXISTS idx_ecr_cluster ON entity_cluster_relations(cluster_id);

-- ============================================
-- 注释
-- ============================================
COMMENT ON TABLE analysis_clusters IS '热点分析聚类结果表';
COMMENT ON TABLE analysis_signals IS '热点检测信号表';
COMMENT ON TABLE article_analyses IS '文章与聚类的关联表';
COMMENT ON TABLE entities IS '关键实体表，用于热度追踪和关联分析';
COMMENT ON TABLE entity_cluster_relations IS '实体与聚类的关联表';
COMMENT ON COLUMN analysis_clusters.summary IS 'LLM生成的中文摘要';
COMMENT ON COLUMN analysis_clusters.primary_link IS '英文原文链接，用于溯源';
COMMENT ON COLUMN articles.analyzed_at IS '文章分析时间戳，用于增量处理';
COMMENT ON COLUMN analysis_clusters.analysis_depth IS '分析深度: full(完整分析) / shallow(浅层翻译)';
COMMENT ON COLUMN analysis_clusters.is_hot IS '是否为热点聚类(文章数>=3)';
COMMENT ON COLUMN analysis_clusters.full_analysis_triggered IS '是否已触发完整分析（用于按需分析）';
