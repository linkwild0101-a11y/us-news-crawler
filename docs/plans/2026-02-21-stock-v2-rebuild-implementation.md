# Stock V2 重建实施计划（Implementation Plan）

- 日期: 2026-02-21
- 对应设计: `docs/plans/2026-02-21-stock-v2-rebuild-design.md`
- 目标: 用 `stock_*_v2` 并行链路重建美股分析能力，并平滑替换旧增强分析主链路

## 1. 实施原则

1. 不直接破坏现网：先并行、后切换、可回滚
2. 增量优先：跟随 crawler 触发，避免高频定时
3. 可追溯：所有产出写入 `run_id / as_of / source_refs`
4. 稳定优先：任一外部源失败不得阻断主链路

## 2. 里程碑

### M0（当天）基础冻结与准备
- [ ] 冻结旧增强链路入口（保留可手动触发）
- [ ] 新增 v2 配置开关（`ENABLE_STOCK_V2`, `DASHBOARD_READ_V2`）
- [ ] 创建 v2 数据库迁移草案

### M1（1-2天）Schema + Backfill 可跑通
- [ ] 建立 `stock_events_v2`
- [ ] 建立 `stock_event_tickers_v2`
- [ ] 建立 `stock_signals_v2`
- [ ] 建立 `stock_opportunities_v2`
- [ ] 建立 `stock_market_regime_v2`
- [ ] 建立 `stock_dashboard_snapshot_v2`
- [ ] 补齐索引、RLS、只读策略
- [ ] 完成全量 backfill 脚本（分批 checkpoint）

### M2（1-2天）Incremental + Workflow 接入
- [ ] 新建 `scripts/stock_pipeline_v2.py`（增量主入口）
- [ ] 新建 `scripts/stock_backfill_v2.py`（全量回填）
- [ ] 新建 `scripts/build_dashboard_snapshot_v2.py`
- [ ] 修改 `analysis-after-crawl.yml`：crawler 后触发 v2 增量
- [ ] 增加运行摘要（非空率、机会数、多空分布、耗时）

### M3（1天）前端灰度切换
- [ ] `frontend/lib/data.ts` 增加 v2 读取分支（feature flag）
- [ ] 首屏机会/信号优先读取 `stock_dashboard_snapshot_v2`
- [ ] 保留旧读取分支，支持一键回滚

### M4（7天）并行验证与切换
- [ ] 并行运行 7 天
- [ ] 对账：空白率、方向正确率、时延、任务成功率
- [ ] 达标后切换 `DASHBOARD_READ_V2=true`
- [ ] 下线旧增强分析定时触发（保留历史只读）

## 3. 代码级任务拆分

## 3.1 SQL / Migration
- [ ] 新增 `sql/2026-02-21_stock_v2_schema.sql`
- [ ] 新增 `sql/2026-02-21_stock_v2_indexes_policies.sql`

验收:
- 迁移可重复执行（幂等）
- RLS 对 anon/authenticated 仅 SELECT

## 3.2 Pipeline（核心）
- [ ] 新建 `scripts/stock_pipeline_v2.py`
  - [ ] `load_incremental_articles()`
  - [ ] `extract_stock_events()`
  - [ ] `map_event_tickers()`
  - [ ] `score_signals_mixed_engine()`（规则主分 + LLM修正）
  - [ ] `build_opportunities()`（A优先，多空同显）
  - [ ] `write_snapshot_v2()`
- [ ] 新建 `scripts/stock_backfill_v2.py`
  - [ ] 全量分页回填
  - [ ] `run_id` checkpoint

验收:
- 单次增量失败不清空历史有效结果
- 无新文章时仍可生成可读快照

## 3.3 Workflow / CI
- [ ] 修改 `.github/workflows/analysis-after-crawl.yml`
  - [ ] 用 `stock_pipeline_v2.py` 替代旧 enhanced 主入口
  - [ ] 增加指标 summary:
    - `opportunities_total`
    - `long_short_ratio`
    - `signals_non_empty_rate`
    - `pipeline_duration_sec`

验收:
- workflow 失败不超过 1%
- summary 可用于每日巡检

## 3.4 Frontend Data Switch
- [ ] 修改 `frontend/lib/types.ts` 增加 v2 snapshot 类型
- [ ] 修改 `frontend/lib/data.ts` 增加 `queryDashboardSnapshotV2`
- [ ] 增加环境开关读取逻辑

验收:
- 打开 `DASHBOARD_READ_V2` 后无需改 UI 即可吃到 v2 数据
- 关闭开关立即回退旧数据层

## 4. 数据质量与风控规则

- [ ] 去重键：`event_key/signal_key/opportunity_key`
- [ ] 时效控制：A=72h，B=14d（可配置）
- [ ] 空白保护：本轮无新增时保留有效 topN，并衰减置信度
- [ ] LLM 降级：超时/失败时自动 `llm_used=false`，保留规则分

## 5. 验证与测试

### 5.1 离线验证
- [ ] `python3 -m py_compile scripts/*.py web/*.py`
- [ ] 对 1k 历史文章跑 dry-run，记录耗时和产出分布

### 5.2 联调验证
- [ ] backfill 后人工抽样 50 条机会（方向正确率）
- [ ] 核对前端非空率（机会/信号/热点）

### 5.3 验收阈值（与设计一致）
- [ ] 非空率 >= 95%
- [ ] 方向正确率 >= 75%
- [ ] crawler 后 10-20 分钟刷新完成
- [ ] 连续 7 天成功率 >= 99%

## 6. 回滚预案

触发条件（任一满足）：
- 非空率连续 2 天 < 90%
- workflow 连续失败 > 3 次
- 前端关键模块出现结构性空白

回滚动作：
1. `DASHBOARD_READ_V2=false`
2. workflow 回切旧聚合步骤
3. 保留 `*_v2` 数据供排障，不删除

## 7. 执行顺序（建议）

1. 先做 SQL + backfill（M1）
2. 再做增量 pipeline + workflow（M2）
3. 再做前端开关读取（M3）
4. 最后做 7 天并行观察与切换（M4）

## 8. 交付物清单

- [ ] 设计文档（已完成）
- [ ] 实施计划（本文）
- [ ] v2 schema migration
- [ ] v2 backfill/incremental 脚本
- [ ] workflow 改造与 summary
- [ ] 前端 v2 数据开关接入
- [ ] 并行观察报告（7天）
