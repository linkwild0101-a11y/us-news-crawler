# US-Monitor 移动端前端与美股信息看板设计文档

- 日期: 2026-02-21
- 适用系统: US-Monitor
- 目标: 在不改动现有核心抓取/分析主链路前提下，新增移动端友好的公网前端，并基于现有数据输出常用美股信息

## 1. 背景与目标

当前系统已经具备：
- RSS 抓取与聚类分析
- 增强分析（外部信号源）
- 哨兵信号与实体关系
- Supabase 数据存储
- GitHub Actions 自动运行

本次新增能力聚焦三件事：
1. 提供兼容手机与平板的前端
2. 免费部署到公网便于远程查看
3. 基于现有数据，稳定输出常用美股信息

## 2. 设计结论（推荐方案）

### 2.1 前端技术栈

采用 **Next.js + Tailwind CSS + Supabase JS（只读）+ PWA**。

理由：
- 原生支持移动端响应式，适合手机与平板
- 部署到 Cloudflare Pages / Vercel 成熟
- 与 Supabase 直连成本低，迭代快
- 可逐步加入离线缓存（PWA）

### 2.2 免费公网部署

优先使用 **Cloudflare Pages 免费版**。

理由：
- 与 GitHub 集成简单，push 自动部署
- 免费额度足够当前只读看板场景
- 海外访问稳定，移动端打开速度较好

备选：Vercel Hobby、Netlify Free。

### 2.3 数据策略

前端只读访问 Supabase（建议通过视图/聚合表读取），先做“稳定可用”的美股信息：
- 指数与风险：SPY/QQQ/DIA/VIX/10Y/DXY
- 行业轮动：常见行业 ETF
- 资金信号：ETF flows、macro signals
- 哨兵与新闻：L1-L4、热点摘要
- 实体关系：关键实体关联

## 3. 信息架构（移动端优先）

### 3.1 页面结构

底部 Tab 四页：

1) **市场总览**
- 核心指标卡（指数、VIX、10Y、DXY）
- 市场风险状态（低/中/高）
- 当日简报（自动摘要）

2) **哨兵信号**
- L1-L4 信号流
- L3/L4 置顶
- 信号详情（触发原因、证据链接、建议动作）

3) **股票看板**
- Watchlist（用户自选）
- 热门行业 ETF 对比
- 近 24h 相关信号摘要

4) **新闻与关系**
- 热点聚类列表
- 实体关系简图（轻量）
- 与美股标的相关的事件上下文

### 3.2 响应式规则

- 手机（<768px）：单列卡片
- 平板（768-1024px）：双列卡片
- 桌面（>1024px）：三列+侧边过滤

## 4. 数据与接口设计

## 4.1 读取来源（优先复用现有表）

- `analysis_signals`：哨兵等级与增强信号
- `analysis_clusters`：热点聚类摘要
- `entity_relations` / `relation_evidence`：关系图谱
- 外部信号聚合结果（由增强分析写入）

### 4.2 新增聚合层（建议）

新增 2 张聚合表（或视图）以降低前端查询复杂度：

1. `market_snapshot_daily`
- 日期、核心指标、风险标签、摘要

2. `ticker_signal_digest`
- ticker、近24h信号数量、关联热点、风险等级、更新时间

说明：前端优先读取聚合层，避免直接拼装复杂关联查询。

### 4.3 安全策略

- 前端仅使用 Supabase anon key
- 只开放只读视图/只读表
- 严格开启 RLS，禁止匿名写入

## 5. 自动化链路设计

目标：每天爬取后自动分析，并同步前端可读数据。

现有链路：
- `crawler.yml`（已存在）
- `analysis-after-crawl.yml`（已存在）

建议补充：
- 新增 `market-digest.yml`（或并入 `analysis-after-crawl`）
  - 生成/刷新 `market_snapshot_daily`
  - 生成/刷新 `ticker_signal_digest`

触发策略：
- 跟随爬取完成自动运行
- 保留 `workflow_dispatch` 手动补跑

## 6. 部署方案

### 6.1 Cloudflare Pages（推荐）

- 将 `frontend/`（Next.js）连接 GitHub 仓库
- 生产分支：`main`
- 构建命令：`npm run build`
- 输出目录：`.next`（使用官方 Next.js preset）
- 环境变量：
  - `NEXT_PUBLIC_SUPABASE_URL`
  - `NEXT_PUBLIC_SUPABASE_ANON_KEY`

### 6.2 可观测性

- 前端注入版本号（commit hash）
- 首页显示“数据更新时间”
- Cloudflare Analytics 监控访问与错误

## 7. 实施计划

### Phase 1（3-5天）：可访问移动端 MVP

- 建立 Next.js 移动端骨架
- 完成 4 页基础 UI
- 接入 Supabase 只读查询
- 上线 Cloudflare Pages 免费域名

验收：
- 手机/平板可正常浏览
- 页内可查看哨兵、热点、基础市场指标

### Phase 2（3-5天）：美股常用信息增强

- 建立 `market_snapshot_daily` 聚合
- 建立 `ticker_signal_digest` 聚合
- 增加 watchlist 与行业 ETF 模块

验收：
- 首页可见完整市场摘要
- 指定 ticker 可查看信号与热点关联

### Phase 3（2-3天）：体验优化

- PWA（添加到主屏）
- 首屏性能优化与缓存
- 告警高亮与交互细节优化

验收：
- 手机首屏加载稳定
- 关键信息 3 秒内可见

## 8. 风险与对策

1. 现有数据字段不统一
- 对策：聚合层统一输出口径

2. 免费平台额度/限制
- 对策：优先读聚合表，降低查询压力

3. 移动端可读性问题
- 对策：统一深色高对比主题，关键信息卡片化

## 9. Go/No-Go 标准

Go 条件：
- 前端公网可访问
- 手机与平板主流程可用
- 每日自动刷新后可看到更新数据
- L3/L4 信号可在前端及时展示

No-Go 条件：
- 前端访问不稳定或数据延迟严重
- 移动端主要模块不可读/不可操作

## 10. 下一步

1. 输出实现任务清单（文件级）
2. 建立 `frontend/` 项目骨架
3. 接入 Supabase 只读与第一个总览页面
4. 接入 Cloudflare Pages 并完成首个公网版本
