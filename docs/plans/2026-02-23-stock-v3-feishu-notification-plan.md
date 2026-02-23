# Stock V3 飞书通知方案（v1）

- 日期: 2026-02-23
- 目标: 用最少通知覆盖最关键风险与决策信息，避免刷屏

## 1. 通知分层

### P0（实时，必须）

1. 运行失败告警（workflow/job failed）
2. 数据源 critical 告警（source health）
3. L3/L4 高等级信号告警（等级上升即时）

### P1（每次 run）

1. 成功摘要（signals/opps、多空分布、risk badge、耗时）
2. 质量摘要（翻译积压、非空率、source health H/D/C）
3. Eval / Paper 指标快照（命中率代理、纸上盈亏）

### P2（日报）

1. 当日机会变化（新增/失效/topN）
2. LONG/SHORT 结构变化
3. 风险与异常复盘摘要

## 2. 通知模板（v1）

### 2.1 失败告警模板

- 标题: `【Stock V3异常】run_id + 状态`
- 字段:
  - run_id
  - 失败阶段
  - 建议动作（查看 Actions 链接）

### 2.2 成功摘要模板

- 标题: `【Stock V3完成】run_id`
- 字段:
  - signals/opps
  - LONG/SHORT
  - risk badge
  - source health H/D/C
  - eval hit_rate proxy
  - paper realized/unrealized pnl

## 3. 频控与去重

1. 同一 run_id 只发一次摘要
2. 同一 source critical 30 分钟内不重复
3. L3/L4 同事件 30 分钟冷却，升级可立即推送

## 4. 落地策略

1. Workflow 末尾 `always()` 发送运行通知
2. notifier 脚本维护状态文件去重
3. 缺少 webhook 时自动降级跳过，不阻断主链路

## 5. 后续增强

1. 接入卡片消息（富文本 + 链接按钮）
2. 增加订阅维度（ticker/方向/等级）
3. 增加静默时段与交易时段策略

## 6. 当前落地状态（2026-02-23）

- 已落地：
  1. Workflow `always()` 运行通知（`scripts/stock_v3_notifier.py`）
  2. 运行摘要包含 source health、eval、paper、drift、champion/challenger、lifecycle 指标
  3. 订阅告警产品化 v1（`scripts/stock_subscription_alert_v3.py`，支持 ticker/方向/等级、冷却窗口）
  4. V3 评分卡/Shadow/验证脚本已可产出并可作为通知附件来源
- 待增强：
  1. 飞书富文本卡片模板
  2. 交易时段静默策略（按美股盘前/盘中/盘后）
