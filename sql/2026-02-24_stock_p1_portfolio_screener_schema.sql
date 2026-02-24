-- StockOps P1: Portfolio Intelligence + Screener schema
-- 日期: 2026-02-24

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TABLE IF NOT EXISTS stock_portfolios_v1 (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL DEFAULT 'system',
    portfolio_key VARCHAR(96) NOT NULL,
    display_name VARCHAR(96) NOT NULL DEFAULT 'Default Portfolio',
    base_currency VARCHAR(8) NOT NULL DEFAULT 'USD',
    risk_profile VARCHAR(16) NOT NULL DEFAULT 'balanced'
        CHECK (risk_profile IN ('conservative', 'balanced', 'aggressive')),
    max_position_weight FLOAT NOT NULL DEFAULT 0.20
        CHECK (max_position_weight > 0 AND max_position_weight <= 1),
    max_gross_exposure FLOAT NOT NULL DEFAULT 1.00
        CHECK (max_gross_exposure > 0 AND max_gross_exposure <= 3),
    max_single_name_risk FLOAT NOT NULL DEFAULT 0.08
        CHECK (max_single_name_risk > 0 AND max_single_name_risk <= 1),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    run_id VARCHAR(64) NOT NULL DEFAULT '',
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, portfolio_key)
);

DROP TRIGGER IF EXISTS update_stock_portfolios_v1_updated_at ON stock_portfolios_v1;
CREATE TRIGGER update_stock_portfolios_v1_updated_at
    BEFORE UPDATE ON stock_portfolios_v1
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS stock_portfolio_holdings_v1 (
    id BIGSERIAL PRIMARY KEY,
    portfolio_id BIGINT NOT NULL REFERENCES stock_portfolios_v1(id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL DEFAULT 'system',
    ticker VARCHAR(16) NOT NULL,
    side VARCHAR(8) NOT NULL DEFAULT 'LONG' CHECK (side IN ('LONG', 'SHORT')),
    quantity NUMERIC(20, 6) NOT NULL DEFAULT 0,
    avg_cost FLOAT NOT NULL DEFAULT 0,
    market_value FLOAT NOT NULL DEFAULT 0,
    weight FLOAT NOT NULL DEFAULT 0 CHECK (weight >= -1 AND weight <= 1),
    stop_loss_pct FLOAT NULL,
    take_profit_pct FLOAT NULL,
    tags TEXT[] NOT NULL DEFAULT '{}',
    notes TEXT NOT NULL DEFAULT '',
    run_id VARCHAR(64) NOT NULL DEFAULT '',
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (portfolio_id, ticker, side)
);

DROP TRIGGER IF EXISTS update_stock_portfolio_holdings_v1_updated_at ON stock_portfolio_holdings_v1;
CREATE TRIGGER update_stock_portfolio_holdings_v1_updated_at
    BEFORE UPDATE ON stock_portfolio_holdings_v1
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS stock_portfolio_advice_v1 (
    id BIGSERIAL PRIMARY KEY,
    advice_key VARCHAR(128) UNIQUE NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    portfolio_id BIGINT NOT NULL REFERENCES stock_portfolios_v1(id) ON DELETE CASCADE,
    ticker VARCHAR(16) NOT NULL,
    holding_side VARCHAR(8) NOT NULL DEFAULT 'LONG' CHECK (holding_side IN ('LONG', 'SHORT')),
    advice_type VARCHAR(24) NOT NULL
        CHECK (advice_type IN ('add', 'reduce', 'hold', 'hedge', 'watch', 'review')),
    action_side VARCHAR(8) NOT NULL DEFAULT 'NEUTRAL'
        CHECK (action_side IN ('LONG', 'SHORT', 'NEUTRAL')),
    priority_score FLOAT NOT NULL DEFAULT 0 CHECK (priority_score >= 0 AND priority_score <= 100),
    confidence FLOAT NOT NULL DEFAULT 0 CHECK (confidence >= 0 AND confidence <= 1),
    risk_level VARCHAR(4) NOT NULL DEFAULT 'L2'
        CHECK (risk_level IN ('L0', 'L1', 'L2', 'L3', 'L4')),
    trigger_points JSONB NOT NULL DEFAULT '[]'::jsonb,
    invalid_if TEXT NOT NULL DEFAULT '',
    opportunity_id BIGINT NULL,
    source_signal_ids TEXT[] NOT NULL DEFAULT '{}',
    source_event_ids TEXT[] NOT NULL DEFAULT '{}',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(16) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'dismissed', 'expired')),
    valid_until TIMESTAMP WITH TIME ZONE NULL,
    run_id VARCHAR(64) NOT NULL,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_stock_portfolio_advice_v1_updated_at ON stock_portfolio_advice_v1;
