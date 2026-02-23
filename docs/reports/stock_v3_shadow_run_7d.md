# Stock V3 Shadow Run Report

- 统计窗口: 最近 7 天
- 生成时间(UTC): 2026-02-23T07:45:43.093384+00:00

## Pipeline 稳定性

| Pipeline | Runs | Success | Failed | Degraded | Success Rate | Avg Duration(s) |
|---|---:|---:|---:|---:|---:|---:|
| stock_pipeline_v2_incremental | 4 | 4 | 0 | 0 | 1.0 | 776.5 |
| stock_v3_champion_challenger | 2 | 2 | 0 | 0 | 1.0 | 0.0 |
| stock_v3_drift_monitor | 2 | 2 | 0 | 0 | 1.0 | 0.0 |
| stock_v3_lifecycle_report | 2 | 2 | 0 | 0 | 1.0 | 0.0 |
| stock_v3_paper_trading | 1 | 0 | 1 | 0 | 0.0 | 0.0 |
| stock_v3_portfolio_constraints | 1 | 1 | 0 | 0 | 1.0 | 0.0 |
| stock_v3_subscription_alert | 1 | 1 | 0 | 0 | 1.0 | 0.0 |

## 核心指标快照

| Metric | Latest | Avg | Samples | Latest Run | Latest Time |
|---|---:|---:|---:|---|---|
| eval_hit_rate_proxy | - | - | 0 | - | - |
| paper_realized_pnl | - | - | 0 | - | - |
| cc_challenger_win_rate | 0.3 | 0.2409 | 2 | gha-22295033890-1-cc | 2026-02-23T07:00:15.103532+00:00 |
| drift_critical_count | 0 | 0.0 | 2 | gha-22295033890-1-drift | 2026-02-23T07:00:17.511108+00:00 |
| lifecycle_active_count | 10 | 10.5 | 2 | gha-22295033890-1-lifecycle | 2026-02-23T07:00:19.663728+00:00 |
