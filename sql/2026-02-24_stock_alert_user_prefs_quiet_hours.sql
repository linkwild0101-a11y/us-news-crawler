-- Sprint C: quiet hours support for stock alert user prefs
-- 日期: 2026-02-24

ALTER TABLE stock_alert_user_prefs_v1
    ADD COLUMN IF NOT EXISTS quiet_hours_start SMALLINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS quiet_hours_end SMALLINT NOT NULL DEFAULT 0;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'stock_alert_user_prefs_v1_quiet_hours_start_check'
    ) THEN
        ALTER TABLE stock_alert_user_prefs_v1
            ADD CONSTRAINT stock_alert_user_prefs_v1_quiet_hours_start_check
            CHECK (quiet_hours_start >= 0 AND quiet_hours_start <= 23);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'stock_alert_user_prefs_v1_quiet_hours_end_check'
    ) THEN
        ALTER TABLE stock_alert_user_prefs_v1
            ADD CONSTRAINT stock_alert_user_prefs_v1_quiet_hours_end_check
            CHECK (quiet_hours_end >= 0 AND quiet_hours_end <= 23);
    END IF;
END $$;

UPDATE stock_alert_user_prefs_v1
SET
    quiet_hours_start = coalesce(quiet_hours_start, 0),
    quiet_hours_end = coalesce(quiet_hours_end, 0)
WHERE is_active = true;
