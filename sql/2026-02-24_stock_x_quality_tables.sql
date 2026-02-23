-- Stock X quality governance tables
-- 日期: 2026-02-24

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TABLE IF NOT EXISTS stock_x_account_score_daily (
    id BIGSERIAL PRIMARY KEY,
    score_date DATE NOT NULL,
    handle VARCHAR(64) NOT NULL,
    quality_score FLOAT NOT NULL DEFAULT 0 CHECK (quality_score >= 0 AND quality_score <= 100),
    reliability_score FLOAT NOT NULL DEFAULT 0 CHECK (reliability_score >= 0 AND reliability_score <= 1),
    precision_score FLOAT NOT NULL DEFAULT 0 CHECK (precision_score >= 0 AND precision_score <= 1),
    activity_score FLOAT NOT NULL DEFAULT 0 CHECK (activity_score >= 0 AND activity_score <= 1),
    freshness_score FLOAT NOT NULL DEFAULT 0 CHECK (freshness_score >= 0 AND freshness_score <= 1),
    latency_score FLOAT NOT NULL DEFAULT 0 CHECK (latency_score >= 0 AND latency_score <= 1),
    neutral_ratio FLOAT NOT NULL DEFAULT 0 CHECK (neutral_ratio >= 0 AND neutral_ratio <= 1),
    low_conf_ratio FLOAT NOT NULL DEFAULT 0 CHECK (low_conf_ratio >= 0 AND low_conf_ratio <= 1),
    posts_7d INTEGER NOT NULL DEFAULT 0,
    signals_7d INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(16) NOT NULL DEFAULT 'degraded' CHECK (status IN ('healthy', 'degraded', 'critical')),
    notes TEXT NOT NULL DEFAULT '',
    run_id VARCHAR(96) NOT NULL DEFAULT '',
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(score_date, handle)
);

DROP TRIGGER IF EXISTS update_stock_x_account_score_daily_updated_at ON stock_x_account_score_daily;
CREATE TRIGGER update_stock_x_account_score_daily_updated_at
    BEFORE UPDATE ON stock_x_account_score_daily
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX IF NOT EXISTS idx_stock_x_score_date
    ON stock_x_account_score_daily(score_date DESC, quality_score DESC);
CREATE INDEX IF NOT EXISTS idx_stock_x_score_handle
    ON stock_x_account_score_daily(handle, score_date DESC);

ALTER TABLE stock_x_account_score_daily ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE stock_x_account_score_daily IS 'Stock X 账号日质量评分快照';
