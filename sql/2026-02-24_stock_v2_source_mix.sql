-- Stock V2 source mix extension
-- 日期: 2026-02-24

ALTER TABLE IF EXISTS stock_signals_v2
    ADD COLUMN IF NOT EXISTS source_mix JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE IF EXISTS stock_opportunities_v2
    ADD COLUMN IF NOT EXISTS source_mix JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN stock_signals_v2.source_mix IS '信号来源构成（X/News 占比与账号摘要）';
COMMENT ON COLUMN stock_opportunities_v2.source_mix IS '机会来源构成（继承自信号层）';
