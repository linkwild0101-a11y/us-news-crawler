# US-Monitor 美股看板分析能力重建设计（Stock V2）

- 日期: 2026-02-21
- 目标: 放弃原增强分析主链路，基于现有爬取数据与现有免费信号源，重建服务美股机会看板的专用分析能力
- 适用范围: 后端分析、聚合层、工作流编排、前端数据读取切换

## 1. 已确认的关键决策

1. 历史重建范围: **全量历史**
2. 旧链路策略: **不再以现有 analyzer/enhanced_analyzer 作为主入口**，重建美股专用流水线
3. 信号源范围: **仅使用现有 articles 与已接入免费信号源**（不新增外部源）
4. 数据切换策略: **并行 `*_v2` 表**，验证后切换
5. 调度策略: **随 crawler 触发增量更新**（非固定小时任务）
6. 验收目标: **可用性/质量/时效三者平衡**
7. 算法策略: **混合引擎**（规则/统计主评分 + LLM 语义增强修正）

## 2. 设计目标与非目标

### 2.1 目标

- 输出稳定、可解释、面向交易决策的美股信号与机会
- 保证看板高可用（减少空白）且不过期污染
- 保持增量更新效率，支持 crawler 完成后快速刷新
- 提供可回放与可追溯能力（run_id/source_refs）

### 2.2 非目标

- 本阶段不新增第三方付费数据源
- 不做高频/分钟级交易信号
- 不在本阶段改动移动端视觉设计（仅数据供给）

## 3. 总体架构

新增独立流水线 `stock_pipeline_v2`，分为三层：

1. Raw Layer
   - 输入: `articles` + 现有免费信号源抓取结果
2. Feature Layer
   - 事件抽取、ticker 归因、方向/情绪、宏观状态、去重与时效特征
3. Serve Layer
   - `stock_signals_v2`、`stock_opportunities_v2`、`stock_dashboard_snapshot_v2` 等供前端直读

策略上采用：
- 规则/统计模型做主分（稳定、可回放）
- LLM 仅负责语义增强、方向纠偏、解释生成与置信度校准

## 4. 数据模型（并行 v2）

建议新增 6 张核心表：

1. `stock_events_v2`
   - 字段建议: `id, event_key, source_type, source_ref, event_type, direction, strength, ttl_hours, summary, details, as_of, run_id, created_at, updated_at`
2. `stock_event_tickers_v2`
   - 字段建议: `id, event_id, ticker, role, weight, confidence, as_of, run_id, created_at`
3. `stock_signals_v2`
   - 字段建议: `id, signal_key, ticker, level, side, signal_score, confidence, trigger_factors, llm_used, explanation, expires_at, as_of, run_id, created_at, updated_at`
4. `stock_opportunities_v2`
   - 字段建议: `id, opportunity_key, ticker, side, horizon, opportunity_score, confidence, risk_level, why_now, invalid_if, catalysts, source_signal_ids, source_event_ids, expires_at, as_of, run_id, created_at, updated_at`
5. `stock_market_regime_v2`
   - 字段建议: `regime_date, risk_state, vol_state, liquidity_state, regime_score, summary, source_payload, run_id, created_at, updated_at`
6. `stock_dashboard_snapshot_v2`
   - 字段建议: `snapshot_time, top_opportunities, top_signals, market_brief, risk_badge, data_health, run_id, created_at`

通用要求：
- 所有表保留 `as_of` / `run_id` / `source_refs` 可追溯字段
- RLS 仅开放只读策略给 `anon, authenticated`

## 5. 增量流程与评分逻辑

每次 crawler 完成后执行：

1. 读取本轮新增文章 + 有效期内未过期事件
2. 规则层处理
   - 美股相关过滤
   - 事件分类（财报/监管/宏观/行业/资金）
   - ticker 归因与权重
3. LLM 层处理
   - 方向判断（多/空/中性）
   - 事件强度、时效语义
   - 解释文本与置信度修正
4. 分数融合
   - `signal_score = base_score + llm_adjust`（裁剪到[0,100]）
   - `opportunity_score = f(signal_score, regime, flow, concentration)`
5. 写入 `stock_signals_v2` / `stock_opportunities_v2`
6. 生成 `stock_dashboard_snapshot_v2`

关键业务规则：
- A horizon 优先排序
- LONG/SHORT 同时输出
- 去重强化：同一事件重复出现 -> 提升置信度而非重复灌库

## 6. 兜底与稳定性设计

1. 无新文章
   - 不清空 v2 结果，保留有效窗口内 topN，按时间衰减置信度
2. 单源失败
   - 不中断主流程，记录 `source_health`
3. LLM 失败
   - 回退规则分，标记 `llm_used=false`
4. 数据异常
   - 极值截断、空值回退、最低输出阈值

## 7. 验收指标（平衡目标）

- 可用性: 看板关键模块非空率 >= 95%
- 质量: 抽样方向准确率（LONG/SHORT）>= 75%
- 时效: crawler 完成后 10-20 分钟内完成增量刷新
- 稳定性: 连续 7 天任务成功率 >= 99%

## 8. 切换与回滚策略

Phase 1: 全量历史回填至 `*_v2`
- 不影响现网读取

Phase 2: 并行运行与对比（建议 7 天）
- 对比空白率、方向一致性、刷新时延

Phase 3: 前端切读 `*_v2`
- 保留 feature flag（可一键切回旧聚合）

Phase 4: 下线旧增强主链路
- 旧表保留只读历史

## 9. 风险与缓解

1. 全量回填耗时长
- 采用分批回填 + run checkpoint

2. LLM 结果波动
- 固定提示模板 + 低温度 + 规则分兜底

3. 无新数据时看板空白
- 保留有效窗口策略 + snapshot 兜底

4. 迁移期间口径不一致
- 并行对账报表 + 指标门槛后再切换

## 10. 下一步

1. 产出实施计划（任务拆分、里程碑、回滚点）
2. 编写 v2 schema migration
3. 实现 stock_pipeline_v2（backfill + incremental）
4. 接入 workflow 并加指标上报
5. 前端切换到 v2 读取层
