# Portfolio Constraints v1（规格草案）

- 日期: 2026-02-23
- 版本: v1
- 目标: 为 Paper Trading 设定可执行、可回放的组合约束

## 1. 仓位约束

1. 最大持仓数: 12
2. 单票权重上限: 15%
3. 总敞口上限: 100%
4. LONG/SHORT 单边上限: 70%

## 2. 开仓规则

- 仅从 active opportunities TopN 选取
- 需要有可用行情（entry price 非空）
- 同 ticker/horizon 不重复开仓

## 3. 平仓规则

1. 到期强平（`expires_at`）
2. 方向反转强平
3. 失效条件命中（后续扩展）

## 4. 指标输出

- `open_count/closed_count`
- `realized_pnl/unrealized_pnl`
- `win_rate`
- `gross_exposure`
