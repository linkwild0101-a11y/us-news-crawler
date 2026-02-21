-- Stock V2 indexes + RLS policies
-- 日期: 2026-02-21

CREATE INDEX IF NOT EXISTS idx_stock_events_v2_active_asof
    ON stock_events_v2(is_active, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_stock_events_v2_source
    ON stock_events_v2(source_type, source_ref);
CREATE INDEX IF NOT EXISTS idx_stock_events_v2_direction
    ON stock_events_v2(direction);
CREATE INDEX IF NOT EXISTS idx_stock_events_v2_run_id
    ON stock_events_v2(run_id);

CREATE INDEX IF NOT EXISTS idx_stock_event_tickers_v2_event
    ON stock_event_tickers_v2(event_id);
CREATE INDEX IF NOT EXISTS idx_stock_event_tickers_v2_ticker
    ON stock_event_tickers_v2(ticker);
CREATE INDEX IF NOT EXISTS idx_stock_event_tickers_v2_run_id
    ON stock_event_tickers_v2(run_id);

CREATE INDEX IF NOT EXISTS idx_stock_signals_v2_active_score
    ON stock_signals_v2(is_active, signal_score DESC);
CREATE INDEX IF NOT EXISTS idx_stock_signals_v2_ticker
    ON stock_signals_v2(ticker);
CREATE INDEX IF NOT EXISTS idx_stock_signals_v2_expires
    ON stock_signals_v2(expires_at);
CREATE INDEX IF NOT EXISTS idx_stock_signals_v2_run_id
    ON stock_signals_v2(run_id);

CREATE INDEX IF NOT EXISTS idx_stock_opportunities_v2_active_score
    ON stock_opportunities_v2(is_active, opportunity_score DESC);
CREATE INDEX IF NOT EXISTS idx_stock_opportunities_v2_ticker
    ON stock_opportunities_v2(ticker);
CREATE INDEX IF NOT EXISTS idx_stock_opportunities_v2_horizon
    ON stock_opportunities_v2(horizon);
CREATE INDEX IF NOT EXISTS idx_stock_opportunities_v2_expires
    ON stock_opportunities_v2(expires_at);
CREATE INDEX IF NOT EXISTS idx_stock_opportunities_v2_run_id
    ON stock_opportunities_v2(run_id);

CREATE INDEX IF NOT EXISTS idx_stock_market_regime_v2_date
    ON stock_market_regime_v2(regime_date DESC);
CREATE INDEX IF NOT EXISTS idx_stock_market_regime_v2_active
    ON stock_market_regime_v2(is_active, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_stock_market_regime_v2_run_id
    ON stock_market_regime_v2(run_id);

CREATE INDEX IF NOT EXISTS idx_stock_dashboard_snapshot_v2_active
    ON stock_dashboard_snapshot_v2(is_active, snapshot_time DESC);
CREATE INDEX IF NOT EXISTS idx_stock_dashboard_snapshot_v2_run_id
    ON stock_dashboard_snapshot_v2(run_id);

ALTER TABLE stock_events_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_event_tickers_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_signals_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_opportunities_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_market_regime_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_dashboard_snapshot_v2 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS stock_events_v2_public_read ON stock_events_v2;
CREATE POLICY stock_events_v2_public_read
    ON stock_events_v2
    FOR SELECT
    TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS stock_event_tickers_v2_public_read ON stock_event_tickers_v2;
CREATE POLICY stock_event_tickers_v2_public_read
    ON stock_event_tickers_v2
    FOR SELECT
    TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS stock_signals_v2_public_read ON stock_signals_v2;
CREATE POLICY stock_signals_v2_public_read
    ON stock_signals_v2
    FOR SELECT
    TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS stock_opportunities_v2_public_read ON stock_opportunities_v2;
CREATE POLICY stock_opportunities_v2_public_read
    ON stock_opportunities_v2
    FOR SELECT
    TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS stock_market_regime_v2_public_read ON stock_market_regime_v2;
CREATE POLICY stock_market_regime_v2_public_read
    ON stock_market_regime_v2
    FOR SELECT
    TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS stock_dashboard_snapshot_v2_public_read ON stock_dashboard_snapshot_v2;
CREATE POLICY stock_dashboard_snapshot_v2_public_read
    ON stock_dashboard_snapshot_v2
    FOR SELECT
    TO anon, authenticated
    USING (true);
