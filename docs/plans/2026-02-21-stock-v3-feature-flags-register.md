# Stock V3 Feature Flags 注册表（Phase 0）

- 日期: 2026-02-21
- 目标: 明确 V3 相关开关、默认值、作用范围与回滚策略

## 1. 后端 Flags（默认全关闭）

1. `ENABLE_STOCK_V3_RUN_LOG=false`
   - 作用: 控制 V3 run metadata 相关逻辑
   - 生效范围: 分析工作流与后端脚本进程环境
2. `ENABLE_STOCK_V3_EVAL=false`
   - 作用: 控制评估/评分卡相关旁路逻辑
   - 生效范围: 分析工作流与后端脚本进程环境
3. `ENABLE_STOCK_V3_PAPER=false`
   - 作用: 控制 paper trading 相关旁路逻辑
   - 生效范围: 分析工作流与后端脚本进程环境
4. `ENABLE_STOCK_V3_CHALLENGER=false`
   - 作用: 控制 Champion/Challenger 对照评分步骤
   - 生效范围: 分析工作流与后端脚本进程环境
5. `ENABLE_STOCK_V3_DRIFT=false`
   - 作用: 控制漂移监控与自动告警步骤
   - 生效范围: 分析工作流与后端脚本进程环境
6. `ENABLE_STOCK_V3_LIFECYCLE=false`
   - 作用: 控制机会生命周期日报生成步骤
   - 生效范围: 分析工作流与后端脚本进程环境
7. `ENABLE_STOCK_V3_SUBSCRIPTION_ALERT=false`
   - 作用: 控制订阅告警投递步骤
   - 生效范围: 分析工作流与后端脚本进程环境
8. `ENABLE_STOCK_V3_CONSTRAINTS=false`
   - 作用: 控制组合约束快照步骤（`stock_portfolio_constraints_v3.py`）
   - 生效范围: 分析工作流与后端脚本进程环境
9. `ENABLE_STOCK_V3_SCORECARD=false`
   - 作用: 控制每日评分卡输出（`stock_daily_scorecard_v3.py`）
   - 生效范围: 分析工作流与后端脚本进程环境
10. `ENABLE_STOCK_V3_SHADOW_REPORT=false`
   - 作用: 控制 shadow-run 报告输出（`stock_shadow_run_report_v3.py`）
   - 生效范围: 分析工作流与后端脚本进程环境
11. `ENABLE_STOCK_V3_VALIDATION=false`
   - 作用: 控制验证套件（幂等/压测/回放一致性）执行
   - 生效范围: 分析工作流与后端脚本进程环境

## 2. 前端 Flag（默认关闭）

1. `NEXT_PUBLIC_DASHBOARD_V3_EXPLAIN=false`
   - 作用: 控制前端 V3 explain beta 展示
   - 生效范围: 前端构建时注入（Cloudflare Pages）

## 3. 配置入口

1. GitHub Actions（后端）
   - 通过 `Repository Variables` 注入：
     - `ENABLE_STOCK_V3_RUN_LOG`
     - `ENABLE_STOCK_V3_EVAL`
     - `ENABLE_STOCK_V3_PAPER`
     - `ENABLE_STOCK_V3_CHALLENGER`
     - `ENABLE_STOCK_V3_DRIFT`
     - `ENABLE_STOCK_V3_LIFECYCLE`
     - `ENABLE_STOCK_V3_SUBSCRIPTION_ALERT`
     - `ENABLE_STOCK_V3_CONSTRAINTS`
     - `ENABLE_STOCK_V3_SCORECARD`
     - `ENABLE_STOCK_V3_SHADOW_REPORT`
     - `ENABLE_STOCK_V3_VALIDATION`
2. Cloudflare Pages（前端）
   - 通过项目环境变量注入：
     - `NEXT_PUBLIC_DASHBOARD_V3_EXPLAIN`

## 4. 回滚策略

1. 出现异常时，先将所有 V3 flags 置为 `false`
2. 保持 V2 主链路不变，不进行代码级回滚
3. 仅当功能级回滚无效时再执行基线 tag 回滚

## 5. 当前落地状态

- 后端 flag 解析模块已新增：`scripts/feature_flags.py`
- V2 pipeline 已接入 flag 读取（仅日志，不改变业务行为）
- workflow 已注入后端 flags（默认 `false`，包含 eval/paper/challenger/drift/lifecycle/subscription）
- workflow 已注入后端 flags（默认 `false`，包含 constraints/scorecard/shadow/validation）
- 前端已新增 V3 explain flag 读取（默认 `false`）
