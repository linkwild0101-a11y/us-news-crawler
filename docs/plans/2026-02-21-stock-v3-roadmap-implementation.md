# Stock V3 技术路线实施方案（Implementation Plan）

- 日期: 2026-02-21
- 对应设计: `docs/plans/2026-02-21-stock-v3-roadmap-design.md`
- 目标: 在保持 Stock V2 稳定运行前提下，分阶段落地 V3（可复现研究 + 评估治理 + 组合闭环 + 产品化解释）

---

## 1. 实施边界与原则

## 1.1 边界

本方案仅覆盖：

1. 后端分析与评估系统演进
2. 数据模型与工作流编排演进
3. 前端决策支持与解释层演进

本方案不覆盖：

1. 自动实盘下单
2. 新增大量付费外部数据源
3. 多资产扩张（先聚焦美股）

## 1.2 原则

1. **并行不替换**：V3 先旁路验证，不直接替换 V2 主链路
2. **先度量后优化**：没有评估基线，不允许切换核心模型
3. **可回放可追责**：所有结果都能追溯到 run 参数与输入数据
4. **降级不空白**：任一子系统异常，不允许看板出现结构性空白

---

## 2. 总体实施节奏（12 周）

## Phase 0（W0，1-2天）基线冻结

- [ ] 固化 V2 当前基线版本（tag + config 快照）
- [ ] 建立 V3 feature flags（默认关闭）
- [ ] 建立路线周报模板（质量、时延、成功率）

## Phase 1（W1-W3）研究基础设施化

- [ ] `research_runs` 元数据体系
- [ ] 数据 Provider Registry 与 Source Health
- [ ] 事件本体 schema v1
- [ ] 分析运行可观测性（结构化日志 + run summary）

## Phase 2（W4-W6）评估与治理

- [ ] 离线评估协议（Hit Rate、Top-K、校准）
- [ ] Champion/Challenger 并行评分
- [ ] 漂移监控规则与告警阈值
- [ ] 评分卡与晋级门槛

## Phase 3（W7-W9）组合闭环与 Paper Trading

- [ ] 组合约束引擎（敞口/集中度/风险预算）
- [ ] Paper Trading 流程
- [ ] 机会生命周期状态机（生成→跟踪→失效→复盘）
- [ ] 归因报表（信号贡献/宏观过滤贡献/LLM贡献）

## Phase 4（W10-W12）前端决策体验升级

- [ ] 指标字典中心（Tooltip 已有，升级为可搜索中心）
- [ ] Why-Now 证据链详情页
- [ ] 订阅告警设计（ticker/方向/等级）
- [ ] 运营与值班手册

---

## 3. 工作流拆分（Workstreams）

## WS-A：Data Fabric（数据织网）

### 目标
把“脚本式数据拉取”升级为“统一可观测接入层”。

### 任务
- [ ] 定义 `provider_id/source_type/sla/error_budget` 元数据
- [ ] 抽象统一读取接口（行情/宏观/新闻）
- [ ] 失败策略：retry + fallback + stale 标记
- [ ] 输出 source_health 快照（可用率、延迟、缺失率）

### 交付物
- [ ] `docs/specs/provider-registry-v1.md`
- [ ] `docs/specs/source-health-sli-slo.md`

## WS-B：Research & Feature（研究与特征）

### 目标
每次 run 都可复现、可比较。

### 任务
- [ ] 新增 `research_runs`、`research_run_metrics`、`research_run_artifacts` 表设计
- [ ] run_id 贯穿：输入窗口、参数、版本、输出统计
- [ ] 事件本体升级（event taxonomy + evidence schema）
- [ ] 定义 run 对账报告格式

### 交付物
- [ ] `docs/specs/research-run-contract-v1.md`
- [ ] `docs/specs/event-taxonomy-v1.md`

## WS-C：Signal Governance（信号治理）

### 目标
建立模型晋级机制与稳定性红线。

### 任务
- [ ] 离线标签构造方案（收益窗口 + 方向标签）
- [ ] 评估指标与统计口径（LONG/SHORT 分开）
- [ ] Champion/Challenger A/B 对照模板
- [ ] Drift 监控（分布、密度、集中度）

### 交付物
- [ ] `docs/specs/offline-eval-protocol-v1.md`
- [ ] `docs/specs/model-promotion-gate-v1.md`

## WS-D：Portfolio & Paper Trading（组合与模拟交易）

### 目标
从“机会列表”升级为“可执行组合建议”。

### 任务
- [ ] 组合约束参数化（净敞口、行业上限、单票上限）
- [ ] 交易规则模板（入场/减仓/退出）
- [ ] Paper Trading 执行日志与绩效报表
- [ ] 失败样本复盘模板

### 交付物
- [ ] `docs/specs/portfolio-constraints-v1.md`
- [ ] `docs/specs/paper-trading-protocol-v1.md`

## WS-E：Frontend Decision UX（前端决策体验）

### 目标
让“为什么能做、什么时候失效”一眼可懂。

### 任务
- [ ] 指标字典中心（搜索 + 版本号 + 字段来源）
- [ ] 证据链页（事件→信号→机会→失效条件）
- [ ] 风险提示组件统一化（与现有 tooltip 对齐）
- [ ] 数据新鲜度/质量徽章

