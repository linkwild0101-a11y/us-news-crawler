# Stock X 账号信息源设计（Top30 先行）

日期：2026-02-23

## 1. 目标

构建一个可持续的 X/Twitter 美股信息源通道，服务 `stock_events_v2 -> stock_signals_v2 -> stock_opportunities_v2`。

- 仅保留美股相关高价值账号
- 每 2 小时自动采集一次，分析流内再补抓一次
- 同时落地原始帖子与结构化信号，兼顾可审计与可用性

## 2. 范围（Phase-1）

- 输入账号池：`config/us_stock_x_accounts.tsv`
- 账号筛选：Top30（新闻10 / 量化期权8 / 宏观7 / 技术5）
- 每账号抓取：最近 20 条
- 数据落库：
  - `stock_x_accounts`
  - `stock_x_ingest_runs`
  - `stock_x_posts_raw`
  - `stock_x_post_signals`
  - `stock_x_account_health_daily`
- 信号映射：`stock_events_v2` + `stock_event_tickers_v2`

## 3. 核心流程

1. 从 TSV 读取账号元数据（类别、粉丝数、信号类型、价值说明）
2. 按评分模型选出 Top30（配额优先 + 全局补位）
3. 通过 Grok API 采集账号最近动态并抽取结构化信号
4. 写入原始帖子与结构化信号表
5. 将可交易信号映射到 `stock_events_v2`
6. 写入运行记录与数据源健康指标（`source_health_daily: x_grok_accounts`）

## 4. 调度

- `RSS Crawler`：改为每 2 小时执行（`5 */2 * * *`）
- 新增 `Stock X Source Ingest`：每 2 小时执行（`15 */2 * * *`）
- `analysis-after-crawl`：在 `stock_pipeline_v2` 前执行一次 X supplement ingest

## 5. 配置与密钥

GitHub Secrets：

- `SUPABASE_URL`
- `SUPABASE_KEY`
- `GROK_API_BASE_URL`
- `GROK_API_KEY`
- `GROK_MODEL`

GitHub Variables：

- `ENABLE_STOCK_X_SOURCE=true`

本地调试可回退读取：`grok_apikey.txt`（不入库，不提交）

## 6. 运行命令

```bash
# 仅导入 Top30 账号
python3 scripts/stock_x_source_ingest.py \
  --mode import \
  --accounts-file config/us_stock_x_accounts.tsv \
  --topn 30

# 全流程（导入 + 采集 + 映射）
python3 scripts/stock_x_source_ingest.py \
  --mode full \
  --accounts-file config/us_stock_x_accounts.tsv \
  --topn 30 \
  --post-limit 20 \
  --workers 6

# 仅采集（使用已激活账号）
python3 scripts/stock_x_source_ingest.py \
  --mode ingest \
  --topn 30 \
  --post-limit 20 \
  --workers 6
```

## 7. 后续迭代（Phase-2/3）

- Phase-2：信号质量治理
  - 引入账号可信度衰减、重复内容惩罚、时效衰减
  - 过滤非美股噪声（加黑名单与规则分类器）
- Phase-3：多源交叉验证
  - X 信号与新闻事件交叉打分
  - 仅对“多源共振”信号提升权重
- Phase-4：组合级执行
  - 将 X 驱动信号接入 V3 组合约束/订阅告警
  - 增加策略回放与收益归因（按 source_type 拆分）
