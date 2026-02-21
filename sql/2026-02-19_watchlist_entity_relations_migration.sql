-- Watchlist + Entity Relations migration
-- 日期: 2026-02-19

-- ============================================
-- 1) analysis_signals 扩展（哨兵计划）
-- ============================================
ALTER TABLE analysis_signals
ADD COLUMN IF NOT EXISTS sentinel_id VARCHAR(64),
ADD COLUMN IF NOT EXISTS alert_level VARCHAR(4),
ADD COLUMN IF NOT EXISTS risk_score FLOAT,
ADD COLUMN IF NOT EXISTS trigger_reasons JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS evidence_links JSONB DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_signals_alert_level ON analysis_signals(alert_level);
CREATE INDEX IF NOT EXISTS idx_signals_sentinel_id ON analysis_signals(sentinel_id);
CREATE INDEX IF NOT EXISTS idx_signals_risk_score ON analysis_signals(risk_score DESC);

-- ============================================
-- 2) 实体关系表（实体关系计划）
-- ============================================
CREATE TABLE IF NOT EXISTS entity_relations (
    id SERIAL PRIMARY KEY,
    entity1_id INTEGER REFERENCES entities(id) ON DELETE CASCADE,
    entity2_id INTEGER REFERENCES entities(id) ON DELETE CASCADE,
    relation_text TEXT NOT NULL,
    confidence FLOAT DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    source_article_ids INTEGER[] DEFAULT '{}',
    source_count INTEGER DEFAULT 1,
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(entity1_id, entity2_id, relation_text)
);

CREATE INDEX IF NOT EXISTS idx_entity_relations_entity1 ON entity_relations(entity1_id);
CREATE INDEX IF NOT EXISTS idx_entity_relations_entity2 ON entity_relations(entity2_id);
CREATE INDEX IF NOT EXISTS idx_entity_relations_conf ON entity_relations(confidence DESC);
CREATE INDEX IF NOT EXISTS idx_entity_relations_last_seen ON entity_relations(last_seen DESC);

DROP TRIGGER IF EXISTS update_entity_relations_updated_at ON entity_relations;
CREATE TRIGGER update_entity_relations_updated_at
    BEFORE UPDATE ON entity_relations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- 3) 关系证据表
-- ============================================
CREATE TABLE IF NOT EXISTS relation_evidence (
    id SERIAL PRIMARY KEY,
    relation_id INTEGER REFERENCES entity_relations(id) ON DELETE CASCADE,
    article_id INTEGER NOT NULL,
    extracted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(relation_id, article_id)
);

CREATE INDEX IF NOT EXISTS idx_relation_evidence_relation ON relation_evidence(relation_id);
CREATE INDEX IF NOT EXISTS idx_relation_evidence_article ON relation_evidence(article_id);

COMMENT ON TABLE entity_relations IS '实体关系表，用于关系图谱构建';
COMMENT ON TABLE relation_evidence IS '实体关系证据表，记录关系来源文章';
