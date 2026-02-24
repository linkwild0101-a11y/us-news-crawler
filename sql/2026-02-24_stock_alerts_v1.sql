-- StockOps P0: Alert loop tables (rule -> event -> delivery -> feedback)
-- 日期: 2026-02-24

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TABLE IF NOT EXISTS stock_alert_rules_v1 (
    id BIGSERIAL PRIMARY KEY,
    rule_key VARCHAR(96) UNIQUE NOT NULL,
    user_id VARCHAR(64) NOT NULL DEFAULT 'system',
    signal_type VARCHAR(32) NOT NULL DEFAULT 'opportunity',
    min_level VARCHAR(2) NOT NULL DEFAULT 'L3',
    min_score FLOAT NOT NULL DEFAULT 70 CHECK (min_score >= 0 AND min_score <= 100),
    cooldown_sec INTEGER NOT NULL DEFAULT 7200 CHECK (cooldown_sec >= 60),
    session_scope VARCHAR(16) NOT NULL DEFAULT 'all'
        CHECK (session_scope IN ('all', 'regular', 'premarket', 'postmarket')),
    daily_limit INTEGER NOT NULL DEFAULT 20 CHECK (daily_limit >= 1),
    priority INTEGER NOT NULL DEFAULT 100,
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    run_id VARCHAR(64) NOT NULL DEFAULT '',
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_stock_alert_rules_v1_updated_at ON stock_alert_rules_v1;
CREATE TRIGGER update_stock_alert_rules_v1_updated_at
    BEFORE UPDATE ON stock_alert_rules_v1
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS stock_alert_events_v1 (
    id BIGSERIAL PRIMARY KEY,
    alert_key VARCHAR(128) UNIQUE NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    ticker VARCHAR(16) NOT NULL,
    signal_type VARCHAR(32) NOT NULL,
    signal_level VARCHAR(2) NOT NULL DEFAULT 'L1',
    alert_score FLOAT NOT NULL DEFAULT 0 CHECK (alert_score >= 0 AND alert_score <= 100),
    side VARCHAR(16) NOT NULL DEFAULT 'NEUTRAL',
    title VARCHAR(220) NOT NULL,
    why_now TEXT NOT NULL DEFAULT '',
    session_tag VARCHAR(16) NOT NULL DEFAULT 'regular'
        CHECK (session_tag IN ('regular', 'premarket', 'postmarket', 'closed')),
    dedupe_window TIMESTAMP WITH TIME ZONE NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(16) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'sent', 'deduped', 'dropped')),
    run_id VARCHAR(64) NOT NULL,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, ticker, signal_type, dedupe_window)
);

