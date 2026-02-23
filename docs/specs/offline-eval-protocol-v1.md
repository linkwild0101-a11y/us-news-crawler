# Offline Eval Protocol v1（规格草案）

- 日期: 2026-02-23
- 版本: v1
- 目标: 在不影响主链路的前提下，形成可重复的信号评估流程

## 1. 评估对象

- `stock_opportunities_v2`（历史机会）
- 当前活跃机会快照（同 ticker/horizon 对照）

## 2. 标签窗口

- 默认窗口: `24h_stability_proxy`
- 可扩展: `48h_stability_proxy`, `7d_stability_proxy`

## 3. 指标定义（v1 代理口径）

1. `eval_total`: 参与评估样本数
2. `eval_hit_rate_proxy`: 同 ticker/horizon 在窗口后方向一致率
3. `eval_long_hit_rate_proxy`: LONG 子集一致率
4. `eval_short_hit_rate_proxy`: SHORT 子集一致率
5. `eval_avg_return_proxy`: 机会分差转换的代理收益

## 4. 落库

- 明细表: `signal_eval_snapshots`
- 聚合指标: `research_run_metrics`（可选）

## 5. 运行规则

1. 评估链路仅旁路运行（`ENABLE_STOCK_V3_EVAL=true`）
2. 落库失败不得阻断主链路
3. 结果用于趋势比较，不直接驱动交易
