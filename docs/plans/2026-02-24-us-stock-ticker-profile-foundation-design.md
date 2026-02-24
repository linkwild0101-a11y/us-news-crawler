# 美股代码基础数据库（Ticker Profile Foundation）设计方案

- 日期：2026-02-24
- 目标：解决看板中大量 `Unknown` 代码说明，构建可持续维护的美股代码基础数据库。

## 1. 设计结论（已确认）

- 方案：A（SEC + Nasdaq 自动同步 + 手工覆盖）
- 首期覆盖：S&P500 + Nasdaq100 + 持仓/关注列表
- 中文简介策略：模板优先，缺失时 LLM 补全
- 补全触发：每天定时批量
- 成本策略：不设硬上限（仅做并发、重试与失败保护）

## 2. 总体架构

- 主字典表：`stock_ticker_profiles_v1`
- 覆盖来源表：`stock_universe_members_v1`
- 待补全队列表：`stock_ticker_profile_enrich_queue_v1`
- 运行日志表：`stock_ticker_profile_sync_runs_v1`
- 手工覆盖文件：`config/stock_ticker_profile_overrides.tsv`

流程：
1) 汇总代码池（S&P500/Nasdaq100/持仓/watchlist/近期信号）
2) 拉取基础信息（SEC + Nasdaq）
3) 模板生成中文简介
4) 缺失/低质量入补全队列
5) 每日 LLM 批处理补全
6) 前端读取主字典展示

## 3. 数据模型

### 3.1 主字典 `stock_ticker_profiles_v1`

建议字段：
- `ticker`, `display_name`, `exchange`, `asset_type`
- `sector`, `industry`, `summary_cn`
- `summary_source`（`template|llm|manual`）
- `quality_score`
- `metadata`, `is_active`, `updated_at`

### 3.2 覆盖来源 `stock_universe_members_v1`

- `ticker`, `source_type`（`sp500|nasdaq100|portfolio|watchlist|recent_signal`）
- `source_ref`, `run_id`, `as_of`

### 3.3 补全队列 `stock_ticker_profile_enrich_queue_v1`

- `ticker`, `reason`（`missing_summary|low_quality|new_symbol`）
- `status`（`pending|running|done|failed`）
- `retry_count`, `last_error`, `next_retry_at`

### 3.4 运行日志 `stock_ticker_profile_sync_runs_v1`

- `run_id`, `input_count`, `updated_count`, `queued_count`
- `llm_success_count`, `llm_failed_count`, `duration_sec`
- `error_summary`, `as_of`

## 4. 同步与补全策略

### A. 代码池构建

合并并去重以下来源：
- S&P500
- Nasdaq100
- 当前持仓
- watchlist
- 最近 7 天机会/提醒中出现代码

### B. 基础信息同步（无 LLM）

- 从 SEC + Nasdaq 拉取：代码、公司名、交易所
- 资产类型、行业优先使用规则与手工覆盖

### C. 中文简介（混合）

- 模板生成：`资产类型 + 行业 + 关注要点`
- 缺失/低质量进入队列

### D. LLM 批处理

- 每日定时消费队列
- 并发执行、失败重试、退避
- 成功回写 `summary_cn`, `summary_source=llm`, `quality_score`

### E. 前端展示

- 优先显示 `display_name + sector + summary_cn`
- 无 profile 或 summary 为空时回退默认文案

## 5. 质量门禁与监控

质量目标：
- Top 卡片 `Unknown` 占比 < 5%
- 覆盖池 `summary_cn` 覆盖率 > 95%
- 同步失败率 < 2%

监控与告警：
- 每日 run summary（处理、更新、入队、补全成功/失败、耗时）
- 连续失败 >= 3 次触发飞书告警

## 6. 回滚与降级

- 外部源失败：保留旧字典值，记录错误，不阻断看板
- LLM失败：保留模板/旧值，等待下次补全
- 前端始终可回退默认文案，保证可读性

## 7. 验收标准

- 连续运行 2~3 个日批后，Unknown 比例稳定下降
- 抽样 100 个代码，中文简介可读且方向正确
- 看板关键卡片（机会/提醒/持仓）显示名称与简介稳定
