-- Stock V3 source health tables
-- 日期: 2026-02-21

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TABLE IF NOT EXISTS source_health_daily (
    id BIGSERIAL PRIMARY KEY,
    source_id VARCHAR(64) NOT NULL,
    health_date DATE NOT NULL,
    success_rate DOUBLE PRECISION NOT NULL DEFAULT 1
        CHECK (success_rate >= 0 AND success_rate <= 1),
    p95_latency_ms INTEGER NOT NULL DEFAULT 0 CHECK (p95_latency_ms >= 0),
    freshness_sec INTEGER NOT NULL DEFAULT 0 CHECK (freshness_sec >= 0),
    null_rate DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (null_rate >= 0 AND null_rate <= 1),
    error_rate DOUBLE PRECISION NOT NULL DEFAULT 0
        CHECK (error_rate >= 0 AND error_rate <= 1),
    status VARCHAR(16) NOT NULL DEFAULT 'healthy'
        CHECK (status IN ('healthy', 'degraded', 'critical')),
    notes TEXT NOT NULL DEFAULT '',
    source_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    run_id VARCHAR(96) NOT NULL DEFAULT '',
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(source_id, health_date)
);

DROP TRIGGER IF EXISTS update_source_health_daily_updated_at ON source_health_daily;
CREATE TRIGGER update_source_health_daily_updated_at
    BEFORE UPDATE ON source_health_daily
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS source_health_incidents (
    id BIGSERIAL PRIMARY KEY,
    source_id VARCHAR(64) NOT NULL,
    incident_type VARCHAR(32) NOT NULL,
    severity VARCHAR(16) NOT NULL DEFAULT 'warning'
        CHECK (severity IN ('info', 'warning', 'critical')),
    message TEXT NOT NULL,
    context JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    run_id VARCHAR(96) NOT NULL DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_source_health_incidents_updated_at ON source_health_incidents;
CREATE TRIGGER update_source_health_incidents_updated_at
    BEFORE UPDATE ON source_health_incidents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX IF NOT EXISTS idx_source_health_daily_date
    ON source_health_daily(health_date DESC);
CREATE INDEX IF NOT EXISTS idx_source_health_daily_status
    ON source_health_daily(status);
CREATE INDEX IF NOT EXISTS idx_source_health_daily_run_id
    ON source_health_daily(run_id);

CREATE INDEX IF NOT EXISTS idx_source_health_incidents_active
    ON source_health_incidents(is_active, last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_source_health_incidents_source
    ON source_health_incidents(source_id, last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_source_health_incidents_run_id
    ON source_health_incidents(run_id);

ALTER TABLE source_health_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE source_health_incidents ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE source_health_daily IS 'Stock V3 数据源日健康快照';
COMMENT ON TABLE source_health_incidents IS 'Stock V3 数据源健康事件';
