# Mobile Frontend + Stock Dashboard 实施清单

- 日期: 2026-02-21
- 来源设计: `docs/plans/2026-02-21-mobile-frontend-stock-dashboard-design.md`

## Phase 1（进行中）

- [x] 新建 `frontend/`（Next.js + Tailwind + Supabase 只读）
- [x] 搭建四个移动端 Tab（市场/哨兵/看板/新闻）
- [x] 增加 PWA 基础清单（manifest + icon）
- [x] 连接 Cloudflare Pages（项目: `us-monitor-mobile-dashboard`）
- [x] 增加 GitHub Actions 自动部署（`deploy-mobile-frontend.yml`）

## Phase 2（已启动）

- [x] 新增 `market_snapshot_daily` / `ticker_signal_digest` 迁移脚本
- [x] 新增 `scripts/refresh_market_digest.py` 聚合刷新脚本
- [x] 接入 `analysis-after-crawl.yml` 自动刷新
- [ ] 接入真实市场行情源（SPY/QQQ/VIX/10Y/DXY）

## Phase 3（待开始）

- [ ] PWA 离线缓存（service worker）
- [ ] 首屏性能压测与缓存策略优化
- [ ] 告警高亮交互优化

## 验收口径（当前）

- 前端可本地运行并读取 Supabase
- 若聚合表未就绪，页面会自动回退到已有 `analysis_signals` / `analysis_clusters`
- 工作流在增强分析后自动刷新聚合层
