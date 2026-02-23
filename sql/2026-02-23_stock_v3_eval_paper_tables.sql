-- Stock V3 eval + paper trading tables
-- 日期: 2026-02-23

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language plpgsql;

CREATE TABLE IF NOT EXISTS signal_eval_snapshots (
    id BIGSERIAL PRIMARY KEY,
    signal_id BIGINT NOT NULL,
    ticker VARCHAR(16) NOT NULL,
    side VARCHAR(8) NOT NULL CHECK (side IN (LONG, SHORT)),
    label_window VARCHAR(32) NOT NULL,
    realized_return DOUBLE PRECISION NOT NULL DEFAULT 0,
    hit_flag BOOLEAN NOT NULL DEFAULT FALSE,
    calibration_bin SMALLINT NOT NULL DEFAULT 0,
    source_run_id VARCHAR(96) NOT NULL DEFAULT ,
    eval_run_id VARCHAR(96) NOT NULL DEFAULT ,
    details JSONB NOT NULL DEFAULT {}::jsonb,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(signal_id, label_window)
);

CREATE INDEX IF NOT EXISTS idx_signal_eval_snapshots_ticker
    ON signal_eval_snapshots(ticker, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_signal_eval_snapshots_eval_run
    ON signal_eval_snapshots(eval_run_id);
CREATE INDEX IF NOT EXISTS idx_signal_eval_snapshots_window
    ON signal_eval_snapshots(label_window, as_of DESC);

CREATE TABLE IF NOT EXISTS portfolio_paper_positions (
    id BIGSERIAL PRIMARY KEY,
    position_key VARCHAR(128) UNIQUE NOT NULL,
    run_id VARCHAR(96) NOT NULL,
    source_opportunity_id BIGINT,
    ticker VARCHAR(16) NOT NULL,
    side VARCHAR(8) NOT NULL CHECK (side IN (LONG, SHORT)),
    horizon VARCHAR(8) NOT NULL DEFAULT A,
    status VARCHAR(16) NOT NULL DEFAULT OPEN CHECK (status IN (OPEN, CLOSED)),
    entry_ts TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    entry_price DOUBLE PRECISION NOT NULL DEFAULT 0,
    entry_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    size DOUBLE PRECISION NOT NULL DEFAULT 1,
    mark_price DOUBLE PRECISION,
    unrealized_pnl DOUBLE PRECISION NOT NULL DEFAULT 0,
    exit_ts TIMESTAMP WITH TIME ZONE,
    exit_price DOUBLE PRECISION,
    realized_pnl DOUBLE PRECISION NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT ,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_portfolio_paper_positions_updated_at ON portfolio_paper_positions;
CREATE TRIGGER update_portfolio_paper_positions_updated_at
    BEFORE UPDATE ON portfolio_paper_positions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX IF NOT EXISTS idx_portfolio_paper_positions_status
    ON portfolio_paper_positions(status, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_portfolio_paper_positions_ticker
    ON portfolio_paper_positions(ticker, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_portfolio_paper_positions_run_id
    ON portfolio_paper_positions(run_id);

CREATE TABLE IF NOT EXISTS portfolio_paper_metrics (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(96) NOT NULL,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    open_count INTEGER NOT NULL DEFAULT 0,
    closed_count INTEGER NOT NULL DEFAULT 0,
    realized_pnl DOUBLE PRECISION NOT NULL DEFAULT 0,
    unrealized_pnl DOUBLE PRECISION NOT NULL DEFAULT 0,
    win_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
    gross_exposure DOUBLE PRECISION NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT ,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_portfolio_paper_metrics_run_id
    ON portfolio_paper_metrics(run_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_paper_metrics_as_of
    ON portfolio_paper_metrics(as_of DESC);

ALTER TABLE signal_eval_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_paper_positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_paper_metrics ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE signal_eval_snapshots IS Stock