DROP TRIGGER IF EXISTS update_stock_alert_events_v1_updated_at ON stock_alert_events_v1;
CREATE TRIGGER update_stock_alert_events_v1_updated_at
    BEFORE UPDATE ON stock_alert_events_v1
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS stock_alert_delivery_v1 (
    id BIGSERIAL PRIMARY KEY,
    alert_id BIGINT NOT NULL REFERENCES stock_alert_events_v1(id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL,
    channel VARCHAR(32) NOT NULL DEFAULT 'inbox',
    dedupe_key VARCHAR(180) UNIQUE NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'sent'
        CHECK (status IN ('sent', 'failed', 'deduped')),
    provider_message TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    sent_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    run_id VARCHAR(64) NOT NULL,
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stock_alert_feedback_v1 (
    id BIGSERIAL PRIMARY KEY,
    alert_id BIGINT NOT NULL REFERENCES stock_alert_events_v1(id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL,
    label VARCHAR(16) NOT NULL CHECK (label IN ('useful', 'noise')),
    reason VARCHAR(240) NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    run_id VARCHAR(64) NOT NULL DEFAULT '',
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stock_alert_user_prefs_v1 (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(64) UNIQUE NOT NULL,
    enable_premarket BOOLEAN NOT NULL DEFAULT FALSE,
    enable_postmarket BOOLEAN NOT NULL DEFAULT TRUE,
    daily_alert_cap INTEGER NOT NULL DEFAULT 20 CHECK (daily_alert_cap >= 1),
    watch_tickers TEXT[] NOT NULL DEFAULT '{}',
    muted_signal_types TEXT[] NOT NULL DEFAULT '{}',
    run_id VARCHAR(64) NOT NULL DEFAULT '',
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_stock_alert_user_prefs_v1_updated_at ON stock_alert_user_prefs_v1;
CREATE TRIGGER update_stock_alert_user_prefs_v1_updated_at
    BEFORE UPDATE ON stock_alert_user_prefs_v1
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX IF NOT EXISTS idx_stock_alert_rules_v1_active
    ON stock_alert_rules_v1(is_active, priority, user_id);
CREATE INDEX IF NOT EXISTS idx_stock_alert_events_v1_user_created
    ON stock_alert_events_v1(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_stock_alert_events_v1_status
    ON stock_alert_events_v1(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_stock_alert_delivery_v1_alert
    ON stock_alert_delivery_v1(alert_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_stock_alert_feedback_v1_alert
    ON stock_alert_feedback_v1(alert_id, created_at DESC);

ALTER TABLE stock_alert_rules_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_alert_events_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_alert_delivery_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_alert_feedback_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_alert_user_prefs_v1 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS stock_alert_rules_v1_public_read ON stock_alert_rules_v1;
DROP POLICY IF EXISTS stock_alert_events_v1_public_read ON stock_alert_events_v1;
DROP POLICY IF EXISTS stock_alert_delivery_v1_public_read ON stock_alert_delivery_v1;
DROP POLICY IF EXISTS stock_alert_feedback_v1_public_read ON stock_alert_feedback_v1;
DROP POLICY IF EXISTS stock_alert_user_prefs_v1_public_read ON stock_alert_user_prefs_v1;

CREATE POLICY stock_alert_rules_v1_public_read
    ON stock_alert_rules_v1 FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY stock_alert_events_v1_public_read
    ON stock_alert_events_v1 FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY stock_alert_delivery_v1_public_read
    ON stock_alert_delivery_v1 FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY stock_alert_feedback_v1_public_read
    ON stock_alert_feedback_v1 FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY stock_alert_user_prefs_v1_public_read
    ON stock_alert_user_prefs_v1 FOR SELECT TO anon, authenticated USING (true);

INSERT INTO stock_alert_rules_v1 (
    rule_key,
    user_id,
    signal_type,
    min_level,
    min_score,
    cooldown_sec,
    session_scope,
    daily_limit,
    priority,
    params,
    run_id,
    is_active
)
VALUES (
    'default-l3-70',
    'system',
    'opportunity',
    'L3',
    70,
    7200,
    'all',
    20,
    100,
    '{"note":"default MVP rule"}'::jsonb,
    'bootstrap',
    true
)
ON CONFLICT (rule_key) DO NOTHING;

INSERT INTO stock_alert_user_prefs_v1 (
    user_id,
    enable_premarket,
    enable_postmarket,
    daily_alert_cap,
    watch_tickers,
    muted_signal_types,
    run_id,
    is_active
)
VALUES (
    'system',
    false,
    true,
    20,
    '{}',
    '{}',
    'bootstrap',
    true
)
ON CONFLICT (user_id) DO NOTHING;

COMMENT ON TABLE stock_alert_rules_v1 IS 'StockOps 告警规则定义（P0）';
COMMENT ON TABLE stock_alert_events_v1 IS 'StockOps 告警事件（P0）';
COMMENT ON TABLE stock_alert_delivery_v1 IS 'StockOps 告警投递记录（P0）';
COMMENT ON TABLE stock_alert_feedback_v1 IS 'StockOps 用户反馈（P0）';
COMMENT ON TABLE stock_alert_user_prefs_v1 IS 'StockOps 用户偏好（P0）';
