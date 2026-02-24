# Legacy 情报链路清理设计（归档方案）

- 日期：2026-02-24
- 目标：清理 RSS 情报分析历史包袱，保留并聚焦美股看板主链路。
- 策略：**安全清理**（迁移到 `archive/legacy_intel/`，不直接删除）。

## 1. 决策确认

- 清理模式：B（归档旧链路）
- 保留主线：A（仅保留美股看板主链路）
- 历史文档：A（一起归档）
- Workflow：A（仅保留 4 个）
- 数据库：A（不删旧表，只清理代码/流程）
- 特殊保留：`us_stock_x_list.txt`

## 2. 保留白名单

- 目录：`frontend/`, `config/`, `sql/`, `docs/`
- 脚本：
  - `scripts/crawler.py`
  - `scripts/cleanup.py`
  - `scripts/refresh_market_digest.py`
  - `scripts/llm_client.py`
  - `scripts/feature_flags.py`
  - `scripts/source_health_collector_v3.py`
  - `scripts/stock_*.py`
- Workflow：
  - `.github/workflows/analysis-after-crawl.yml`
  - `.github/workflows/crawler.yml`
  - `.github/workflows/x-source-ingest.yml`
  - `.github/workflows/deploy-mobile-frontend.yml`
- 根目录特殊保留：`us_stock_x_list.txt`

## 3. 归档范围

- `web/`（旧 Streamlit）
- 非白名单 `scripts/` 内容（旧情报分析链路）
- 根目录历史情报文档/来源清单（`us_*`, `military_*`, `worldmonitor*` 等）
- 非白名单 workflow 文件

归档目标目录：`archive/legacy_intel/`

## 4. Workflow 调整

- `analysis-after-crawl.yml` 删除 legacy fallback 输入与 job：
  - 移除 `legacy_fallback` input
  - 移除 `legacy-fallback-analysis` job
  - 保留 Stock V2/V3 主链路

## 5. 验证

- `python3 -m py_compile scripts/*.py`
- `npm --prefix frontend run typecheck`
- `npm --prefix frontend run build`
- 检查 `.github/workflows/` 仅剩 4 个目标文件

## 6. 回滚

- 本次清理单独提交
- 如发现误归档，从 `archive/legacy_intel/` 原路恢复

