# US News RSS Crawler

基于云服务的零成本 RSS 新闻爬虫系统，每日自动爬取 539 个美国新闻源的 RSS  feeds，提取正文内容，进行 SimHash 去重，存储到 Supabase PostgreSQL 数据库。

## 特性

- **539个RSS源**: 军事(210) + 政治(193) + 经济(150)
- **自动爬取**: GitHub Actions 每6小时运行
- **混合内容提取**: 本地提取 + Cloudflare Worker（绕过反爬）
- **SimHash去重**: 智能识别转载/相似文章
- **90天自动清理**: 数据 retention 管理
- **零成本**: 完全使用免费云服务额度

## 技术栈

| 组件 | 服务 | 用途 |
|------|------|------|
| 调度器 | GitHub Actions | 定时触发爬虫 |
| 爬虫引擎 | Python + asyncio | RSS抓取与处理 |
| 内容提取 | Cloudflare Workers | 绕过反爬机制 |
| 数据库 | Supabase PostgreSQL | 数据存储 |
| 去重算法 | SimHash | 相似文章检测 |

## 项目结构

```
.
├── data/
│   └── sources.json          # RSS源数据
├── scripts/
│   ├── extract_sources.py    # 提取RSS源
│   ├── import_sources.py     # 导入到Supabase
│   ├── crawler.py            # 主爬虫
│   ├── dedup.py              # SimHash去重
│   ├── cleaner.py            # 数据清洗
│   └── cleanup.py            # 90天清理
├── sql/
│   └── schema.sql            # 数据库表结构
├── workers/
│   └── content-extractor/    # Cloudflare Worker
├── frontend/                 # Next.js 移动端看板
├── .github/
│   └── workflows/
│       └── crawler.yml       # GitHub Actions
├── requirements.txt          # Python依赖
└── README.md                 # 本文档
```

## 快速开始

### 1. 环境准备

复制环境变量模板：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 API 密钥：

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
WORKER_URL=https://your-worker.your-name.workers.dev
WORLDMONITOR_BASE_URL=https://worldmonitor.app
ENABLE_WORLDMONITOR_ENDPOINTS=true
WORLDMONITOR_MAX_PRIORITY=2
```

端点白名单默认在 `config/analysis_config.py` 的
`WORLDMONITOR_SIGNAL_CONFIG["enabled_endpoints"]` 配置，可按需增减。

### 2. 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 数据库设置

在 Supabase SQL Editor 中执行 `sql/schema.sql` 创建表结构。

### 4. 导入RSS源

```bash
python scripts/import_sources.py
```

### 5. 手动运行爬虫（测试）

```bash
python scripts/crawler.py
```

### 6. 刷新移动端聚合摘要（可选）

```bash
python scripts/refresh_market_digest.py --hours 24 --limit 500
```

### 7. 本地启动移动端前端（可选）

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

## GitHub Actions 配置

在 GitHub Repository → Settings → Secrets and variables → Actions 中添加：

- `SUPABASE_URL`: Supabase 项目 URL
- `SUPABASE_KEY`: Supabase Service Role Key
- `WORKER_URL`: Cloudflare Worker URL（部署后获得）
- `RAILWAY_URL`: Railway RSS 代理地址（可选，建议配置）
- `WORLDMONITOR_BASE_URL`: worldmonitor API 基础地址（可选）

## Cloudflare Worker 部署

```bash
cd workers/content-extractor
npm install
npm run deploy
```

部署成功后，记录 Worker URL 并更新到 GitHub Secrets。

## 数据库表结构

### rss_sources
RSS源信息表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL | 主键 |
| name | VARCHAR(255) | 源名称 |
| rss_url | VARCHAR(500) | RSS地址（唯一） |
| category | VARCHAR(50) | 分类: military/politics/economy/tech |
| anti_scraping | VARCHAR(50) | 反爬级别: None/Cloudflare/Paywall |
| status | VARCHAR(20) | 状态: active/inactive/error |

### articles
文章表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL | 主键 |
| title | TEXT | 标题 |
| content | TEXT | 正文内容 |
| url | TEXT | 文章URL（唯一） |
| source_id | INTEGER | 外键关联rss_sources |
| simhash | VARCHAR(64) | SimHash指纹 |
| fetched_at | TIMESTAMP | 抓取时间 |

## 免费额度监控

### GitHub Actions
- **免费额度**: 2000分钟/月
- **本项目**: ~480分钟/月（每6小时×4次/天×30天×40分钟）
- **状态**: ✅ 充足

### Supabase
- **免费额度**: 500MB 存储
- **本项目**: ~200-300MB（90天数据）
- **状态**: ✅ 充足

### Cloudflare Workers
- **免费额度**: 100,000请求/天
- **本项目**: ~3,000-5,000请求/天
- **状态**: ✅ 充足

## 维护

### 查看爬取日志

```sql
SELECT * FROM crawl_logs ORDER BY started_at DESC LIMIT 10;
```

### 手动清理旧数据

```bash
python scripts/cleanup.py --dry-run  # 预览
python scripts/cleanup.py            # 执行清理
```

### 更新RSS源

如果源文件有更新：

```bash
python scripts/extract_sources.py    # 重新提取
python scripts/import_sources.py     # 重新导入
```

## 故障排查

### 爬虫运行超时
- GitHub Actions 单次运行上限6小时
- 如果超时，减少每批处理的源数量
- 若日志长期无输出，确认 workflow 使用 `python -u` 与 `PYTHONUNBUFFERED=1`

### 数据库存储满了
- 减少数据保留天数（90→60→30天）
- 或升级到 Supabase Pro ($25/月)

### Worker请求超限
- 减少反爬站点的提取频率
- 或优化提取逻辑减少请求

## License

MIT
