# StockOps × US-Monitor 一体化迭代方案（PRD 对齐版，P0-P2）

- 日期：2026-02-24（更新）
- 版本：v2.0
- 输入来源：
  - `docs/plans/2026-02-24-stockops-p0-mvp.md`
  - `docs/plans/2026-02-24-stockops-detailed-prd.md`
  - 当前主线代码与已落地改动（Stock V2/V3 + X 信源 + Alert V1）

---

## 1. 目标与整合原则

1. **单仓主线推进**：继续并入 `us-news-crawler` 主线，不拆新系统。
2. **P0 先闭环，再扩能力**：先稳定“提醒生成 → 去重投递 → 用户反馈”。
3. **PRD 全量对齐**：将详细 PRD 的 P0/P1/P2 目标映射到可执行 Sprint。
4. **技术演进渐进式**：P0 保持 scripts+Supabase，P1 再引入 FastAPI 旁路。

---

## 2. 当前基线（已完成）

### 2.1 已落地能力

- P0 数据层：`stock_alert_rules_v1 / events_v1 / delivery_v1 / feedback_v1 / user_prefs_v1`
- P0 引擎层：
  - `scripts/stock_alert_engine_v1.py`
  - `scripts/stock_alert_dispatch_v1.py`
- P0 调度层：`analysis-after-crawl.yml` 已支持 `ENABLE_STOCK_ALERT_V1`
- P0 前端层（Sprint B MVP）：
  - Dashboard 新增 Alerts Tab（提醒中心）
  - 提醒过滤、已读、反馈入口（有用/噪音）
  - API：`frontend/app/api/alerts/feedback/route.ts`

### 2.2 当前缺口

- 缺反馈聚合与阈值调优脚本（`stock_alert_feedback_agg_v1.py`）
- 缺盘前/盘后与每日上限治理在 UI/策略层的完整贯通
- 缺 P1 的持仓建议、策略筛选器、宏观影响层与实验框架
- 缺 P2 自动化执行与风控闸门主链路

### 2.3 最新进展（2026-02-24）

- P0 反馈日报/周报已落地并接入 workflow 可选步骤。
- P1 数据层已启动：新增 `portfolio + screener + macro map` SQL 草案。
- P1 建议引擎 MVP 已落地：`scripts/stock_portfolio_advice_v1.py`。
- P0 KPI 基础设施已启动：`alert_open_events + kpi_view + kpi_report`。
- P1 筛选器 MVP 与 FastAPI 旁路已落地（可灰度开关）。

---

## 3. PRD 到迭代方案映射（总览）

### 3.1 时间窗对齐（沿用 PRD）

- **P0：2026-02-24 ~ 2026-03-22**
- **P1：2026-03-23 ~ 2026-04-19**
- **P2：2026-04-20 ~ 2026-05-17**

### 3.2 能力映射

- PRD P0（提醒+解释+反馈）→ 当前 Sprint A/B/C
- PRD P1（Advice/Screener/Macro/A-B）→ 新增 Sprint D/E
- PRD P2（Automation/Risk/Broker）→ 新增 Sprint F/G

---

## 4. P0 交付计划（到 2026-03-22）

## Sprint A（已完成）— 规则与去重骨架

- SQL 迁移 + Alert Engine + Dispatch + Actions 开关
- 对应 PRD：FR-001/002/003 的基础实现

## Sprint B（进行中）— 提醒中心与反馈入口

- 已完成：
  - 前端提醒中心（列表/过滤/已读）
  - 反馈按钮（有用/噪音）
  - 反馈写入 API
- 待完成：
  - `stock_alert_feedback_agg_v1.py`
  - 每日阈值建议报告（输出 `docs/reports/`）
- 对应 PRD：FR-004、用户流程 7.1 第 3~6 步

## Sprint C（待执行）— 时段治理与通知质量

1. 盘前/盘后开关全链路打通（规则 + 用户偏好 + 前端）
2. 每日提醒上限与静默时段策略
3. 飞书通知模板升级（why-now、风险、失效条件、原文）
4. 噪音反馈率周报（noise ratio）

**P0 验收（与 PRD KPI 合并）**

