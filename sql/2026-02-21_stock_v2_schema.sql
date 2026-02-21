-- Stock V2 schema migration
-- 日期: 2026-02-21

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TABLE IF NOT EXISTS stock_events_v2 (
    id BIGSERIAL PRIMARY KEY,
    event_key VARCHAR(128) UNIQUE NOT NULL,
    source_type VARCHAR(32) NOT NULL DEFAULT 'article',
    source_ref VARCHAR(128) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    direction VARCHAR(16) NOT NULL CHECK (direction IN ('LONG', 'SHORT', 'NEUTRAL')),
    strength FLOAT NOT NULL DEFAULT 0.5 CHECK (strength >= 0 AND strength <= 1),
    ttl_hours INTEGER NOT NULL DEFAULT 72,
    summary TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    published_at TIMESTAMP WITH TIME ZONE,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    run_id VARCHAR(64) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_stock_events_v2_updated_at ON stock_events_v2;
CREATE TRIGGER update_stock_events_v2_updated_at
    BEFORE UPDATE ON stock_events_v2
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS stock_event_tickers_v2 (
    id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL REFERENCES stock_events_v2(id) ON DELETE CASCADE,
    ticker VARCHAR(16) NOT NULL,
    role VARCHAR(16) NOT NULL DEFAULT 'primary',
    weight FLOAT NOT NULL DEFAULT 1 CHECK (weight >= 0 AND weight <= 1),
    confidence FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    run_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(event_id, ticker, role)
);

CREATE TABLE IF NOT EXISTS stock_signals_v2 (
    id BIGSERIAL PRIMARY KEY,
    signal_key VARCHAR(128) UNIQUE NOT NULL,
    ticker VARCHAR(16) NOT NULL,
    level VARCHAR(4) NOT NULL CHECK (level IN ('L0', 'L1', 'L2', 'L3', 'L4')),
    side VARCHAR(8) NOT NULL CHECK (side IN ('LONG', 'SHORT')),
    signal_score FLOAT NOT NULL CHECK (signal_score >= 0 AND signal_score <= 100),
    confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    trigger_factors JSONB NOT NULL DEFAULT '[]'::jsonb,
    llm_used BOOLEAN NOT NULL DEFAULT FALSE,
    explanation TEXT NOT NULL DEFAULT '',
    source_event_ids BIGINT[] NOT NULL DEFAULT '{}',
    expires_at TIMESTAMP WITH TIME ZONE,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    run_id VARCHAR(64) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_stock_signals_v2_updated_at ON stock_signals_v2;
CREATE TRIGGER update_stock_signals_v2_updated_at
    BEFORE UPDATE ON stock_signals_v2
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS stock_opportunities_v2 (
    id BIGSERIAL PRIMARY KEY,
    opportunity_key VARCHAR(128) UNIQUE NOT NULL,
    ticker VARCHAR(16) NOT NULL,
    side VARCHAR(8) NOT NULL CHECK (side IN ('LONG', 'SHORT')),
    horizon VARCHAR(8) NOT NULL CHECK (horizon IN ('A', 'B')),
    opportunity_score FLOAT NOT NULL CHECK (opportunity_score >= 0 AND opportunity_score <= 100),
    confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    risk_level VARCHAR(4) NOT NULL DEFAULT 'L1' CHECK (risk_level IN ('L0', 'L1', 'L2', 'L3', 'L4')),
    why_now TEXT NOT NULL,
    invalid_if TEXT NOT NULL,
    catalysts JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_signal_ids BIGINT[] NOT NULL DEFAULT '{}',
    source_event_ids BIGINT[] NOT NULL DEFAULT '{}',
    expires_at TIMESTAMP WITH TIME ZONE,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    run_id VARCHAR(64) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_stock_opportunities_v2_updated_at ON stock_opportunities_v2;
CREATE TRIGGER update_stock_opportunities_v2_updated_at
    BEFORE UPDATE ON stock_opportunities_v2
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS stock_market_regime_v2 (
    id BIGSERIAL PRIMARY KEY,
    regime_date DATE NOT NULL,
    risk_state VARCHAR(16) NOT NULL DEFAULT 'neutral',
    vol_state VARCHAR(16) NOT NULL DEFAULT 'mid_vol',
    liquidity_state VARCHAR(16) NOT NULL DEFAULT 'neutral',
    regime_score FLOAT NOT NULL DEFAULT 0 CHECK (regime_score >= -1 AND regime_score <= 1),
    summary TEXT NOT NULL DEFAULT '',
    source_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    run_id VARCHAR(64) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(regime_date, run_id)
);

DROP TRIGGER IF EXISTS update_stock_market_regime_v2_updated_at ON stock_market_regime_v2;
CREATE TRIGGER update_stock_market_regime_v2_updated_at
    BEFORE UPDATE ON stock_market_regime_v2
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS stock_dashboard_snapshot_v2 (
    id BIGSERIAL PRIMARY KEY,
    snapshot_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    top_opportunities JSONB NOT NULL DEFAULT '[]'::jsonb,
    top_signals JSONB NOT NULL DEFAULT '[]'::jsonb,
    market_brief TEXT NOT NULL DEFAULT '',
    risk_badge VARCHAR(4) NOT NULL DEFAULT 'L1' CHECK (risk_badge IN ('L0', 'L1', 'L2', 'L3', 'L4')),
    data_health JSONB NOT NULL DEFAULT '{}'::jsonb,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    run_id VARCHAR(64) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(run_id)
);

DROP TRIGGER IF EXISTS update_stock_dashboard_snapshot_v2_updated_at ON stock_dashboard_snapshot_v2;
CREATE TRIGGER update_stock_dashboard_snapshot_v2_updated_at
    BEFORE UPDATE ON stock_dashboard_snapshot_v2
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE stock_events_v2 IS 'Stock V2 事件主表';
COMMENT ON TABLE stock_event_tickers_v2 IS 'Stock V2 事件与ticker关联';
COMMENT ON TABLE stock_signals_v2 IS 'Stock V2 信号表（L0-L4）';
COMMENT ON TABLE stock_opportunities_v2 IS 'Stock V2 机会表（多空+A/B）';
COMMENT ON TABLE stock_market_regime_v2 IS 'Stock V2 市场状态';
COMMENT ON TABLE stock_dashboard_snapshot_v2 IS 'Stock V2 看板快照';
