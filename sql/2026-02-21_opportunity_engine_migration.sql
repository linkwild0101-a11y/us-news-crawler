-- Opportunity engine migration
-- 日期: 2026-02-21

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TABLE IF NOT EXISTS opportunities (
    id SERIAL PRIMARY KEY,
    opportunity_key VARCHAR(128) UNIQUE NOT NULL,
    ticker VARCHAR(16) NOT NULL,
    side VARCHAR(8) NOT NULL CHECK (side IN ('LONG', 'SHORT')),
    horizon VARCHAR(8) NOT NULL CHECK (horizon IN ('A', 'B')),
    opportunity_score FLOAT NOT NULL CHECK (opportunity_score >= 0 AND opportunity_score <= 100),
    confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    risk_level VARCHAR(4) DEFAULT 'L1',
    why_now TEXT NOT NULL,
    invalid_if TEXT NOT NULL,
    catalysts JSONB DEFAULT '[]'::jsonb,
    factor_breakdown JSONB DEFAULT '{}'::jsonb,
    source_signal_ids INTEGER[] DEFAULT '{}',
    source_cluster_ids INTEGER[] DEFAULT '{}',
    expires_at TIMESTAMP WITH TIME ZONE,
    as_of TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_opportunities_score ON opportunities(opportunity_score DESC);
CREATE INDEX IF NOT EXISTS idx_opportunities_ticker ON opportunities(ticker);
CREATE INDEX IF NOT EXISTS idx_opportunities_side ON opportunities(side);
CREATE INDEX IF NOT EXISTS idx_opportunities_horizon ON opportunities(horizon);
CREATE INDEX IF NOT EXISTS idx_opportunities_asof ON opportunities(as_of DESC);

DROP TRIGGER IF EXISTS update_opportunities_updated_at ON opportunities;
CREATE TRIGGER update_opportunities_updated_at
    BEFORE UPDATE ON opportunities
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS opportunity_evidence (
    id SERIAL PRIMARY KEY,
    opportunity_id INTEGER REFERENCES opportunities(id) ON DELETE CASCADE,
    source_type VARCHAR(32) NOT NULL,
    source_ref VARCHAR(128) NOT NULL,
    title TEXT,
    url TEXT,
    weight FLOAT DEFAULT 0.5 CHECK (weight >= 0 AND weight <= 1),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(opportunity_id, source_type, source_ref)
);

CREATE INDEX IF NOT EXISTS idx_oe_opportunity_id ON opportunity_evidence(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_oe_source_type ON opportunity_evidence(source_type);

CREATE TABLE IF NOT EXISTS ticker_factor_snapshot (
    ticker VARCHAR(16) PRIMARY KEY,
    flow_score FLOAT DEFAULT 0 CHECK (flow_score >= -1 AND flow_score <= 1),
    macro_score FLOAT DEFAULT 0 CHECK (macro_score >= -1 AND macro_score <= 1),
    event_score FLOAT DEFAULT 0 CHECK (event_score >= -1 AND event_score <= 1),
    sentiment_score FLOAT DEFAULT 0 CHECK (sentiment_score >= -1 AND sentiment_score <= 1),
    volatility_score FLOAT DEFAULT 0 CHECK (volatility_score >= -1 AND volatility_score <= 1),
    risk_adjust FLOAT DEFAULT 0 CHECK (risk_adjust >= -1 AND risk_adjust <= 1),
    total_score FLOAT DEFAULT 0 CHECK (total_score >= -1 AND total_score <= 1),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tfs_total_score ON ticker_factor_snapshot(total_score DESC);

CREATE TABLE IF NOT EXISTS market_regime_daily (
    regime_date DATE PRIMARY KEY,
    risk_state VARCHAR(16) DEFAULT 'neutral',
    vol_state VARCHAR(16) DEFAULT 'mid_vol',
    liquidity_state VARCHAR(16) DEFAULT 'neutral',
    regime_score FLOAT DEFAULT 0 CHECK (regime_score >= -1 AND regime_score <= 1),
    summary TEXT DEFAULT '',
    source_payload JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_market_regime_updated_at ON market_regime_daily;
CREATE TRIGGER update_market_regime_updated_at
    BEFORE UPDATE ON market_regime_daily
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE opportunities ENABLE ROW LEVEL SECURITY;
ALTER TABLE opportunity_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE ticker_factor_snapshot ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_regime_daily ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS opportunities_public_read ON opportunities;
CREATE POLICY opportunities_public_read
    ON opportunities
    FOR SELECT
    TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS opportunity_evidence_public_read ON opportunity_evidence;
CREATE POLICY opportunity_evidence_public_read
    ON opportunity_evidence
    FOR SELECT
    TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS ticker_factor_snapshot_public_read ON ticker_factor_snapshot;
CREATE POLICY ticker_factor_snapshot_public_read
    ON ticker_factor_snapshot
    FOR SELECT
    TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS market_regime_daily_public_read ON market_regime_daily;
CREATE POLICY market_regime_daily_public_read
    ON market_regime_daily
    FOR SELECT
    TO anon, authenticated
    USING (true);

COMMENT ON TABLE opportunities IS '美股投资机会主表（多空机会）';
COMMENT ON TABLE opportunity_evidence IS '机会证据表（信号/新闻/来源）';
COMMENT ON TABLE ticker_factor_snapshot IS 'Ticker 因子快照（用于机会解释）';
COMMENT ON TABLE market_regime_daily IS '市场状态快照（risk-on/off）';
