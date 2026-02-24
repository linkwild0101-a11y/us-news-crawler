# StockOps P1 数据模型设计稿（Portfolio + Screener）

- 日期：2026-02-24
- 目标：落地 PRD P1 的持仓建议与策略筛选基础数据层，保证可解释、可回溯、可灰度。
- 关联文档：
  - `docs/plans/2026-02-24-stockops-integrated-iteration-plan.md`
  - `docs/plans/2026-02-24-stockops-detailed-prd.md`

## 1. 设计范围

1. Portfolio Intelligence（FR-301/302）
   - 组合主档、持仓明细、建议结果表。
   - 建议必须输出 2~3 条触发依据与失效条件。
2. Screener（FR-401/402/403）
   - 模板定义、运行记录、候选结果。
   - 预留 backtest 指标字段，先支持 preview 运行。
3. Macro Layer（FR-501/502）
   - 事件→行业→标的映射表，先落库，再逐步完善推理链。

## 2. 新增表（SQL）

对应迁移：`sql/2026-02-24_stock_p1_portfolio_screener_schema.sql`

1. `stock_portfolios_v1`
   - 组合层参数：风险偏好、单仓上限、总暴露等。
2. `stock_portfolio_holdings_v1`
   - 持仓明细：ticker、side、quantity、weight、止盈止损。
3. `stock_portfolio_advice_v1`
   - 建议输出：advice_type、priority_score、confidence、trigger_points、invalid_if。
4. `stock_screener_templates_v1`
   - 模板定义：event/trend/reversal + 默认过滤条件与打分权重。
5. `stock_screener_runs_v1`
   - 运行记录：run_mode、filters、metrics、candidate_count。
6. `stock_screener_candidates_v1`
   - 候选结果：score、confidence、risk_level、reason_points。
7. `stock_macro_impact_map_v1`
   - 宏观映射：macro_event_type、sector_code、ticker、impact_score。

## 3. 初始实现（本轮已交付）

1. 新增脚本 `scripts/stock_portfolio_advice_v1.py`
   - 基于 `stock_portfolio_holdings_v1` + `stock_opportunities_v2` 生成建议。
   - 输出 `add/reduce/hold/review/watch`，并写入 `stock_portfolio_advice_v1`。
   - 每条建议生成 2~3 条依据与失效条件。
2. 新增脚本 `scripts/stock_screener_run_v1.py`
   - 基于 `stock_screener_templates_v1` 对机会池执行参数化筛选。
   - 输出候选分数、理由点、回测代理指标（hit/drawdown/vol proxy）。
3. FastAPI 旁路 `apps/stockops_api/main.py`
   - 提供 `/health`、`/alerts`、`/alerts/{id}/feedback` 最小服务闭环。
4. Actions 接入可选步骤
   - `analysis-after-crawl.yml` 新增开关：`ENABLE_STOCK_P1_PORTFOLIO_ADVICE`。
   - 新增 `ENABLE_STOCK_P1_SCREENER`，可灰度启用筛选器。
   - 开启后自动跑建议脚本/筛选脚本，run_id 与主流程对齐。

## 4. 开关与执行建议

1. GitHub Variables 新增：`ENABLE_STOCK_P1_PORTFOLIO_ADVICE=true`（灰度）
2. 先执行 SQL，再触发 `Stock V2 Analysis After Crawl`
3. 首次建议建议只对 `system/default` 组合跑 1~2 天观察噪音率

## 5. 验收口径（P1 预检）

1. 数据完整性
   - `stock_portfolio_advice_v1` 每条记录必须包含 `trigger_points`（>=2）和 `invalid_if`。
2. 可解释性
   - 前端可直接消费 `trigger_points` 与 `payload.opportunity`。
3. 可运维性
   - run_id 可追溯到具体 Actions run。
   - 出错不阻塞主链路（continue-on-error）。

## 6. 下一步（Sprint D/E）

1. 增加组合输入 API（持仓增删改 + 风险偏好）
2. 增加 screener 执行脚本（模板参数化 + 候选打分）
3. 将 advice/screener 输出接入前端 Advice Center
4. 引入 FastAPI 旁路只读接口（/health, /advice, /screener/runs）
