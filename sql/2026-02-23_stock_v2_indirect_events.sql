-- Stock V2 indirect impact pool (secondary observation layer)
-- 日期: 2026-02-23

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TABLE IF NOT EXISTS stock_indirect_events_v2 (
    id BIGSERIAL PRIMARY KEY,
    event_key VARCHAR(128) UNIQUE NOT NULL,
    article_id BIGINT,
    source_ref VARCHAR(220) NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    source_name VARCHAR(128) NOT NULL DEFAULT 'unknown',
    title TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    theme VARCHAR(32) NOT NULL,
    impact_scope VARCHAR(16) NOT NULL DEFAULT 'sector'
        CHECK (impact_scope IN ('index', 'sector', 'ticker')),
    candidate_tickers TEXT[] NOT NULL DEFAULT '{}',
    relevance_score FLOAT NOT NULL DEFAULT 0 CHECK (relevance_score >= 0 AND relevance_score <= 100),
    confidence FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    promotion_status VARCHAR(16) NOT NULL DEFAULT 'pending'
        CHECK (promotion_status IN ('pending', 'promoted', 'rejected')),
    promotion_reason TEXT NOT NULL DEFAULT '',
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    published_at TIMESTAMP WITH TIME ZONE,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    run_id VARCHAR(64) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_stock_indirect_events_v2_updated_at ON stock_indirect_events_v2;
CREATE TRIGGER update_stock_indirect_events_v2_updated_at
    BEFORE UPDATE ON stock_indirect_events_v2
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX IF NOT EXISTS idx_stock_indirect_events_v2_active_asof
    ON stock_indirect_events_v2(is_active, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_stock_indirect_events_v2_theme
    ON stock_indirect_events_v2(theme, promotion_status, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_stock_indirect_events_v2_run_id
    ON stock_indirect_events_v2(run_id);
CREATE INDEX IF NOT EXISTS idx_stock_indirect_events_v2_score
    ON stock_indirect_events_v2(relevance_score DESC, confidence DESC);

ALTER TABLE stock_indirect_events_v2 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS stock_indirect_events_v2_public_read ON stock_indirect_events_v2;
CREATE POLICY stock_indirect_events_v2_public_read
    ON stock_indirect_events_v2
    FOR SELECT
    TO anon, authenticated
    USING (true);

COMMENT ON TABLE stock_indirect_events_v2 IS 'Stock V2 二级关联池（间接影响观察层）';
