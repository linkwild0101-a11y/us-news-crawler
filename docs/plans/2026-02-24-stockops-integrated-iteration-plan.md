# StockOps × US-Monitor 新整合迭代方案（P0→P1）

- 日期：2026-02-24
- 输入来源：`docs/plans/2026-02-24-stockops-p0-mvp.md` + 当前 US-Monitor 主线现状
- 目标：在不打断现有美股看板迭代的前提下，先交付 **P0 信号质量闭环**，再平滑演进到 **云端 FastAPI 服务化**。

---

## 1. 已确认的产品决策

1. 架构策略：**并入现有仓库主线**（不单独新开系统）
2. P0 优先级：**信号质量闭环优先**（异动规则 + 去重冷却 + 用户反馈）
3. 服务化策略：
   - P0：继续使用现有 `scripts + Supabase + GitHub Actions`
   - P1：新增最小 FastAPI 云端服务（不替代现有流水线，先旁路）

---

## 2. 新目标定义（替换原 StockOps P0）

### P0（2~3周，必须上线）

上线范围聚焦 3 件事：

1. **异动提醒规则层**（由现有事件/信号生成 alert）
2. **去重冷却层**（同用户同标的同信号窗口不重复推送）
3. **反馈闭环层**（有用/噪音反馈入库并反哺阈值）

### P1（1~2周，服务化准备）

1. 云端 FastAPI 最小骨架上线（health + alerts query + feedback write）
2. 与 Supabase 同库协作，读写同一套 `stockops_*` 表
3. 前端逐步从本地聚合函数切到 FastAPI API（灰度）

---

## 3. 架构整合方案

## 3.1 保持不动（稳定基座）

- `scripts/stock_pipeline_v2.py`：事件/信号/机会主链路
- `scripts/stock_x_source_ingest.py`：X 信源入库（现已扩到 top44）
- `frontend/`：现有看板继续作为统一入口
- `.github/workflows/analysis-after-crawl.yml`：主分析调度

## 3.2 新增模块（并入现有代码风格）

- 后端脚本层（P0）：
  - `scripts/stock_alert_engine_v1.py`（规则与告警生成）
  - `scripts/stock_alert_dispatch_v1.py`（去重冷却 + 投递日志）
  - `scripts/stock_alert_feedback_agg_v1.py`（反馈聚合与阈值建议）
- 前端（P0）：
  - 在现有 `frontend` 增加提醒中心 tab 与反馈交互，不新建独立 app
- 云端 API（P1）：
  - `apps/stockops-api/`（FastAPI 最小服务）

---

## 4. 数据模型（Supabase）

新增表（P0）：

1. `stock_alert_rules_v1`
   - 规则定义（signal_type、threshold、cooldown_sec、session_scope、is_active）
2. `stock_alert_events_v1`
   - 告警事件（ticker、signal_type、score、payload、session_tag、as_of）
3. `stock_alert_delivery_v1`
   - 投递记录（channel、status、dedupe_key、sent_at）
4. `stock_alert_feedback_v1`
   - 用户反馈（label=useful/noise、reason、created_at）
5. `stock_alert_user_prefs_v1`
   - 用户偏好（盘前/盘后开关、每日上限、关注ticker）

关键约束：

- `unique(user_id, ticker, signal_type, dedupe_window)`
- 所有表带 `run_id/as_of/is_active`，保持与现有 V2/V3 风格一致

---

## 5. 迭代任务拆解（新版本）

## Sprint A（第1周）— 规则与去重骨架

1. SQL 迁移：创建 `stock_alert_*_v1` 表与索引
2. 新增 `stock_alert_engine_v1.py`
   - 输入：`stock_signals_v2`, `stock_opportunities_v2`, `stock_market_regime_v2`
   - 输出：`stock_alert_events_v1`
3. 新增 `stock_alert_dispatch_v1.py`
   - 去重：基于 Supabase + dedupe key（P0 不强依赖 Redis）
   - 冷却：按规则 cooldown_sec
4. Actions 集成（analysis-after-crawl 末尾）

**验收标准**
- 每轮可稳定产出 alert events
- 冷却窗口内重复提醒率显著下降

## Sprint B（第2周）— 反馈闭环与前端接入

1. 前端提醒中心（并入现有 dashboard）
   - 最新提醒列表、过滤、已读
2. 提醒卡片增加反馈按钮（有用/噪音）
3. 新增 `stock_alert_feedback_agg_v1.py`
   - 每日生成“阈值调优建议”到 `docs/reports/`

**验收标准**
- 反馈可写入并可统计
- 可按 ticker/signal_type 看到 useful ratio

## Sprint C（第3周）— 盘前盘后与质量治理

1. 时段开关（America/New_York）
2. 用户偏好与每日提醒上限
3. 飞书通知模板升级（附 why-now、来源、失效条件）

**验收标准**
- 盘前/盘后开关生效
- 日告警量可控，噪音投诉下降

---

## 6. P1 服务化（云端 FastAPI）

## 6.1 最小范围（不替换主链路）

- API:
  - `GET /health`
  - `GET /alerts`
  - `POST /alerts/{id}/feedback`
- 部署：Railway/Render/Fly.io 任一
- 数据：直接读写 Supabase（与脚本共库）

## 6.2 灰度策略

1. 前端先保留直连 Supabase + feature flag
2. 开 `NEXT_PUBLIC_ENABLE_STOCKOPS_API=true` 后切 FastAPI 读路径
3. 出现异常可一键回退直连模式

---

## 7. 与现有计划合并规则

将以下旧计划合并到本方案执行：

- `2026-02-24-stockops-p0-mvp.md`：保留目标，不直接照搬独立 apps 架构
- `2026-02-23-stock-v3-feishu-notification-plan.md`：通知能力作为 Sprint C 子任务
- `2026-02-23-stock-evidence-first-transmission-*`：继续作为 alert explainability 数据源

---

## 8. KPI（P0必看）

1. 告警延迟 p95 < 60s（分析完成后）
2. 冷却后重复告警率下降 > 40%
3. 用户反馈 useful ratio 周环比提升
4. 噪音反馈占比周环比下降
5. 盘前/盘后误提醒率可追踪

---

## 9. 风险与缓解

1. **噪音过高**：先限制规则白名单 + 每日上限
2. **时段判断错误**：统一 `America/New_York` + 边界测试
3. **服务化扰动主链路**：P1 旁路灰度，保留脚本链路为主
4. **阈值调优过慢**：反馈聚合日报 + 每周一次参数回放

---

## 10. 本周可立即执行的 Next 3

1. 提交 `stock_alert_*_v1` SQL 迁移
2. 实现 `scripts/stock_alert_engine_v1.py` 最小规则（L3/L4 + score 阈值）
3. 在现有前端增加“提醒中心 MVP 列表 + 有用/噪音按钮”