- 告警延迟 p95 < 60s
- 提醒 CTR >= 18%
- 噪音反馈率 <= 30%
- 7 日留存 >= 25%（看板活跃口径）

---

## 5. P1 交付计划（2026-03-23 ~ 2026-04-19）

## Sprint D — Portfolio Intelligence + Macro Layer

1. 持仓输入模型（watchlist/portfolio）
2. 持仓驱动建议生成（优先级+解释+风险提示）
3. 宏观事件三级映射（事件→行业→标的）
4. 建议卡支持“触发依据 2~3 条”强制输出

**对应 PRD**：FR-301/302、FR-501/502

## Sprint E — Screener + 实验平台 + FastAPI 旁路

1. 策略筛选器模板（事件驱动/趋势/反转）
2. 参数化筛选（阈值、窗口、流动性过滤）
3. 回测预览 MVP（命中率/回撤/波动）
4. FastAPI 最小服务：
   - `GET /health`
   - `GET /alerts`
   - `POST /alerts/{id}/feedback`
5. A/B 实验埋点：建议排序与文案版本

**对应 PRD**：FR-401/402/403 + P1 实验平台要求

**P1 验收（PRD 对齐）**

- 建议点击率 >= 20%
- 建议采纳率 >= 12%
- 宏观卡片打开率 >= 15%
- 噪音反馈率 <= 25%

---

## 6. P2 交付计划（2026-04-20 ~ 2026-05-17）

## Sprint F — 自动化执行与风控闸门

1. 模拟盘执行主链路（paper 默认）
2. 风控前置拦截（仓位/回撤/单笔风险）
3. 审计日志标准化（输入、触发、风控、订单）

**对应 PRD**：FR-601/602/603

## Sprint G — Broker 适配与专业扩展

1. 首批券商接入（建议先单券商 MVP）
2. 社区共识层（来源权重与一致性聚合）
3. 期权扩展（标签级，不做重度 Greeks 引擎）

**P2 验收（PRD 对齐）**

- 自动化执行成功率 >= 99%
- 风控拦截准确率 >= 95%
- P2 功能 30 日留存 >= 35%
- Pro 转化率 >= 6%

---

## 7. 技术架构落地策略（与现状兼容）

### 7.1 P0-P1 过渡期

- 保留：`scripts/stock_pipeline_v2.py`、`scripts/stock_x_source_ingest.py`
- 新增：Alert/Feedback 聚合脚本，不破坏现有 V2/V3 表结构
- 前端优先直连 Supabase，FastAPI 仅做可回退旁路

### 7.2 Feature Flags

- `ENABLE_STOCK_ALERT_V1`
- `NEXT_PUBLIC_ENABLE_STOCK_EVIDENCE_LAYER`
- `NEXT_PUBLIC_ENABLE_STOCK_TRANSMISSION_LAYER`
- `NEXT_PUBLIC_ENABLE_STOCK_AI_DEBATE_VIEW`
- `NEXT_PUBLIC_ENABLE_STOCKOPS_API`（P1 灰度）

---

## 8. 数据与埋点统一口径（PRD 对齐）

必须落库/上报事件：

- `alert_sent`
- `alert_opened`
- `feedback_submitted`
- `suggestion_shown`
- `suggestion_accepted`
- `order_blocked_by_risk`

核心指标口径：

- Alert CTR = `alert_opened / alert_sent`
- Suggestion 采纳率 = `suggestion_accepted / suggestion_shown`
- 噪音反馈率 = `feedback_noise / feedback_submitted`

---

## 9. 风险与应对

1. **提醒噪音偏高**：加强冷却、白名单、每日上限、反馈闭环调参。
2. **解释可信度不足**：强制保留原文入口+证据映射+反方视角。
3. **服务化扰动主链路**：FastAPI 旁路灰度，随时回退前端直连。
4. **外部数据波动**：多源冗余+降级策略+source health 告警。

---

## 10. 近两周执行清单（按优先级）

1. 完成 Sprint B 收尾：反馈聚合脚本 + 报告产出。
2. 完成 Sprint C：时段开关、频控、飞书模板升级。
3. 建立 P1 技术预研分支：Portfolio schema + Screener 模板定义。（已启动）
4. 补齐埋点事件与 KPI 看板，形成每周例行复盘模板。