CREATE TRIGGER update_stock_portfolio_advice_v1_updated_at
    BEFORE UPDATE ON stock_portfolio_advice_v1
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS stock_screener_templates_v1 (
    id BIGSERIAL PRIMARY KEY,
    template_key VARCHAR(96) UNIQUE NOT NULL,
    owner_user_id VARCHAR(64) NOT NULL DEFAULT 'system',
    template_name VARCHAR(96) NOT NULL,
    template_type VARCHAR(16) NOT NULL
        CHECK (template_type IN ('event', 'trend', 'reversal')),
    description TEXT NOT NULL DEFAULT '',
    universe VARCHAR(32) NOT NULL DEFAULT 'us_equity',
    default_filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    scoring_weights JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    run_id VARCHAR(64) NOT NULL DEFAULT '',
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_stock_screener_templates_v1_updated_at ON stock_screener_templates_v1;
CREATE TRIGGER update_stock_screener_templates_v1_updated_at
    BEFORE UPDATE ON stock_screener_templates_v1
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS stock_screener_runs_v1 (
    id BIGSERIAL PRIMARY KEY,
    run_key VARCHAR(128) UNIQUE NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    template_id BIGINT NOT NULL REFERENCES stock_screener_templates_v1(id) ON DELETE RESTRICT,
    run_mode VARCHAR(16) NOT NULL DEFAULT 'preview'
        CHECK (run_mode IN ('preview', 'backtest', 'live_candidate')),
    universe VARCHAR(32) NOT NULL DEFAULT 'us_equity',
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(16) NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'success', 'failed')),
    run_id VARCHAR(64) NOT NULL,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_stock_screener_runs_v1_updated_at ON stock_screener_runs_v1;
