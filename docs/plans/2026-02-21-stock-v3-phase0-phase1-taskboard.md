# Stock V3 Phase 0 + Phase 1 执行任务看板（可直接执行）

- 日期: 2026-02-21
- 适用范围: `Stock V3` 路线的前 10 个工作日（Phase 0 + Phase 1）
- 上游文档:
  - `docs/plans/2026-02-21-stock-v3-roadmap-design.md`
  - `docs/plans/2026-02-21-stock-v3-roadmap-implementation.md`

---

## 1. 本阶段目标（10 个工作日）

1. 冻结 V2 生产基线（可回滚）
2. 建立 V3 最小可用“研究运行追踪”能力（run metadata）
3. 建立数据源健康度基础能力（source health）
4. 不影响当前 V2 主链路稳定运行

## 执行进展（2026-02-21）

- [x] P0-1 冻结 V2 基线（tag: `stock-v2-baseline-2026-02-21`）
- [x] P0-2 接入 V3 feature flags（默认关闭）
- [x] P0-3 周报/Gate 模板落盘
- [ ] Phase 1 任务执行中

---

## 2. 看板规则

### 2.1 任务状态

- `READY`: 可开工
- `IN_PROGRESS`: 执行中
- `BLOCKED`: 被依赖阻塞
- `DONE`: 验收通过

### 2.2 完成定义（DoD）

每个任务必须同时满足：

1. 文档更新（设计/规格/Runbook）
2. 代码或配置落地
3. 可重复验证命令可执行
4. 回滚路径明确

---

## 3. Phase 0（W0）任务清单

## P0-1 冻结 V2 基线

- 状态: `READY`
- 优先级: P0
- 依赖: 无
- 输出:
  - Git tag（例如 `stock-v2-baseline-2026-02-21`）
  - `baseline-manifest`（commit、workflow、关键 env）
- DoD:
  - 可一键定位到当前 V2 线上版本
  - 回滚命令可用

## P0-2 建立 V3 Feature Flags

- 状态: `READY`
- 优先级: P0
- 依赖: P0-1
- 输出:
  - `ENABLE_STOCK_V3_RUN_LOG`
  - `ENABLE_STOCK_V3_EVAL`
  - `ENABLE_STOCK_V3_PAPER`
  - `NEXT_PUBLIC_DASHBOARD_V3_EXPLAIN`
- DoD:
  - 默认全关闭
  - 关闭时系统行为与当前 V2 完全一致

## P0-3 周报与门禁模板

- 状态: `READY`
- 优先级: P1
- 依赖: 无
- 输出:
  - 周报模板（稳定性、时延、质量、风险）
  - Gate 评审模板（Go/No-Go）
- DoD:
  - 每周可复用，字段稳定

---

## 4. Phase 1（W1-W3）任务清单

## P1-1 Provider Registry 规格文档

- 状态: `READY`
- 优先级: P0
- 依赖: P0-2
- 输出: `docs/specs/provider-registry-v1.md`
- 核心字段:
  - `provider_id, source_type, endpoint, auth_type, sla_target, retry_policy, fallback_policy`
- DoD:
  - 所有现有源可映射到统一字段

## P1-2 Source Health 指标定义

- 状态: `READY`
- 优先级: P0
- 依赖: P1-1
- 输出: `docs/specs/source-health-sli-slo.md`
- 核心指标:
  - `success_rate, p95_latency_ms, freshness_sec, null_rate, status`
- DoD:
  - 指标口径可直接用于日报/告警

## P1-3 Research Run Contract 规格

- 状态: `READY`
- 优先级: P0
- 依赖: P0-1
- 输出: `docs/specs/research-run-contract-v1.md`
- 核心字段:
  - `run_id, pipeline_name, pipeline_version, params_json, input_window, started_at, ended_at, status`
- DoD:
  - 可覆盖 incremental/backfill 两类 run

## P1-4 数据库迁移草案（V3 基础表）

