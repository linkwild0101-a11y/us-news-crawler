-- Sprint B: allow frontend feedback writes under RLS
-- 日期: 2026-02-24

ALTER TABLE stock_alert_feedback_v1 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS stock_alert_feedback_v1_public_insert ON stock_alert_feedback_v1;

CREATE POLICY stock_alert_feedback_v1_public_insert
    ON stock_alert_feedback_v1
    FOR INSERT
    TO anon, authenticated
    WITH CHECK (
      char_length(trim(user_id)) > 0
      AND label IN ('useful', 'noise')
      AND char_length(reason) <= 240
      AND EXISTS (
        SELECT 1
        FROM stock_alert_events_v1 e
        WHERE e.id = alert_id
      )
    );
