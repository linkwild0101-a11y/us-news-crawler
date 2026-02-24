# StockOps 新整合方案执行清单（PRD 对齐）

- 方案来源：
  - `docs/plans/2026-02-24-stockops-integrated-iteration-plan.md`
  - `docs/plans/2026-02-24-stockops-detailed-prd.md`
- 执行目标：在主仓持续交付 P0，并按 PRD 时间窗推进 P1/P2。

---

## P0（2026-02-24 ~ 2026-03-22）

## A. 规则与去重骨架（已完成）

- [x] 执行：`sql/2026-02-24_stock_alerts_v1.sql`
- [x] 新增 `scripts/stock_alert_engine_v1.py`
- [x] 新增 `scripts/stock_alert_dispatch_v1.py`
- [x] workflow 接入 `ENABLE_STOCK_ALERT_V1`
- [x] 端到端验证：sent + deduped 行为正确

## B. 提醒中心与反馈入口（进行中）

- [x] 前端提醒中心（并入 dashboard）
- [x] 提醒卡“有用/噪音”反馈按钮
- [x] 反馈 API：`frontend/app/api/alerts/feedback/route.ts`
- [x] 执行 SQL：`sql/2026-02-24_stock_alert_feedback_insert_policy.sql`
- [x] 新增 `scripts/stock_alert_feedback_agg_v1.py`
- [ ] 每日报告：`docs/reports/stock-alert-feedback-daily-*.md`

## C. 时段治理与通知质量（待执行）

- [x] 盘前/盘后开关贯通（规则 + 偏好 + 前端）
- [ ] 执行 SQL：`sql/2026-02-24_stock_alert_user_prefs_write_policy.sql`
- [ ] 每日提醒上限与静默时段
- [x] 飞书模板升级（why-now + 风险 + 失效条件 + 原文）
- [x] 噪音反馈率周报

## P0 KPI 门禁

- [ ] 告警延迟 p95 < 60s
- [ ] Alert CTR >= 18%
- [ ] 噪音反馈率 <= 30%
- [ ] 7 日留存 >= 25%

---

## P1（2026-03-23 ~ 2026-04-19）

## D. Portfolio Intelligence + Macro

- [ ] 持仓输入与风险暴露模型
- [ ] 建议生成（优先级/解释/风险提示）
- [ ] 事件→行业→标的三级映射
- [ ] 建议卡强制输出“触发依据 2~3 条”

## E. Screener + FastAPI + A/B

- [ ] 策略模板（事件驱动/趋势/反转）
- [ ] 参数化筛选与回测预览（命中率/回撤/波动）
- [ ] FastAPI 旁路：`/health` `/alerts` `/alerts/{id}/feedback`
- [ ] 建议排序/文案 A-B 实验埋点

## P1 KPI 门禁

- [ ] 建议点击率 >= 20%
- [ ] 建议采纳率 >= 12%
- [ ] 宏观卡片打开率 >= 15%
- [ ] 噪音反馈率 <= 25%

---

## P2（2026-04-20 ~ 2026-05-17）

## F. 自动化执行与风控闸门

- [ ] `paper` 默认执行链路
- [ ] 风控拦截（仓位/回撤/单笔风险）
- [ ] 审计日志（策略输入/触发/风控/订单）

## G. Broker + 专业扩展

- [ ] 首批券商适配 MVP
- [ ] 社区共识层
- [ ] 期权扩展（标签级）

## P2 KPI 门禁

- [ ] 自动化执行成功率 >= 99%
- [ ] 风控拦截准确率 >= 95%
- [ ] P2 功能 30 日留存 >= 35%
- [ ] Pro 转化率 >= 6%

---

## 本周 Next 5

- [ ] 完成 `stock_alert_feedback_agg_v1.py`
- [ ] 产出首份反馈调优日报
- [ ] 完成盘前/盘后 + 上限治理 SQL 与脚本
- [ ] 将 Alert CTR/Noise Ratio 接入周报
- [ ] 启动 P1 数据模型设计稿（portfolio + screener）
