-- Stock V3 Phase2-Phase4 tables
-- 日期: 2026-02-23

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TABLE IF NOT EXISTS signal_model_scorecards (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(96) NOT NULL,
    score_date DATE NOT NULL DEFAULT CURRENT_DATE,
    opportunity_id BIGINT REFERENCES stock_opportunities_v2(id) ON DELETE SET NULL,
    ticker VARCHAR(16) NOT NULL,
    side VARCHAR(8) NOT NULL CHECK (side IN ('LONG', 'SHORT')),
    horizon VARCHAR(8) NOT NULL CHECK (horizon IN ('A', 'B')),
    champion_model VARCHAR(32) NOT NULL DEFAULT 'v2_rule',
    challenger_model VARCHAR(32) NOT NULL DEFAULT 'v3_alt',
    champion_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    challenger_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    score_delta DOUBLE PRECISION NOT NULL DEFAULT 0,
    expected_hit_proxy DOUBLE PRECISION NOT NULL DEFAULT 0,
    winner VARCHAR(16) NOT NULL DEFAULT 'tie'
        CHECK (winner IN ('champion', 'challenger', 'tie')),
    promote_candidate BOOLEAN NOT NULL DEFAULT FALSE,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(run_id, opportunity_id, challenger_model)
);

CREATE TABLE IF NOT EXISTS signal_drift_snapshots (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(96) NOT NULL,
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    window_hours INTEGER NOT NULL DEFAULT 24,
    metric_name VARCHAR(64) NOT NULL,
    baseline_value DOUBLE PRECISION NOT NULL DEFAULT 0,
    current_value DOUBLE PRECISION NOT NULL DEFAULT 0,
    drift_value DOUBLE PRECISION NOT NULL DEFAULT 0,
    threshold_warn DOUBLE PRECISION NOT NULL DEFAULT 0,
    threshold_critical DOUBLE PRECISION NOT NULL DEFAULT 0,
    status VARCHAR(16) NOT NULL DEFAULT 'normal'
        CHECK (status IN ('normal', 'warn', 'critical')),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(run_id, metric_name)
);

CREATE TABLE IF NOT EXISTS opportunity_lifecycle_snapshots (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(96) UNIQUE NOT NULL,
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    window_hours INTEGER NOT NULL DEFAULT 24,
    generated_count INTEGER NOT NULL DEFAULT 0,
    active_count INTEGER NOT NULL DEFAULT 0,
    long_count INTEGER NOT NULL DEFAULT 0,
    short_count INTEGER NOT NULL DEFAULT 0,
    expiring_24h_count INTEGER NOT NULL DEFAULT 0,
    expired_24h_count INTEGER NOT NULL DEFAULT 0,
    paper_closed_24h_count INTEGER NOT NULL DEFAULT 0,
    paper_win_rate_24h DOUBLE PRECISION NOT NULL DEFAULT 0,
    top_event_types JSONB NOT NULL DEFAULT '[]'::jsonb,
    notes TEXT NOT NULL DEFAULT '',
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stock_alert_subscriptions (
    id BIGSERIAL PRIMARY KEY,
    subscription_key VARCHAR(128) UNIQUE NOT NULL,
    subscriber VARCHAR(64) NOT NULL,
    channel VARCHAR(16) NOT NULL DEFAULT 'feishu'
        CHECK (channel IN ('feishu')),
    feishu_webhook_url TEXT NOT NULL DEFAULT '',
    tickers TEXT[] NOT NULL DEFAULT '{}',
    side_filter VARCHAR(8) NOT NULL DEFAULT 'ALL'
        CHECK (side_filter IN ('ALL', 'LONG', 'SHORT')),
    min_risk_level VARCHAR(4) NOT NULL DEFAULT 'L3'
        CHECK (min_risk_level IN ('L1', 'L2', 'L3', 'L4')),
    min_opportunity_score DOUBLE PRECISION NOT NULL DEFAULT 70,
    min_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.55,
    cooldown_minutes INTEGER NOT NULL DEFAULT 30,
    max_items_per_run INTEGER NOT NULL DEFAULT 3,
    quiet_hours_start SMALLINT NOT NULL DEFAULT 0,
    quiet_hours_end SMALLINT NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_sent_at TIMESTAMP WITH TIME ZONE,
    notes TEXT NOT NULL DEFAULT '',
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_stock_alert_subscriptions_updated_at ON stock_alert_subscriptions;
CREATE TRIGGER update_stock_alert_subscriptions_updated_at
    BEFORE UPDATE ON stock_alert_subscriptions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS stock_alert_delivery_logs (
    id BIGSERIAL PRIMARY KEY,
    delivery_key VARCHAR(160) UNIQUE NOT NULL,
    subscription_id BIGINT NOT NULL REFERENCES stock_alert_subscriptions(id) ON DELETE CASCADE,
    run_id VARCHAR(96) NOT NULL DEFAULT '',
    channel VARCHAR(16) NOT NULL DEFAULT 'feishu',
    ticker VARCHAR(16) NOT NULL,
    side VARCHAR(8) NOT NULL CHECK (side IN ('LONG', 'SHORT')),
    risk_level VARCHAR(4) NOT NULL CHECK (risk_level IN ('L0', 'L1', 'L2', 'L3', 'L4')),
    opportunity_id BIGINT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(16) NOT NULL DEFAULT 'sent'
        CHECK (status IN ('sent', 'skipped', 'failed')),
    response_text TEXT NOT NULL DEFAULT '',
    sent_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signal_model_scorecards_date
    ON signal_model_scorecards(score_date DESC);
CREATE INDEX IF NOT EXISTS idx_signal_model_scorecards_winner
    ON signal_model_scorecards(winner, score_date DESC);
CREATE INDEX IF NOT EXISTS idx_signal_model_scorecards_ticker
    ON signal_model_scorecards(ticker, score_date DESC);

CREATE INDEX IF NOT EXISTS idx_signal_drift_snapshots_date
    ON signal_drift_snapshots(snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_signal_drift_snapshots_status
    ON signal_drift_snapshots(status, snapshot_date DESC);

CREATE INDEX IF NOT EXISTS idx_opportunity_lifecycle_snapshots_date
    ON opportunity_lifecycle_snapshots(snapshot_date DESC);

CREATE INDEX IF NOT EXISTS idx_stock_alert_subscriptions_active
    ON stock_alert_subscriptions(is_active, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_stock_alert_delivery_logs_sub_sent
    ON stock_alert_delivery_logs(subscription_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_stock_alert_delivery_logs_opportunity
    ON stock_alert_delivery_logs(opportunity_id, sent_at DESC);

ALTER TABLE signal_model_scorecards ENABLE ROW LEVEL SECURITY;
ALTER TABLE signal_drift_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE opportunity_lifecycle_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_alert_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_alert_delivery_logs ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE signal_model_scorecards IS 'Stock V3 Champion/Challenger 对照评分卡';
COMMENT ON TABLE signal_drift_snapshots IS 'Stock V3 信号/机会分布漂移快照';
COMMENT ON TABLE opportunity_lifecycle_snapshots IS 'Stock V3 机会生命周期日复盘快照';
COMMENT ON TABLE stock_alert_subscriptions IS 'Stock V3 订阅告警配置（ticker/方向/等级）';
COMMENT ON TABLE stock_alert_delivery_logs IS 'Stock V3 订阅告警投递日志';
