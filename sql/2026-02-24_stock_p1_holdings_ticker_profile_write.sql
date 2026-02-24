-- StockOps P1: frontend holdings write policies + ticker profile dictionary
-- 日期: 2026-02-24

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TABLE IF NOT EXISTS stock_ticker_profiles_v1 (
    id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(16) UNIQUE NOT NULL,
    display_name VARCHAR(128) NOT NULL DEFAULT '',
    asset_type VARCHAR(16) NOT NULL DEFAULT 'unknown'
        CHECK (asset_type IN ('equity', 'etf', 'index', 'macro', 'unknown')),
    sector VARCHAR(64) NOT NULL DEFAULT 'Unknown',
    industry VARCHAR(64) NOT NULL DEFAULT 'Unknown',
    summary_cn TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    source VARCHAR(32) NOT NULL DEFAULT 'seed',
    run_id VARCHAR(64) NOT NULL DEFAULT '',
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_stock_ticker_profiles_v1_updated_at ON stock_ticker_profiles_v1;
CREATE TRIGGER update_stock_ticker_profiles_v1_updated_at
    BEFORE UPDATE ON stock_ticker_profiles_v1
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX IF NOT EXISTS idx_stock_ticker_profiles_v1_active
    ON stock_ticker_profiles_v1(is_active, updated_at DESC);

ALTER TABLE stock_ticker_profiles_v1 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS stock_ticker_profiles_v1_public_read ON stock_ticker_profiles_v1;
CREATE POLICY stock_ticker_profiles_v1_public_read
    ON stock_ticker_profiles_v1 FOR SELECT TO anon, authenticated USING (true);

ALTER TABLE stock_portfolios_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_portfolio_holdings_v1 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS stock_portfolios_v1_public_insert ON stock_portfolios_v1;
DROP POLICY IF EXISTS stock_portfolios_v1_public_update ON stock_portfolios_v1;
DROP POLICY IF EXISTS stock_portfolio_holdings_v1_public_insert ON stock_portfolio_holdings_v1;
DROP POLICY IF EXISTS stock_portfolio_holdings_v1_public_update ON stock_portfolio_holdings_v1;

CREATE POLICY stock_portfolios_v1_public_insert
    ON stock_portfolios_v1
    FOR INSERT
    TO anon, authenticated
    WITH CHECK (
      user_id = 'system'
      AND char_length(portfolio_key) BETWEEN 1 AND 96
      AND risk_profile IN ('conservative', 'balanced', 'aggressive')
      AND max_position_weight > 0
      AND max_position_weight <= 1
      AND max_gross_exposure > 0
      AND max_gross_exposure <= 3
      AND max_single_name_risk > 0
      AND max_single_name_risk <= 1
    );

CREATE POLICY stock_portfolios_v1_public_update
    ON stock_portfolios_v1
    FOR UPDATE
    TO anon, authenticated
    USING (user_id = 'system')
    WITH CHECK (
      user_id = 'system'
      AND char_length(portfolio_key) BETWEEN 1 AND 96
      AND risk_profile IN ('conservative', 'balanced', 'aggressive')
      AND max_position_weight > 0
      AND max_position_weight <= 1
      AND max_gross_exposure > 0
      AND max_gross_exposure <= 3
      AND max_single_name_risk > 0
      AND max_single_name_risk <= 1
    );

CREATE POLICY stock_portfolio_holdings_v1_public_insert
    ON stock_portfolio_holdings_v1
    FOR INSERT
    TO anon, authenticated
    WITH CHECK (
      user_id = 'system'
      AND char_length(ticker) BETWEEN 1 AND 16
      AND side IN ('LONG', 'SHORT')
      AND quantity >= 0
      AND avg_cost >= 0
      AND market_value >= 0
      AND weight >= -1
      AND weight <= 1
      AND EXISTS (
        SELECT 1
        FROM stock_portfolios_v1 p
        WHERE p.id = portfolio_id
          AND p.user_id = 'system'
      )
    );

CREATE POLICY stock_portfolio_holdings_v1_public_update
    ON stock_portfolio_holdings_v1
    FOR UPDATE
    TO anon, authenticated
    USING (user_id = 'system')
    WITH CHECK (
      user_id = 'system'
      AND char_length(ticker) BETWEEN 1 AND 16
      AND side IN ('LONG', 'SHORT')
      AND quantity >= 0
      AND avg_cost >= 0
      AND market_value >= 0
      AND weight >= -1
      AND weight <= 1
    );

COMMENT ON TABLE stock_ticker_profiles_v1 IS '股票代码基础信息字典（用于前端说明与提示）';
