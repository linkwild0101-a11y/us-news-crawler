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
- [ ] P2-5 Champion/Challenger 对照评分
- [ ] P2-6 漂移监控与自动告警
- [ ] P3-3 机会生命周期复盘报表
- [ ] P4-2 指标字典中心（前端可搜索）
- [ ] P4-3 订阅告警产品化（ticker/方向/等级）

## 验证命令

```bash
python3 -m py_compile scripts/*.py web/*.py
python3 scripts/stock_eval_v3.py --help
python3 scripts/stock_paper_trading_v3.py --help
```

## 风险

1. 评估口径 v1 为代理指标，需在后续版本引入真实收益标签
2. Paper Trading 价格来自 Stooq，盘中与收盘场景存在偏差
3. Workflow 增量步骤增加运行时长，需持续观察
