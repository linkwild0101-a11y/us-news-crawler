# Stock V3 运维值班手册（Ops Runbook）

- 日期: 2026-02-23
- 适用范围: `analysis-after-crawl.yml` 中的 Stock V3 旁路步骤

## 1. 值班目标

1. 保证 V2 主链路稳定产出（signals/opportunities 不空白）
2. 保障 V3 旁路指标可用（eval/paper/drift/challenger/lifecycle/subscription）
3. 对关键异常进行 30 分钟内定位并执行降级

## 2. 关键开关（GitHub Repository Variables）

- 核心: `ENABLE_STOCK_V3_RUN_LOG` / `ENABLE_STOCK_V3_EVAL` / `ENABLE_STOCK_V3_PAPER`
- 治理: `ENABLE_STOCK_V3_CHALLENGER` / `ENABLE_STOCK_V3_DRIFT` / `ENABLE_STOCK_V3_LIFECYCLE`
- 通知: `ENABLE_STOCK_V3_SUBSCRIPTION_ALERT`
- 扩展: `ENABLE_STOCK_V3_CONSTRAINTS` / `ENABLE_STOCK_V3_SCORECARD` / `ENABLE_STOCK_V3_SHADOW_REPORT` / `ENABLE_STOCK_V3_VALIDATION`

默认建议：

- 日常自动运行: 打开 `RUN_LOG/EVAL/PAPER/CHALLENGER/DRIFT/LIFECYCLE/SUBSCRIPTION_ALERT`
- 周期报告: 按需打开 `SCORECARD/SHADOW_REPORT`
- 验证压测: 仅手动触发时打开 `VALIDATION`

## 3. 每日巡检清单

1. GitHub Actions 最近一次 `Stock V2 Analysis After Crawl` 结论为 `success`
2. `stock_dashboard_snapshot_v2` 有当天快照，`stock_signals_v2` / `stock_opportunities_v2` 非空
3. `source_health_daily` 的 H/D/C 分布无持续 `critical`
4. `research_run_metrics` 有当日新增（eval/paper/drift/challenger/lifecycle/subscription）
5. 飞书通知收到运行摘要；若开启订阅告警，`stock_alert_delivery_logs` 有 sent 记录

## 4. 常见告警与处理

### 4.1 增量分析超时或卡慢

处理顺序：

1. 保持 V2 主链路；临时关闭耗时旁路（`ENABLE_STOCK_V3_*`）
2. 下调增量参数（`--article-limit`、`--llm-event-cap`）
3. 复跑 workflow_dispatch 验证

### 4.2 source health 出现 critical

处理顺序：

1. 查看 `source_health_daily` 对应 source_id
2. 若是外部源不可用，保留 fallback，避免看板空白
3. 连续 3 次 critical 时，将相关旁路步骤置 `false`

### 4.3 订阅告警未发送

处理顺序：

1. 检查 `stock_alert_subscriptions` 是否存在 `is_active=true`
2. 检查 `FEISHU_WEBHOOK_URL` secret 是否有效
3. 查 `stock_alert_delivery_logs` 的 `status/response_text`

## 5. 回滚策略

1. 立即将所有 V3 Variables 设为 `false`
2. 仅保留 V2 主链路
3. 导出最近 24h run 指标，记录事件时间线
4. 排障完成后按顺序逐个恢复：RUN_LOG → EVAL/PAPER → CHALLENGER/DRIFT/LIFECYCLE → SUBSCRIPTION

## 6. 本地验证命令

```bash
python3 -m py_compile scripts/*.py web/*.py
python3 scripts/stock_eval_v3.py --help
python3 scripts/stock_paper_trading_v3.py --help
python3 scripts/stock_portfolio_constraints_v3.py --help
python3 scripts/stock_daily_scorecard_v3.py --help
python3 scripts/stock_shadow_run_report_v3.py --help
python3 scripts/stock_v3_validation_suite.py --help
```

## 7. 资料索引

- 工作流: `.github/workflows/analysis-after-crawl.yml`
- 评分卡: `scripts/stock_daily_scorecard_v3.py`
- Shadow 报告: `scripts/stock_shadow_run_report_v3.py`
- 验证套件: `scripts/stock_v3_validation_suite.py`
- 通知: `scripts/stock_v3_notifier.py`, `scripts/stock_subscription_alert_v3.py`
