# Research Run Contract v1（规格草案）

- 日期: 2026-02-21
- 版本: v1
- 目标: 为每次分析运行提供可复现、可追溯、可对账的统一契约

## 1. run 主记录字段（research_runs）

1. `run_id`（唯一）
2. `pipeline_name`（如 `stock_pipeline_v2_incremental`）
3. `pipeline_version`（语义版本或 git sha）
4. `trigger_type`（`workflow_run|workflow_dispatch|manual`）
5. `status`（`running|success|failed|degraded`）
6. `started_at` / `ended_at`
7. `duration_sec`
8. `input_window`（JSON，包含 hours/lookback/limit）
9. `params_json`（CLI 参数与 flags 快照）
10. `commit_sha`
11. `notes`

## 2. run 指标字段（research_run_metrics）

1. `run_id`
2. `metric_name`（如 `signals_written`）
3. `metric_value`
4. `metric_unit`（`count|sec|ratio`）
5. `created_at`

建议首批指标：

- `articles_seen`
- `stock_articles`
- `events_upserted`
- `signals_written`
- `opportunities_written`
- `pipeline_duration_sec`

## 3. run 附件字段（research_run_artifacts）

1. `run_id`
2. `artifact_type`（`summary_md|metrics_json|error_log|diff_report`）
3. `artifact_ref`（路径或对象存储 URL）
4. `checksum`
5. `created_at`

## 4. 写入时机

1. run 启动：写 `running`
2. 核心阶段完成：持续 upsert metrics
3. run 结束：写 `success/failed/degraded` 与结束时间

## 5. 兼容要求

1. `ENABLE_STOCK_V3_RUN_LOG=false` 时不写入（零行为变更）
2. 写入失败不得阻断 V2 主链路
3. 同一 run_id 的重复提交应幂等

## 6. 对账最小查询

按 `run_id` 可一次拿到：

1. 参数快照
2. 输入窗口
3. 核心产出指标
4. 失败信息与摘要链接
