# StockOps 新整合方案执行清单（可执行）

- 方案来源：`docs/plans/2026-02-24-stockops-integrated-iteration-plan.md`
- 执行目标：先落地 P0 第一阶段（规则 + 去重），随后进入反馈闭环。

## Sprint A（本周执行）

## A1. 数据层（SQL）

- [ ] 在 Supabase 执行：`sql/2026-02-24_stock_alerts_v1.sql`
- [ ] 校验表是否创建：
  - `stock_alert_rules_v1`
  - `stock_alert_events_v1`
  - `stock_alert_delivery_v1`
  - `stock_alert_feedback_v1`
  - `stock_alert_user_prefs_v1`
- [ ] 校验默认种子：`default-l3-70` 规则 + `system` 偏好

## A2. 引擎层（规则生成）

- [x] 新增 `scripts/stock_alert_engine_v1.py`
- [ ] 本地 dry run：
  - `python3 scripts/stock_alert_engine_v1.py --hours 72 --opp-limit 200 --signal-limit 300`
- [ ] 核验写入：`stock_alert_events_v1` 是否有 pending 事件

## A3. 投递层（去重冷却）

- [x] 新增 `scripts/stock_alert_dispatch_v1.py`
- [ ] 本地 dry run：
  - `python3 scripts/stock_alert_dispatch_v1.py --dry-run --limit 100`
- [ ] 实际执行：
  - `python3 scripts/stock_alert_dispatch_v1.py --channel inbox --limit 100`
- [ ] 核验结果：
  - `stock_alert_delivery_v1` 有 sent 记录
  - 重复执行后 dedupe 生效（新增 sent 显著下降）

## A4. CI 集成（可控开关）

- [x] `analysis-after-crawl.yml` 已接入 alert engine/dispatch 步骤
- [x] 新增变量开关：`ENABLE_STOCK_ALERT_V1`（默认 false）
- [ ] 打开变量并手动触发 workflow 验证

## A5. 验证与回归

- [ ] `python3 -m py_compile scripts/*.py`
- [ ] Workflow YAML 语法检查
- [ ] 观察一次完整 run 的 alert 产出与去重效果

---

## Sprint B（下周）

- [x] 前端提醒中心列表（并入现有 dashboard）
- [x] 提醒卡“有用/噪音”反馈按钮
- [ ] 执行 SQL：`sql/2026-02-24_stock_alert_feedback_insert_policy.sql`
- [ ] 反馈聚合脚本 `stock_alert_feedback_agg_v1.py`
- [ ] 阈值建议日报（输出到 `docs/reports/`）

## Sprint C（第3周）

- [ ] 盘前/盘后开关接入用户偏好
- [ ] 每日提醒上限治理
- [ ] 飞书模板升级（why-now + 风险 + 原文）

---

## 里程碑验收口径

- M1：能稳定生成 alert events（规则触发可解释）
- M2：去重冷却生效（重复提醒率明显下降）
- M3：用户反馈可写入并可统计 useful/noise 比例
