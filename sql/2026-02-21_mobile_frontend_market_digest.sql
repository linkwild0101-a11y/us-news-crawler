-- Mobile frontend market digest tables
-- 日期: 2026-02-21

CREATE TABLE IF NOT EXISTS market_snapshot_daily (
    snapshot_date DATE PRIMARY KEY,
    spy NUMERIC,
    qqq NUMERIC,
    dia NUMERIC,
    vix NUMERIC,
    us10y NUMERIC,
    dxy NUMERIC,
    risk_level VARCHAR(4) DEFAULT 'L1',
    daily_brief TEXT DEFAULT '',
    source_payload JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ticker_signal_digest (
    ticker VARCHAR(16) PRIMARY KEY,
    signal_count_24h INTEGER DEFAULT 0,
    related_cluster_count_24h INTEGER DEFAULT 0,
    risk_level VARCHAR(4) DEFAULT 'L1',
    top_sentinel_levels TEXT[] DEFAULT '{}',
    top_clusters JSONB DEFAULT '[]'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_market_snapshot_date ON market_snapshot_daily(snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_market_snapshot_risk ON market_snapshot_daily(risk_level);

CREATE INDEX IF NOT EXISTS idx_ticker_digest_signal_count ON ticker_signal_digest(signal_count_24h DESC);
CREATE INDEX IF NOT EXISTS idx_ticker_digest_risk ON ticker_signal_digest(risk_level);

DROP TRIGGER IF EXISTS update_market_snapshot_updated_at ON market_snapshot_daily;
CREATE TRIGGER update_market_snapshot_updated_at
    BEFORE UPDATE ON market_snapshot_daily
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE market_snapshot_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE ticker_signal_digest ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS market_snapshot_public_read ON market_snapshot_daily;
CREATE POLICY market_snapshot_public_read
    ON market_snapshot_daily
    FOR SELECT
    TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS ticker_signal_digest_public_read ON ticker_signal_digest;
CREATE POLICY ticker_signal_digest_public_read
    ON ticker_signal_digest
    FOR SELECT
    TO anon, authenticated
    USING (true);

COMMENT ON TABLE market_snapshot_daily IS '移动端市场总览聚合快照';
COMMENT ON TABLE ticker_signal_digest IS '移动端 ticker 风险与信号摘要';