- 状态: `READY`
- 优先级: P0
- 依赖: P1-2, P1-3
- 输出:
  - `sql/2026-xx-xx_stock_v3_run_tables.sql`
  - `sql/2026-xx-xx_stock_v3_health_tables.sql`
- DoD:
  - 幂等可重复执行
  - 只新增，不破坏 V2 表

## P1-5 Run Logger 最小实现

- 状态: `READY`
- 优先级: P0
- 依赖: P1-3, P1-4
- 输出:
  - 在 `stock_pipeline_v2` 增加可选 run metadata 写入（flag 控制）
- DoD:
  - 开关关闭时零行为变化
  - 开关开启时可看到 run 完整记录

## P1-6 Source Health Collector 最小实现

- 状态: `READY`
- 优先级: P1
- 依赖: P1-2, P1-4
- 输出:
  - 每次 workflow 汇总一次 source health 快照
- DoD:
  - 至少覆盖当前已用关键源（行情/宏观/新闻输入）

## P1-7 Workflow 旁路接入（不影响主链路）

- 状态: `READY`
- 优先级: P0
- 依赖: P1-5, P1-6
- 输出:
  - workflow 增加 V3 旁路 job（允许失败，不阻断主 job）
- DoD:
  - 主链路成功率不下降
  - 旁路结果可见于 step summary

## P1-8 Run Summary 输出标准化

- 状态: `READY`
- 优先级: P1
- 依赖: P1-7
- 输出:
  - 固定 summary 字段（时延、非空率、signals/opps、source health）
- DoD:
  - 每次 run 输出结构一致，可机器读取

---

## 5. 10 个工作日排期建议

### Day 1-2
- P0-1, P0-2, P0-3

### Day 3-4
- P1-1, P1-2, P1-3

### Day 5-6
- P1-4, P1-5（第一版）

### Day 7-8
- P1-6, P1-7

### Day 9-10
- P1-8 + 联调回归 + Gate 评审

---

## 6. 关键验收门禁（Phase 0 + 1）

## Gate-A（Day 2）

- [ ] V2 baseline 已冻结
- [ ] V3 flags 已接入且默认关闭
- [ ] 回滚说明可执行

## Gate-B（Day 6）

- [ ] run metadata 表已可写
- [ ] incremental run 可记录参数与状态
- [ ] 关闭 flag 时行为一致

## Gate-C（Day 10）

- [ ] workflow 旁路 job 已稳定运行
- [ ] source health 可输出快照
- [ ] 主链路成功率与时延无明显退化

---

## 7. 验证命令（建议）

```bash
# Python 语法检查
python3 -m py_compile scripts/*.py web/*.py

# 前端基础检查
cd frontend && npm run typecheck && npm run lint && npm run build

# 运行 V2 增量（基线对照）
python3 scripts/stock_pipeline_v2.py --mode incremental --hours 168 --article-limit 2000 --lookback-hours 336

# （落地后）开启 run-log 的旁路验证
# ENABLE_STOCK_V3_RUN_LOG=true python3 scripts/stock_pipeline_v2.py ...
```

---

## 8. 风险与阻塞点

1. **字段口径不统一**
   - 对策: 先冻结 contract，再实现
2. **workflow 时延被拉长**
   - 对策: 旁路 job `continue-on-error`，并限制执行预算
3. **观测数据过多影响可读性**
   - 对策: summary 只保留核心指标，详细数据落表

---

## 9. 执行职责建议

1. 后端 owner: P1-4/P1-5/P1-6
2. 平台 owner: P1-7/P1-8
3. 产品 owner: P0-3（周报与 gate）
4. 全员评审: Gate-A/B/C

---

## 10. 下一步（进入 Phase 2 的入口）

当 Gate-C 通过后，立即启动：

1. `offline-eval-protocol-v1.md`
2. `model-promotion-gate-v1.md`
3. Champion/Challenger 对照运行（7 天）