### 交付物
- [ ] `docs/specs/dashboard-explainability-v1.md`

---

## 4. 数据模型增量设计（V3）

## 4.1 新增表（建议）

1. `research_runs`
   - `run_id, pipeline_name, pipeline_version, started_at, ended_at, status, params_json, input_window, commit_sha`
2. `research_run_metrics`
   - `run_id, metric_name, metric_value, metric_unit, created_at`
3. `source_health_daily`
   - `source_id, date, success_rate, p95_latency_ms, freshness_sec, null_rate, status`
4. `signal_eval_snapshots`
   - `snapshot_id, signal_id, label_window, realized_return, hit_flag, calibration_bin, created_at`
5. `portfolio_paper_positions`
   - `position_id, run_id, ticker, side, entry_ts, entry_price, size, status, exit_ts, exit_price`
6. `portfolio_paper_metrics`
   - `run_id, pnl, sharpe, max_drawdown, turnover, win_rate, created_at`

## 4.2 兼容策略

- 不改写 `stock_*_v2` 主服务表
- V3 表与 V2 并行，通过 run_id 建关联
- 前端逐步消费 V3 聚合，不直接依赖实验中间表

---

## 5. Feature Flags 设计

- `ENABLE_STOCK_V3_RUN_LOG`：开启 run 元数据写入
- `ENABLE_STOCK_V3_EVAL`：开启评估与评分卡
- `ENABLE_STOCK_V3_PAPER`：开启模拟交易链路
- `NEXT_PUBLIC_DASHBOARD_V3_EXPLAIN`：开启前端 V3 解释中心

策略：

1. 默认全关
2. 先在 workflow_dispatch 开启验证
3. 达标后切换到自动触发

---

## 6. 工作流与调度设计

## 6.1 触发链路

1. RSS crawler 完成
2. 执行 V2 主链路（持续产出）
3. 旁路执行 V3 评估链路（不影响主结果）
4. 生成 run summary 与评估报告

## 6.2 任务拆分

- Job-A：ingest + event build（V2主）
- Job-B：eval + drift（V3旁路）
- Job-C：paper simulation（按日批）
- Job-D：frontend snapshot enrich（解释层）

## 6.3 失败策略

- Job-B/C/D 失败不影响 Job-A 成功
- 所有失败写入 run metrics + summary
- 连续失败超过阈值触发降级开关

---

## 7. 验收指标与门槛

## 7.1 系统稳定性

- 工作流成功率 >= 99%
- 主看板非空率 >= 95%
- crawler 后刷新延迟 P95 <= 20 分钟

## 7.2 策略有效性

- LONG/SHORT 分开 Hit Rate 在对照窗口内优于 V2 基线
- Top-K 机会命中率较 V2 提升（目标 +10% 相对提升）
- 置信度校准误差下降（ECE 下降）

## 7.3 决策可解释性

- 关键指标解释覆盖率 100%
- 机会详情证据链完整率 >= 95%

---

## 8. 测试计划

## 8.1 离线测试

- [ ] schema migration 幂等验证
- [ ] 1k/5k/10k 样本压力测试
- [ ] 回放测试（同 run 参数重复执行一致性）

## 8.2 联调测试

- [ ] workflow 全链路演练（含降级路径）
- [ ] 前端 V3 explain 开关回归
- [ ] 数据新鲜度与质量徽章校验

## 8.3 试运行测试

- [ ] 7 天 shadow run（V2主 + V3旁路）
- [ ] 每日评分卡自动汇总
- [ ] 异常案例复盘会

---

## 9. 回滚与应急

触发条件（任一）：

1. 非空率连续 2 天 < 90%
2. 评估链路造成主链路时延超标
3. 前端关键解释层导致明显可用性问题

回滚动作：

1. 关闭所有 V3 flags
2. 保持 V2 主链路运行
3. 冻结 V3 变更并导出 run artifacts 排障

---

## 10. 组织与节奏建议

建议按“周节奏 + 门禁评审”推进：

1. 每周一：里程碑评审（目标、风险、依赖）
2. 每周三：中期质量检查（指标快照）
3. 每周五：交付评审（是否达到 gate）

建议最少保留 1 周 buffer，用于数据口径与评估偏差修正。

---

## 11. 近期执行清单（接下来 10 个工作日）

1. [x] 完成 Phase 0 全部事项
2. [x] 输出 3 份规格文档（provider、run contract、eval protocol）
3. [x] 完成 `research_runs` 与 `source_health_daily` migration 草案
4. [x] 在现有 workflow 增加 run summary 骨架（不改主逻辑）
5. [x] 约定模型晋级门槛并冻结（v1 文档）
6. [ ] 产出第一版评分卡模板（CSV/Markdown）

---

## 12. 交付物清单

- [x] `docs/plans/2026-02-21-stock-v3-roadmap-design.md`（已完成）
- [x] `docs/plans/2026-02-21-stock-v3-roadmap-implementation.md`（本文）
- [x] provider registry 规格文档
- [x] research run contract 规格文档
- [x] eval protocol 与 promotion gate 文档
- [ ] workflow shadow run 报告（7天）
