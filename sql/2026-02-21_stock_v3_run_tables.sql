-- Stock V3 run metadata tables
-- 日期: 2026-02-21

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TABLE IF NOT EXISTS research_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(96) UNIQUE NOT NULL,
    pipeline_name VARCHAR(64) NOT NULL,
    pipeline_version VARCHAR(64) NOT NULL DEFAULT 'v1',
    trigger_type VARCHAR(32) NOT NULL DEFAULT 'manual',
    status VARCHAR(16) NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'success', 'failed', 'degraded')),
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMP WITH TIME ZONE,
    duration_sec INTEGER NOT NULL DEFAULT 0 CHECK (duration_sec >= 0),
    input_window JSONB NOT NULL DEFAULT '{}'::jsonb,
    params_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    commit_sha VARCHAR(64) NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_research_runs_updated_at ON research_runs;
CREATE TRIGGER update_research_runs_updated_at
    BEFORE UPDATE ON research_runs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS research_run_metrics (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(96) NOT NULL REFERENCES research_runs(run_id) ON DELETE CASCADE,
    metric_name VARCHAR(64) NOT NULL,
    metric_value DOUBLE PRECISION NOT NULL DEFAULT 0,
    metric_unit VARCHAR(16) NOT NULL DEFAULT 'count',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(run_id, metric_name)
);

CREATE TABLE IF NOT EXISTS research_run_artifacts (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(96) NOT NULL REFERENCES research_runs(run_id) ON DELETE CASCADE,
    artifact_type VARCHAR(32) NOT NULL,
    artifact_ref TEXT NOT NULL,
    checksum VARCHAR(128) NOT NULL DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_runs_pipeline_started
    ON research_runs(pipeline_name, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_research_runs_status_started
    ON research_runs(status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_research_run_metrics_run_id
    ON research_run_metrics(run_id);
CREATE INDEX IF NOT EXISTS idx_research_run_metrics_metric_name
    ON research_run_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_research_run_artifacts_run_id
    ON research_run_artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_research_run_artifacts_type
    ON research_run_artifacts(artifact_type);

ALTER TABLE research_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_run_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_run_artifacts ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE research_runs IS 'Stock V3 运行主记录';
COMMENT ON TABLE research_run_metrics IS 'Stock V3 运行指标';
COMMENT ON TABLE research_run_artifacts IS 'Stock V3 运行附件';
