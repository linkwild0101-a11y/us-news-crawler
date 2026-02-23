# Paper Trading Protocol v1（规格草案）

- 日期: 2026-02-23
- 版本: v1
- 目标: 定义模拟交易链路输入、状态机与结果归档

## 1. 输入

- `stock_opportunities_v2` active TopN
- Stooq 实时近似收盘价（无认证）

## 2. 状态机

- `OPEN` -> `CLOSED`
- 触发条件: 到期、方向失配、手动终止

## 3. 明细落库

- `portfolio_paper_positions`
  - 开仓信息: ticker/side/horizon/entry_ts/entry_price
  - 持仓信息: mark_price/unrealized_pnl
  - 平仓信息: exit_ts/exit_price/realized_pnl

## 4. 聚合落库

- `portfolio_paper_metrics`
  - `open_count/closed_count`
  - `realized_pnl/unrealized_pnl`
  - `win_rate/gross_exposure`

## 5. 运行策略

1. 仅旁路运行（`ENABLE_STOCK_V3_PAPER=true`）
2. 失败不阻断 V2 主链路
3. 每次运行写 `run_id` 便于回放
