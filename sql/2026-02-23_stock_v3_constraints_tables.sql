-- Stock V3 portfolio constraints tables
-- 日期: 2026-02-23

CREATE TABLE IF NOT EXISTS portfolio_constraint_snapshots (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(96) NOT NULL,
    opportunity_id BIGINT,
    ticker VARCHAR(16) NOT NULL,
    side VARCHAR(8) NOT NULL CHECK (side IN ('LONG', 'SHORT')),
    decision VARCHAR(16) NOT NULL CHECK (decision IN ('accepted', 'rejected')),
    decision_reason VARCHAR(64) NOT NULL DEFAULT 'accepted',
    rank INTEGER NOT NULL DEFAULT 0,
    opportunity_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    constraint_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_portfolio_constraint_snapshots_run
    ON portfolio_constraint_snapshots(run_id, decision, rank);
CREATE INDEX IF NOT EXISTS idx_portfolio_constraint_snapshots_ticker
    ON portfolio_constraint_snapshots(ticker, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_portfolio_constraint_snapshots_asof
    ON portfolio_constraint_snapshots(as_of DESC);

ALTER TABLE portfolio_constraint_snapshots ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE portfolio_constraint_snapshots IS 'Stock V3 组合约束筛选快照';
