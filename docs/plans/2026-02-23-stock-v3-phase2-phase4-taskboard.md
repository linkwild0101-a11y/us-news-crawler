# Stock V3 Phase 2-4 执行看板（持续更新）

- 日期: 2026-02-23
- 上游文档: `docs/plans/2026-02-21-stock-v3-roadmap-implementation.md`

## 当前进展

- [x] P2-1 离线评估协议文档（`offline-eval-protocol-v1.md`）
- [x] P2-2 模型晋级门禁文档（`model-promotion-gate-v1.md`）
- [x] P2-3 评估/纸上交易表 migration 草案（`sql/2026-02-23_stock_v3_eval_paper_tables.sql`）
- [x] P2-4 评估脚本最小实现（`scripts/stock_eval_v3.py`）
- [x] P3-1 Paper Trading 脚本最小实现（`scripts/stock_paper_trading_v3.py`）
- [x] P3-2 workflow 旁路接入（eval/paper 开关控制）
- [x] P4-1 explainability 规格文档（`dashboard-explainability-v1.md`）
- [x] P2-5 Champion/Challenger 对照评分（`scripts/stock_champion_challenger_v3.py`）
- [x] P2-6 漂移监控与自动告警（`scripts/stock_drift_monitor_v3.py`）
- [x] P3-3 机会生命周期复盘报表（`scripts/stock_lifecycle_report_v3.py`）
- [x] P4-2 指标字典中心（前端可搜索，`MetricDictionaryCenter`）
- [x] P4-3 订阅告警产品化（ticker/方向/等级，`scripts/stock_subscription_alert_v3.py`）
- [x] P3-4 组合约束参数化引擎（`scripts/stock_portfolio_constraints_v3.py`）
- [x] P4-4 Why-Now 证据链详情抽屉（前端机会卡可展开）
- [x] P4-5 数据新鲜度/质量徽章（freshness + source health）
- [x] P2-7 每日评分卡脚本（`scripts/stock_daily_scorecard_v3.py`）
- [x] P2-8 7日 shadow-run 报告脚本（`scripts/stock_shadow_run_report_v3.py`）
- [x] P2-9 V3 验证套件（`scripts/stock_v3_validation_suite.py`）
- [x] P3-5 workflow 增加 constraints/scorecard/shadow/validation 可选步骤

## 验证命令

```bash
python3 -m py_compile scripts/*.py web/*.py
python3 scripts/stock_eval_v3.py --help
python3 scripts/stock_paper_trading_v3.py --help
python3 scripts/stock_champion_challenger_v3.py --help
python3 scripts/stock_drift_monitor_v3.py --help
python3 scripts/stock_lifecycle_report_v3.py --help
python3 scripts/stock_subscription_alert_v3.py --help
python3 scripts/stock_portfolio_constraints_v3.py --help
python3 scripts/stock_daily_scorecard_v3.py --help
python3 scripts/stock_shadow_run_report_v3.py --help
python3 scripts/stock_v3_validation_suite.py --help
```

## 风险

1. 评估口径 v1 仍含代理指标，需在后续版本引入真实收益标签
2. Paper Trading 价格来自 Stooq，盘中与收盘场景存在偏差
3. 订阅告警依赖 webhook 配置，建议先 `--dry-run` 验证再开启自动触发
4. `portfolio_paper_positions` / `portfolio_constraint_snapshots` 需先在 Supabase 执行 migration