CREATE TRIGGER update_stock_screener_runs_v1_updated_at
    BEFORE UPDATE ON stock_screener_runs_v1
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS stock_screener_candidates_v1 (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES stock_screener_runs_v1(id) ON DELETE CASCADE,
    ticker VARCHAR(16) NOT NULL,
    side VARCHAR(8) NOT NULL DEFAULT 'LONG' CHECK (side IN ('LONG', 'SHORT')),
    score FLOAT NOT NULL DEFAULT 0 CHECK (score >= 0 AND score <= 100),
    confidence FLOAT NOT NULL DEFAULT 0 CHECK (confidence >= 0 AND confidence <= 1),
    risk_level VARCHAR(4) NOT NULL DEFAULT 'L2'
        CHECK (risk_level IN ('L0', 'L1', 'L2', 'L3', 'L4')),
    horizon VARCHAR(2) NOT NULL DEFAULT 'B' CHECK (horizon IN ('A', 'B', 'C')),
    rank INTEGER NOT NULL DEFAULT 9999,
    reason_points JSONB NOT NULL DEFAULT '[]'::jsonb,
    backtest_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_opportunity_id BIGINT NULL,
    source_signal_ids TEXT[] NOT NULL DEFAULT '{}',
    status VARCHAR(16) NOT NULL DEFAULT 'candidate'
        CHECK (status IN ('candidate', 'selected', 'rejected')),
    run_trace_id VARCHAR(64) NOT NULL DEFAULT '',
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stock_macro_impact_map_v1 (
    id BIGSERIAL PRIMARY KEY,
    impact_key VARCHAR(128) UNIQUE NOT NULL,
    macro_event_type VARCHAR(24) NOT NULL
        CHECK (
            macro_event_type IN (
                'tariff',
                'rate',
                'regulation',
                'earnings_cycle',
                'liquidity',
                'geopolitics',
                'other'
            )
        ),
    sector_code VARCHAR(32) NOT NULL,
    ticker VARCHAR(16) NOT NULL,
    impact_direction VARCHAR(16) NOT NULL
        CHECK (impact_direction IN ('positive', 'negative', 'neutral')),
    impact_score FLOAT NOT NULL DEFAULT 0 CHECK (impact_score >= 0 AND impact_score <= 100),
    rationale_cn TEXT NOT NULL DEFAULT '',
    source_event_id BIGINT NULL,
    run_id VARCHAR(64) NOT NULL,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stock_portfolios_v1_user_active
    ON stock_portfolios_v1(user_id, is_active, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_stock_portfolio_holdings_v1_portfolio
    ON stock_portfolio_holdings_v1(portfolio_id, is_active, weight DESC);
CREATE INDEX IF NOT EXISTS idx_stock_portfolio_advice_v1_user_status
    ON stock_portfolio_advice_v1(user_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_stock_portfolio_advice_v1_ticker
    ON stock_portfolio_advice_v1(ticker, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_stock_screener_templates_v1_type
    ON stock_screener_templates_v1(template_type, is_active, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_stock_screener_runs_v1_user_created
    ON stock_screener_runs_v1(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_stock_screener_candidates_v1_run_rank
    ON stock_screener_candidates_v1(run_id, rank ASC);
CREATE INDEX IF NOT EXISTS idx_stock_macro_impact_map_v1_ticker
    ON stock_macro_impact_map_v1(ticker, as_of DESC);

ALTER TABLE stock_portfolios_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_portfolio_holdings_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_portfolio_advice_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_screener_templates_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_screener_runs_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_screener_candidates_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_macro_impact_map_v1 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS stock_portfolios_v1_public_read ON stock_portfolios_v1;
DROP POLICY IF EXISTS stock_portfolio_holdings_v1_public_read ON stock_portfolio_holdings_v1;
DROP POLICY IF EXISTS stock_portfolio_advice_v1_public_read ON stock_portfolio_advice_v1;
DROP POLICY IF EXISTS stock_screener_templates_v1_public_read ON stock_screener_templates_v1;
DROP POLICY IF EXISTS stock_screener_runs_v1_public_read ON stock_screener_runs_v1;
DROP POLICY IF EXISTS stock_screener_candidates_v1_public_read ON stock_screener_candidates_v1;
DROP POLICY IF EXISTS stock_macro_impact_map_v1_public_read ON stock_macro_impact_map_v1;

CREATE POLICY stock_portfolios_v1_public_read
    ON stock_portfolios_v1 FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY stock_portfolio_holdings_v1_public_read
    ON stock_portfolio_holdings_v1 FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY stock_portfolio_advice_v1_public_read
    ON stock_portfolio_advice_v1 FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY stock_screener_templates_v1_public_read
    ON stock_screener_templates_v1 FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY stock_screener_runs_v1_public_read
    ON stock_screener_runs_v1 FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY stock_screener_candidates_v1_public_read
    ON stock_screener_candidates_v1 FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY stock_macro_impact_map_v1_public_read
    ON stock_macro_impact_map_v1 FOR SELECT TO anon, authenticated USING (true);

INSERT INTO stock_portfolios_v1 (
    user_id,
    portfolio_key,
    display_name,
    risk_profile,
    max_position_weight,
    max_gross_exposure,
    max_single_name_risk,
    metadata,
    run_id,
    is_active
)
VALUES (
    'system',
    'default',
    'Default Portfolio',
    'balanced',
    0.20,
    1.00,
    0.08,
    '{"note":"bootstrap default portfolio"}'::jsonb,
    'bootstrap',
    true
)
ON CONFLICT (user_id, portfolio_key) DO NOTHING;

INSERT INTO stock_screener_templates_v1 (
    template_key,
    owner_user_id,
    template_name,
    template_type,
    description,
    universe,
    default_filters,
    scoring_weights,
    metadata,
    run_id,
    is_active
)
VALUES
    (
        'event-core-v1',
        'system',
        '事件驱动核心模板',
        'event',
        '关注事件密度、机会分数与置信度，适合盘前复盘。',
        'us_equity',
        '{"min_score":70,"min_confidence":0.55,"horizon":["A","B"]}'::jsonb,
        '{"score":0.55,"confidence":0.30,"freshness":0.15}'::jsonb,
        '{"version":"1.0.0"}'::jsonb,
        'bootstrap',
        true
    ),
    (
        'trend-balance-v1',
        'system',
        '趋势跟随平衡模板',
        'trend',
        '强调趋势方向一致性与风险等级，适合中短线候选筛选。',
        'us_equity',
        '{"min_score":65,"min_confidence":0.50,"risk_levels":["L1","L2","L3"]}'::jsonb,
        '{"score":0.45,"confidence":0.30,"risk":0.25}'::jsonb,
        '{"version":"1.0.0"}'::jsonb,
        'bootstrap',
        true
    ),
    (
        'reversal-guard-v1',
        'system',
        '反转防守模板',
        'reversal',
        '偏向高风险反转机会，默认更严格风险门槛。',
        'us_equity',
        '{"min_score":75,"min_confidence":0.60,"risk_levels":["L3","L4"]}'::jsonb,
        '{"score":0.40,"confidence":0.35,"catalyst":0.25}'::jsonb,
        '{"version":"1.0.0"}'::jsonb,
        'bootstrap',
        true
    )
ON CONFLICT (template_key) DO NOTHING;

COMMENT ON TABLE stock_portfolios_v1 IS 'StockOps P1 组合主表';
COMMENT ON TABLE stock_portfolio_holdings_v1 IS 'StockOps P1 组合持仓明细';
COMMENT ON TABLE stock_portfolio_advice_v1 IS 'StockOps P1 持仓建议输出';
COMMENT ON TABLE stock_screener_templates_v1 IS 'StockOps P1 筛选模板';
COMMENT ON TABLE stock_screener_runs_v1 IS 'StockOps P1 筛选运行记录';
COMMENT ON TABLE stock_screener_candidates_v1 IS 'StockOps P1 筛选候选结果';
COMMENT ON TABLE stock_macro_impact_map_v1 IS 'StockOps P1 宏观事件到行业/标的映射';
