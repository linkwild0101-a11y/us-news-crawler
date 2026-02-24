-- StockOps P1: ticker profile foundation tables
-- 日期: 2026-02-24

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

ALTER TABLE IF EXISTS stock_ticker_profiles_v1
    ADD COLUMN IF NOT EXISTS exchange VARCHAR(24) NOT NULL DEFAULT '';
ALTER TABLE IF EXISTS stock_ticker_profiles_v1
    ADD COLUMN IF NOT EXISTS summary_source VARCHAR(16) NOT NULL DEFAULT 'template';
ALTER TABLE IF EXISTS stock_ticker_profiles_v1
    ADD COLUMN IF NOT EXISTS quality_score FLOAT NOT NULL DEFAULT 0.5
        CHECK (quality_score >= 0 AND quality_score <= 1);
ALTER TABLE IF EXISTS stock_ticker_profiles_v1
    ADD COLUMN IF NOT EXISTS last_llm_at TIMESTAMP WITH TIME ZONE NULL;

CREATE INDEX IF NOT EXISTS idx_stock_ticker_profiles_v1_quality
    ON stock_ticker_profiles_v1(quality_score DESC, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_stock_ticker_profiles_v1_exchange
    ON stock_ticker_profiles_v1(exchange, asset_type);

CREATE TABLE IF NOT EXISTS stock_universe_members_v1 (
    id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(16) NOT NULL,
    source_type VARCHAR(32) NOT NULL
        CHECK (source_type IN ('sp500', 'nasdaq100', 'portfolio', 'watchlist', 'recent_signal')),
    source_ref VARCHAR(128) NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    run_id VARCHAR(64) NOT NULL DEFAULT '',
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (ticker, source_type)
);

DROP TRIGGER IF EXISTS update_stock_universe_members_v1_updated_at ON stock_universe_members_v1;
CREATE TRIGGER update_stock_universe_members_v1_updated_at
    BEFORE UPDATE ON stock_universe_members_v1
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX IF NOT EXISTS idx_stock_universe_members_v1_source
    ON stock_universe_members_v1(source_type, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_stock_universe_members_v1_ticker
    ON stock_universe_members_v1(ticker, updated_at DESC);

CREATE TABLE IF NOT EXISTS stock_ticker_profile_enrich_queue_v1 (
    id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(16) NOT NULL UNIQUE,
    reason VARCHAR(32) NOT NULL
        CHECK (reason IN ('missing_summary', 'low_quality', 'new_symbol')),
    status VARCHAR(16) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'done', 'failed')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    next_retry_at TIMESTAMP WITH TIME ZONE NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    run_id VARCHAR(64) NOT NULL DEFAULT '',
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_stock_ticker_profile_enrich_queue_v1_updated_at
    ON stock_ticker_profile_enrich_queue_v1;
CREATE TRIGGER update_stock_ticker_profile_enrich_queue_v1_updated_at
    BEFORE UPDATE ON stock_ticker_profile_enrich_queue_v1
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX IF NOT EXISTS idx_stock_ticker_profile_enrich_queue_v1_status
    ON stock_ticker_profile_enrich_queue_v1(status, next_retry_at, updated_at DESC);

CREATE TABLE IF NOT EXISTS stock_ticker_profile_sync_runs_v1 (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL UNIQUE,
    stage VARCHAR(32) NOT NULL DEFAULT 'sync'
        CHECK (stage IN ('sync', 'enrich')),
    status VARCHAR(16) NOT NULL DEFAULT 'success'
        CHECK (status IN ('running', 'success', 'failed')),
    input_count INTEGER NOT NULL DEFAULT 0,
    updated_count INTEGER NOT NULL DEFAULT 0,
    queued_count INTEGER NOT NULL DEFAULT 0,
    llm_success_count INTEGER NOT NULL DEFAULT 0,
    llm_failed_count INTEGER NOT NULL DEFAULT 0,
    duration_sec FLOAT NOT NULL DEFAULT 0,
    error_summary TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stock_ticker_profile_sync_runs_v1_stage
    ON stock_ticker_profile_sync_runs_v1(stage, created_at DESC);

ALTER TABLE stock_universe_members_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_ticker_profile_enrich_queue_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_ticker_profile_sync_runs_v1 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS stock_universe_members_v1_public_read ON stock_universe_members_v1;
DROP POLICY IF EXISTS stock_ticker_profile_enrich_queue_v1_public_read
    ON stock_ticker_profile_enrich_queue_v1;
DROP POLICY IF EXISTS stock_ticker_profile_sync_runs_v1_public_read
    ON stock_ticker_profile_sync_runs_v1;

CREATE POLICY stock_universe_members_v1_public_read
    ON stock_universe_members_v1
    FOR SELECT
    TO anon, authenticated
    USING (true);
CREATE POLICY stock_ticker_profile_enrich_queue_v1_public_read
    ON stock_ticker_profile_enrich_queue_v1
    FOR SELECT
    TO anon, authenticated
    USING (true);
CREATE POLICY stock_ticker_profile_sync_runs_v1_public_read
    ON stock_ticker_profile_sync_runs_v1
    FOR SELECT
    TO anon, authenticated
    USING (true);

COMMENT ON TABLE stock_universe_members_v1 IS 'Ticker 覆盖池成员来源表';
COMMENT ON TABLE stock_ticker_profile_enrich_queue_v1 IS 'Ticker 简介补全队列';
COMMENT ON TABLE stock_ticker_profile_sync_runs_v1 IS 'Ticker Profile 同步/补全运行日志';
