# Stock V2 生产基线冻结清单（Baseline Manifest）

- 冻结时间（UTC）: 2026-02-21T15:32:10Z
- 冻结负责人: us-news-crawler automation
- 目标: 固化当前可运行的 Stock V2 生产基线，支持后续 V3 并行演进与一键回滚。

## 1. 基线版本

- Git 分支: `main`
- 冻结提交: `ec6f634`
- 基线 Tag: `stock-v2-baseline-2026-02-21`

## 2. 关键工作流（生产相关）

1. `analysis-after-crawl.yml`
   - 职责: crawler 完成后执行 Stock V2 增量分析、市场摘要刷新与指标汇总。
2. `deploy-mobile-frontend.yml`
   - 职责: 前端构建并部署到 Cloudflare Pages。
3. `crawler.yml`
   - 职责: 新闻采集主流程。

## 3. 关键运行参数与开关

### 后端（GitHub Secrets）

- `SUPABASE_URL`
- `SUPABASE_KEY`
- `DASHSCOPE_API_KEY` / `ALIBABA_API_KEY`

### 前端（Cloudflare Pages Env）

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `NEXT_PUBLIC_DASHBOARD_READ_V2=true`

## 4. 本基线下的核心能力

1. `stock_*_v2` 数据链路（事件/信号/机会/市场状态/快照）
2. LONG/SHORT 双向机会输出
3. LLM 并发增强（`llm-workers`）
4. 热点聚类中文化（含历史翻译回填脚本）
5. 前端关键指标悬停/点击解释

## 5. 回滚与恢复手册

### A. 功能级回滚（优先）

1. 前端只读切换回旧层（如需要）
   - `NEXT_PUBLIC_DASHBOARD_READ_V2=false`
2. 分析工作流回退到 legacy_fallback 手动模式（临时）

### B. 代码级回滚（Tag 回滚）

```bash
git fetch origin --tags
git checkout main
git reset --hard stock-v2-baseline-2026-02-21
git push --force-with-lease origin main
```

## 6. 冻结后约束

1. V3 改动默认走 feature flag，不得直接影响 V2 主链路。
2. 任何新增工作流必须保证 V2 主流程可独立成功。
3. 发生异常优先执行功能级回滚，避免直接代码强回滚。
