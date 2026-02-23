-- Stock evidence-first + transmission schema (P0)
-- 日期: 2026-02-23

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS 66113
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
66113 language 'plpgsql';

CREATE TABLE IF NOT EXISTS stock_evidence_v2 (
    id BIGSERIAL PRIMARY KEY,
    opportunity_id BIGINT REFERENCES stock_opportunities_v2(id) ON DELETE CASCADE,
    ticker VARCHAR(16) NOT NULL,
    source_type VARCHAR(32) NOT NULL DEFAULT 'article',
    source_ref VARCHAR(128) NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    source_name VARCHAR(128) NOT NULL DEFAULT '',
    published_at TIMESTAMP WITH TIME ZONE,
    quote_snippet TEXT NOT NULL,
    numeric_facts JSONB NOT NULL DEFAULT '[]'::jsonb,
    entity_tags TEXT[] NOT NULL DEFAULT '{}',
    confidence FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    snippet_hash VARCHAR(32) NOT NULL DEFAULT '',
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    run_id VARCHAR(96) NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(opportunity_id, snippet_hash)
);

DROP TRIGGER IF EXISTS update_stock_evidence_v2_updated_at ON stock_evidence_v2;
CREATE TRIGGER update_stock_evidence_v2_updated_at
    BEFORE UPDATE ON stock_evidence_v2
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS stock_transmission_paths_v2 (
    id BIGSERIAL PRIMARY KEY,
    opportunity_id BIGINT REFERENCES stock_opportunities_v2(id) ON DELETE CASCADE,
    path_key VARCHAR(160) UNIQUE NOT NULL,
    ticker VARCHAR(16) NOT NULL,
    macro_factor VARCHAR(64) NOT NULL,
    industry VARCHAR(64) NOT NULL,
    direction VARCHAR(16) NOT NULL DEFAULT 'NEUTRAL'
        CHECK (direction IN ('LONG', 'SHORT', 'NEUTRAL')),
    strength FLOAT NOT NULL DEFAULT 0.5 CHECK (strength >= 0 AND strength <= 1),
    reason TEXT NOT NULL DEFAULT '',
    evidence_ids BIGINT[] NOT NULL DEFAULT '{}',
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    run_id VARCHAR(96) NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_stock_transmission_paths_v2_updated_at ON stock_transmission_paths_v2;
CREATE TRIGGER update_stock_transmission_paths_v2_updated_at
    BEFORE UPDATE ON stock_transmission_paths_v2
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE IF EXISTS stock_opportunities_v2
    ADD COLUMN IF NOT EXISTS evidence_ids BIGINT[] NOT NULL DEFAULT '{}';
ALTER TABLE IF EXISTS stock_opportunities_v2
    ADD COLUMN IF NOT EXISTS path_ids BIGINT[] NOT NULL DEFAULT '{}';
ALTER TABLE IF EXISTS stock_opportunities_v2
    ADD COLUMN IF NOT EXISTS uncertainty_flags JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE IF EXISTS stock_opportunities_v2
    ADD COLUMN IF NOT EXISTS counter_view TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_stock_evidence_v2_opp
    ON stock_evidence_v2(opportunity_id, is_active, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_stock_evidence_v2_ticker
    ON stock_evidence_v2(ticker, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_stock_evidence_v2_run_id
    ON stock_evidence_v2(run_id);

CREATE INDEX IF NOT EXISTS idx_stock_transmission_paths_v2_opp
    ON stock_transmission_paths_v2(opportunity_id, is_active, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_stock_transmission_paths_v2_ticker
    ON stock_transmission_paths_v2(ticker, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_stock_transmission_paths_v2_macro
    ON stock_transmission_paths_v2(macro_factor, industry);
CREATE INDEX IF NOT EXISTS idx_stock_transmission_paths_v2_run_id
    ON stock_transmission_paths_v2(run_id);

ALTER TABLE stock_evidence_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_transmission_paths_v2 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS stock_evidence_v2_public_read ON stock_evidence_v2;
CREATE POLICY stock_evidence_v2_public_read
    ON stock_evidence_v2
    FOR SELECT
    TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS stock_transmission_paths_v2_public_read ON stock_transmission_paths_v2;
CREATE POLICY stock_transmission_paths_v2_public_read
    ON stock_transmission_paths_v2
    FOR SELECT
    TO anon, authenticated
    USING (true);

COMMENT ON TABLE stock_evidence_v2 IS 'Stock V2 机会证据表（原文关键段落）';
COMMENT ON TABLE stock_transmission_paths_v2 IS 'Stock V2 宏观-行业-个股传导路径';
COMMENT ON COLUMN stock_evidence_v2.numeric_facts IS '结构化数字事实（如增速、利率、EPS）';
COMMENT ON COLUMN stock_transmission_paths_v2.strength IS '链路强度，0~1';
COMMENT ON COLUMN stock_opportunities_v2.evidence_ids IS '关联证据ID集合';
COMMENT ON COLUMN stock_opportunities_v2.path_ids IS '关联传导链ID集合';
COMMENT ON COLUMN stock_opportunities_v2.uncertainty_flags IS '不确定性标签';
COMMENT ON COLUMN stock_opportunities_v2.counter_view IS '反方观点摘要';
