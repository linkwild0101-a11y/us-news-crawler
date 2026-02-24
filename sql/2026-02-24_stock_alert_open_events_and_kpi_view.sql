-- StockOps P0 KPI: alert open events + daily KPI view
-- 日期: 2026-02-24

CREATE TABLE IF NOT EXISTS stock_alert_open_events_v1 (
    id BIGSERIAL PRIMARY KEY,
    alert_id BIGINT NOT NULL REFERENCES stock_alert_events_v1(id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL,
    source VARCHAR(32) NOT NULL DEFAULT 'frontend',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    opened_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    run_id VARCHAR(64) NOT NULL DEFAULT '',
    as_of TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (alert_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_stock_alert_open_events_v1_opened
    ON stock_alert_open_events_v1(opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_stock_alert_open_events_v1_alert
    ON stock_alert_open_events_v1(alert_id);

ALTER TABLE stock_alert_open_events_v1 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS stock_alert_open_events_v1_public_read ON stock_alert_open_events_v1;
DROP POLICY IF EXISTS stock_alert_open_events_v1_public_insert ON stock_alert_open_events_v1;

CREATE POLICY stock_alert_open_events_v1_public_read
    ON stock_alert_open_events_v1 FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY stock_alert_open_events_v1_public_insert
    ON stock_alert_open_events_v1 FOR INSERT TO anon, authenticated WITH CHECK (true);

CREATE OR REPLACE VIEW stock_alert_kpi_daily_v1 AS
WITH sent AS (
    SELECT
        (d.sent_at AT TIME ZONE 'UTC')::date AS metric_date,
        COUNT(*) AS alert_sent,
        PERCENTILE_CONT(0.95) WITHIN GROUP (
            ORDER BY EXTRACT(EPOCH FROM (d.sent_at - e.created_at))
        ) AS latency_p95_sec
    FROM stock_alert_delivery_v1 d
    JOIN stock_alert_events_v1 e ON e.id = d.alert_id
    WHERE d.status = 'sent'
    GROUP BY 1
),
opened AS (
    SELECT
        (opened_at AT TIME ZONE 'UTC')::date AS metric_date,
        COUNT(DISTINCT alert_id) AS alert_opened
    FROM stock_alert_open_events_v1
    GROUP BY 1
),
feedback AS (
    SELECT
        (created_at AT TIME ZONE 'UTC')::date AS metric_date,
        COUNT(*) AS feedback_total,
        COUNT(*) FILTER (WHERE label = 'noise') AS feedback_noise,
        COUNT(*) FILTER (WHERE label = 'useful') AS feedback_useful
    FROM stock_alert_feedback_v1
    GROUP BY 1
)
SELECT
    COALESCE(s.metric_date, o.metric_date, f.metric_date) AS metric_date,
    COALESCE(s.alert_sent, 0) AS alert_sent,
    COALESCE(o.alert_opened, 0) AS alert_opened,
    COALESCE(f.feedback_total, 0) AS feedback_total,
    COALESCE(f.feedback_noise, 0) AS feedback_noise,
    COALESCE(f.feedback_useful, 0) AS feedback_useful,
    ROUND(COALESCE(s.latency_p95_sec, 0)::numeric, 3) AS latency_p95_sec,
    ROUND(
        CASE WHEN COALESCE(s.alert_sent, 0) > 0
            THEN COALESCE(o.alert_opened, 0)::numeric / s.alert_sent::numeric
            ELSE 0
        END,
        4
    ) AS alert_ctr,
    ROUND(
        CASE WHEN COALESCE(f.feedback_total, 0) > 0
            THEN COALESCE(f.feedback_noise, 0)::numeric / f.feedback_total::numeric
            ELSE 0
        END,
        4
    ) AS noise_ratio
FROM sent s
FULL OUTER JOIN opened o ON o.metric_date = s.metric_date
FULL OUTER JOIN feedback f ON f.metric_date = COALESCE(s.metric_date, o.metric_date)
ORDER BY metric_date DESC;

COMMENT ON TABLE stock_alert_open_events_v1 IS 'StockOps P0 告警打开事件';
COMMENT ON VIEW stock_alert_kpi_daily_v1 IS 'StockOps P0 KPI 日聚合视图';
