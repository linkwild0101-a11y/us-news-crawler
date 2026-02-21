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
- workflow 已注入后端 flags（默认 `false`）
- 前端已新增 V3 explain flag 读取（默认 `false`）
