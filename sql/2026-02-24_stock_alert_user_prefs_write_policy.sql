-- Sprint C: allow frontend write for alert user prefs
-- 日期: 2026-02-24

ALTER TABLE stock_alert_user_prefs_v1 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS stock_alert_user_prefs_v1_public_insert ON stock_alert_user_prefs_v1;
DROP POLICY IF EXISTS stock_alert_user_prefs_v1_public_update ON stock_alert_user_prefs_v1;

CREATE POLICY stock_alert_user_prefs_v1_public_insert
    ON stock_alert_user_prefs_v1
    FOR INSERT
    TO anon, authenticated
    WITH CHECK (
      user_id = 'system'
      AND daily_alert_cap BETWEEN 1 AND 200
      AND coalesce(array_length(watch_tickers, 1), 0) <= 200
      AND coalesce(array_length(muted_signal_types, 1), 0) <= 50
    );

CREATE POLICY stock_alert_user_prefs_v1_public_update
    ON stock_alert_user_prefs_v1
    FOR UPDATE
    TO anon, authenticated
    USING (user_id = 'system')
    WITH CHECK (
      user_id = 'system'
      AND daily_alert_cap BETWEEN 1 AND 200
      AND coalesce(array_length(watch_tickers, 1), 0) <= 200
      AND coalesce(array_length(muted_signal_types, 1), 0) <= 50
    );
