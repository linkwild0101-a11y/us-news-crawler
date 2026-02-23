-- Stock X source tables
-- 日期: 2026-02-23

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TABLE IF NOT EXISTS stock_x_accounts (
    id BIGSERIAL PRIMARY KEY,
    handle VARCHAR(64) NOT NULL UNIQUE,
    category VARCHAR(64) NOT NULL,
    follower_text VARCHAR(64) NOT NULL DEFAULT '',
    follower_count BIGINT NOT NULL DEFAULT 0,
    signal_type TEXT NOT NULL DEFAULT '',
    value_note TEXT NOT NULL DEFAULT '',
    score FLOAT NOT NULL DEFAULT 0,
    priority_rank INTEGER NOT NULL DEFAULT 999,
    source_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    run_id VARCHAR(96) NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_stock_x_accounts_updated_at ON stock_x_accounts;
CREATE TRIGGER update_stock_x_accounts_updated_at
    BEFORE UPDATE ON stock_x_accounts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS stock_x_ingest_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(96) NOT NULL UNIQUE,
    mode VARCHAR(16) NOT NULL DEFAULT 'full',
    status VARCHAR(16) NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'success', 'failed')),
    accounts_total INTEGER NOT NULL DEFAULT 0,
    accounts_success INTEGER NOT NULL DEFAULT 0,
    accounts_failed INTEGER NOT NULL DEFAULT 0,
    posts_written INTEGER NOT NULL DEFAULT 0,
    signals_written INTEGER NOT NULL DEFAULT 0,
    events_written INTEGER NOT NULL DEFAULT 0,
    duration_sec INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT NOT NULL DEFAULT '',
    params_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_stock_x_ingest_runs_updated_at ON stock_x_ingest_runs;
CREATE TRIGGER update_stock_x_ingest_runs_updated_at
    BEFORE UPDATE ON stock_x_ingest_runs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS stock_x_posts_raw (
    id BIGSERIAL PRIMARY KEY,
    post_key VARCHAR(160) NOT NULL UNIQUE,
    account_id BIGINT NOT NULL REFERENCES stock_x_accounts(id) ON DELETE CASCADE,
    handle VARCHAR(64) NOT NULL,
    post_id VARCHAR(64) NOT NULL DEFAULT '',
    post_url TEXT NOT NULL DEFAULT '',
    posted_at TIMESTAMP WITH TIME ZONE,
    content TEXT NOT NULL,
    content_zh TEXT NOT NULL DEFAULT '',
    lang VARCHAR(16) NOT NULL DEFAULT 'unknown',
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    run_id VARCHAR(96) NOT NULL,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_stock_x_posts_raw_updated_at ON stock_x_posts_raw;
CREATE TRIGGER update_stock_x_posts_raw_updated_at
    BEFORE UPDATE ON stock_x_posts_raw
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS stock_x_post_signals (
    id BIGSERIAL PRIMARY KEY,
    post_id BIGINT NOT NULL REFERENCES stock_x_posts_raw(id) ON DELETE CASCADE,
    account_id BIGINT NOT NULL REFERENCES stock_x_accounts(id) ON DELETE CASCADE,
    handle VARCHAR(64) NOT NULL,
    ticker VARCHAR(16) NOT NULL,
    side VARCHAR(16) NOT NULL CHECK (side IN ('LONG', 'SHORT', 'NEUTRAL')),
    event_type VARCHAR(32) NOT NULL DEFAULT 'news',
    confidence FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    strength FLOAT NOT NULL DEFAULT 0.5 CHECK (strength >= 0 AND strength <= 1),
    summary_zh TEXT NOT NULL DEFAULT '',
    why_now_zh TEXT NOT NULL DEFAULT '',
    invalid_if_zh TEXT NOT NULL DEFAULT '',
    signal_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    run_id VARCHAR(96) NOT NULL,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(post_id, ticker, event_type, side)
);

CREATE TABLE IF NOT EXISTS stock_x_account_health_daily (
    id BIGSERIAL PRIMARY KEY,
    health_date DATE NOT NULL,
    handle VARCHAR(64) NOT NULL,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    post_count INTEGER NOT NULL DEFAULT 0,
    signal_count INTEGER NOT NULL DEFAULT 0,
    avg_latency_ms FLOAT NOT NULL DEFAULT 0,
    status VARCHAR(16) NOT NULL DEFAULT 'healthy' CHECK (status IN ('healthy', 'degraded', 'critical')),
    latest_error TEXT NOT NULL DEFAULT '',
    run_id VARCHAR(96) NOT NULL DEFAULT '',
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(health_date, handle)
);

CREATE INDEX IF NOT EXISTS idx_stock_x_accounts_active
    ON stock_x_accounts(is_active, priority_rank);
CREATE INDEX IF NOT EXISTS idx_stock_x_posts_handle_time
    ON stock_x_posts_raw(handle, posted_at DESC);
CREATE INDEX IF NOT EXISTS idx_stock_x_posts_run_id
    ON stock_x_posts_raw(run_id, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_stock_x_signals_ticker
    ON stock_x_post_signals(ticker, confidence DESC);
CREATE INDEX IF NOT EXISTS idx_stock_x_signals_run_id
    ON stock_x_post_signals(run_id, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_stock_x_health_date
    ON stock_x_account_health_daily(health_date DESC, status);

ALTER TABLE stock_x_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_x_ingest_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_x_posts_raw ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_x_post_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_x_account_health_daily ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE stock_x_accounts IS 'Stock X/Twitter 账号主数据';
COMMENT ON TABLE stock_x_ingest_runs IS 'Stock X 采集运行记录';
COMMENT ON TABLE stock_x_posts_raw IS 'Stock X 原始内容存档';
COMMENT ON TABLE stock_x_post_signals IS 'Stock X 结构化信号';
COMMENT ON TABLE stock_x_account_health_daily IS 'Stock X 账号健康度日快照';
