# RSS新闻爬虫云方案 - 工作计划

## TL;DR

> **目标**: 构建零成本云服务方案，每日爬取558个RSS源（军事/政治/经济），提取新闻内容，SimHash去重，Supabase入库，90天自动清理
> 
> **交付物**: 
> - GitHub Actions自动爬虫工作流
> - Supabase PostgreSQL数据库 + 表结构
> - Cloudflare Worker内容提取服务
> - Python爬虫脚本（RSS解析 + SimHash去重）
> - 90天数据自动清理脚本
> 
> **预估成本**: $0/月 (GitHub Actions 2000分钟 + Supabase 500MB + Cloudflare 10万请求/天)
> 
> **调度**: 每6小时自动运行（cron: `0 */6 * * *`）
> 
> **并行度**: 3个Wave并行执行，预计40分钟完成

---

## 上下文

### 原始需求
用户希望从当前目录的markdown文件中提取558个RSS源，构建云爬虫系统：
- 源：军事214 + 政治193 + 经济151 = 558个RSS源
- 频率：每6小时爬取一次
- 处理：RSS → 正文提取 → SimHash去重 → 清洗 → 入库
- 存储：Supabase PostgreSQL，保留90天自动清理
- 成本：尽量使用免费云服务

### 确认的决策
| 决策项 | 选择 |
|--------|------|
| 爬取频率 | 每6小时一次 |
| 内容提取 | 混合方案：Worker处理反爬站点，本地Python处理普通站点 |
| 去重策略 | SimHash相似内容检测（处理转载文章） |
| 语言处理 | 保持英文原文 |
| 数据保留 | 90天后自动清理 |

### 源数据文件
- `us_military_news_sources_214.md` - 军事新闻源
- `us_politics_news_sources_193.md` - 政治新闻源（假设存在，实际需检查）
- `us_economy_finance_sources_151.md` - 经济新闻源

---

## 工作目标

### 核心目标
构建完全基于免费云服务的RSS新闻爬虫系统，自动爬取、去重、存储、清理，无需人工干预。

### 具体交付物
1. **数据提取脚本**: 从markdown提取558个RSS URL → `sources.json`
2. **Supabase数据库**: 项目创建 + 表结构 + 初始数据导入
3. **Cloudflare Worker**: 内容提取API服务（处理反爬站点）
4. **GitHub Actions**: 爬虫调度工作流（每6小时触发）
5. **Python爬虫**: RSS解析、SimHash去重、数据清洗
6. **清理脚本**: 90天自动删除旧数据

### 定义完成
- [ ] GitHub Actions成功运行，无报错
- [ ] Supabase数据表创建，sources.json已导入
- [ ] Cloudflare Worker部署成功，API可访问
- [ ] 单次爬取完成，articles表有新数据
- [ ] SimHash去重工作正常（相似文章被识别）
- [ ] 90天清理脚本运行，旧数据被删除
- [ ] 总成本为$0

### Must Have（必须完成）
- 558个RSS源全部录入数据库
- 每6小时自动爬取
- SimHash去重算法实现
- 90天自动数据清理

### Must NOT Have（明确排除）
- 不使用付费云服务（除非免费额度用尽）
- 不进行翻译（保持英文原文）
- 不存储超过90天的数据
- 不处理社交媒体API（仅限RSS）

---

## 验证策略

### 测试决策
- **基础设施测试**: 有（每个组件部署后验证）
- **集成测试**: 有（完整端到端爬取测试）
- **框架**: pytest (Python) + GitHub Actions验证

### Agent-Executed QA Scenarios（每个TODO必须包含）

每个任务完成后，执行代理将通过以下方式验证：
- **API/数据库验证**: curl/psql查询验证数据
- **部署验证**: HTTP请求验证服务可访问
- **日志验证**: GitHub Actions日志检查
- **数据验证**: 查询数据库确认数据完整性

---

## 执行策略

### 并行执行Wave

```
Wave 1 (Start Immediately):
├── Task 1: 提取RSS源数据 → sources.json
└── Task 2: 创建Supabase项目 + 表结构

Wave 2 (After Wave 1):
├── Task 3: 导入sources.json到数据库
└── Task 4: 开发Cloudflare Worker内容提取服务

Wave 3 (After Wave 2):
├── Task 5: 开发Python RSS爬虫核心
└── Task 6: 实现SimHash去重算法

Wave 4 (After Wave 3):
├── Task 7: 数据清洗模块
└── Task 8: GitHub Actions工作流配置

Wave 5 (Final):
├── Task 9: 90天自动清理脚本
└── Task 10: 端到端集成测试 + 文档
```

### 依赖矩阵

| Task | Depends On | Blocks | 可并行 |
|------|------------|--------|--------|
| 1 | None | 3 | 2 |
| 2 | None | 3 | 1 |
| 3 | 1, 2 | 4 | - |
| 4 | 3 | 5, 6 | - |
| 5 | 4 | 7, 8 | 6 |
| 6 | 4 | 7, 8 | 5 |
| 7 | 5, 6 | 9, 10 | 8 |
| 8 | 5, 6 | 9, 10 | 7 |
| 9 | 7, 8 | - | 10 |
| 10 | 7, 8 | - | 9 |

---

## TODOs

### Task 1: 从Markdown提取RSS源数据

**What to do**:
- 解析3个markdown文件：`us_military_news_sources_214.md`, `us_politics_news_sources_193.md`, `us_economy_finance_sources_151.md`
- 提取每行的：name, listing_url, rss_url, category, anti_scraping
- 生成 `data/sources.json` 结构化数据
- 验证RSS URL格式正确性

**Must NOT do**:
- 不修改原始markdown文件
- 不爬取内容（仅提取URL）
- 不处理缺失的源文件（如发现缺失需记录警告）

**Recommended Agent Profile**:
- **Category**: `quick`
- **Skills**: 无需特殊技能，纯文本处理
- **Reason**: 简单的文件解析和JSON生成任务

**Parallelization**:
- **Can Run In Parallel**: YES
- **Parallel Group**: Wave 1
- **Blocks**: Task 3
- **Blocked By**: None

**References**:
- 源文件格式：`us_military_news_sources_214.md:21-30` - Markdown表格格式示例
- 输出格式参考：`data/sources.json` - 包含字段: id, name, rss_url, category, anti_scraping

**Acceptance Criteria**:
- [ ] 解析3个markdown文件，提取所有RSS URL
- [ ] 生成 `data/sources.json`，格式：`[{"id": 1, "name": "...", "rss_url": "...", "category": "military", "anti_scraping": "None"}]`
- [ ] 统计总数并与预期558对比，记录差异
- [ ] 验证所有rss_url以http开头
- [ ] Agent验证：`cat data/sources.json | jq '. | length'` 返回有效数字

**Agent-Executed QA Scenarios**:
```
Scenario: 验证sources.json生成正确
  Tool: Bash
  Preconditions: markdown源文件存在
  Steps:
    1. 运行提取脚本: python scripts/extract_sources.py
    2. 检查文件存在: test -f data/sources.json
    3. 验证JSON格式: cat data/sources.json | jq '.' > /dev/null
    4. 统计数量: count=$(cat data/sources.json | jq '. | length')
    5. 断言: count > 500
    6. 抽样检查: cat data/sources.json | jq '.[0].rss_url' | grep -E "^\"http"
  Expected Result: sources.json存在，格式正确，数量>500，URL格式正确
  Evidence: 输出count数值和抽样URL

Scenario: 验证分类正确
  Tool: Bash
  Steps:
    1. 检查military分类: cat data/sources.json | jq '[.[] | select(.category=="military")] | length'
    2. 检查politics分类: cat data/sources.json | jq '[.[] | select(.category=="politics")] | length'
    3. 检查economy分类: cat data/sources.json | jq '[.[] | select(.category=="economy")] | length'
    4. 断言: 每个分类都有合理数量(>50)
  Expected Result: 三个分类都有数据
  Evidence: 各分类数量输出
```

**Commit**: YES
- Message: `feat(data): extract RSS sources from markdown files`
- Files: `data/sources.json`, `scripts/extract_sources.py`

---

### Task 2: 创建Supabase项目与数据库表

**What to do**:
- 注册/登录Supabase (使用GitHub账号)
- 创建新项目：`us-news-crawler`
- 执行SQL创建表结构：
  - `rss_sources` - RSS源信息
  - `articles` - 爬取的文章
  - `crawl_logs` - 爬取日志
- 配置Row Level Security (RLS)策略
- 记录项目URL和anon key到 `.env.example`

**Must NOT do**:
- 不上传真实`.env`文件（只上传`.env.example`模板）
- 不开启外部访问（仅服务间调用）

**Recommended Agent Profile**:
- **Category**: `quick`
- **Skills**: 无需特殊技能，网页操作+SQL
- **Reason**: 主要是Supabase UI操作和标准SQL

**Parallelization**:
- **Can Run In Parallel**: YES
- **Parallel Group**: Wave 1
- **Blocks**: Task 3
- **Blocked By**: None

**References**:
- Supabase官方文档: https://supabase.com/docs/guides/database
- PostgreSQL表设计最佳实践

**Acceptance Criteria**:
- [ ] Supabase项目创建成功，Dashboard可访问
- [ ] 执行SQL创建3个表结构
- [ ] RLS策略配置完成（安全）
- [ ] `.env.example`包含：SUPABASE_URL, SUPABASE_KEY
- [ ] Agent验证：`curl -s $SUPABASE_URL/rest/v1/rss_sources?limit=1` 返回空数组或数据

**Agent-Executed QA Scenarios**:
```
Scenario: 验证Supabase项目创建
  Tool: Bash
  Preconditions: 用户已提供SUPABASE_URL和SUPABASE_KEY
  Steps:
    1. 测试连接: curl -s "$SUPABASE_URL/rest/v1/" -H "apikey: $SUPABASE_KEY"
    2. 检查表存在: curl -s "$SUPABASE_URL/rest/v1/rss_sources?limit=0" -H "apikey: $SUPABASE_KEY"
    3. 断言: HTTP状态200
  Expected Result: Supabase项目可访问，表结构正确
  Evidence: curl响应状态码

Scenario: 验证表结构正确
  Tool: Bash
  Steps:
    1. 查询表结构: psql $DATABASE_URL -c "\d rss_sources"
    2. 检查字段: grep -E "id|name|rss_url|category"
    3. 断言: 所有必需字段存在
  Expected Result: 表结构符合设计
  Evidence: 表字段列表
```

**SQL Schema**:
```sql
-- RSS源表
CREATE TABLE rss_sources (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    rss_url VARCHAR(500) UNIQUE NOT NULL,
    listing_url VARCHAR(500),
    category VARCHAR(50) NOT NULL CHECK (category IN ('military', 'politics', 'economy')),
    anti_scraping VARCHAR(50) DEFAULT 'None',
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'error')),
    last_fetch TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 文章表
CREATE TABLE articles (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT,
    url TEXT UNIQUE NOT NULL,
    source_id INTEGER REFERENCES rss_sources(id),
    published_at TIMESTAMP,
    fetched_at TIMESTAMP DEFAULT NOW(),
    simhash VARCHAR(64), -- SimHash指纹
    category VARCHAR(50),
    author VARCHAR(255),
    summary TEXT,
    extraction_method VARCHAR(50) DEFAULT 'local' -- 'local' 或 'cloudflare'
);

-- 爬取日志表
CREATE TABLE crawl_logs (
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    sources_count INTEGER,
    articles_fetched INTEGER,
    articles_new INTEGER,
    articles_deduped INTEGER,
    errors_count INTEGER,
    status VARCHAR(20) DEFAULT 'running'
);

-- 索引优化
CREATE INDEX idx_articles_simhash ON articles(simhash);
CREATE INDEX idx_articles_url ON articles(url);
CREATE INDEX idx_articles_fetched_at ON articles(fetched_at);
CREATE INDEX idx_articles_published_at ON articles(published_at);
CREATE INDEX idx_sources_category ON rss_sources(category);
CREATE INDEX idx_sources_status ON rss_sources(status);

-- 启用RLS
ALTER TABLE rss_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE articles ENABLE ROW LEVEL SECURITY;

-- 创建策略（仅服务账号可访问）
CREATE POLICY "Service only" ON rss_sources FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service only" ON articles FOR ALL USING (auth.role() = 'service_role');
```

**Commit**: YES
- Message: `feat(db): setup Supabase project and database schema`
- Files: `sql/schema.sql`, `.env.example`

---

### Task 3: 导入Sources数据到Supabase

**What to do**:
- 读取 `data/sources.json`
- 批量插入到 `rss_sources` 表
- 验证数据完整性
- 生成导入报告（成功数/失败数/重复数）

**Must NOT do**:
- 不重复导入已存在的URL（使用UPSERT）
- 不修改源数据格式

**Recommended Agent Profile**:
- **Category**: `quick`
- **Skills**: 无需特殊技能
- **Reason**: 简单的数据导入任务

**Parallelization**:
- **Can Run In Parallel**: NO
- **Parallel Group**: Wave 2
- **Blocks**: Task 4
- **Blocked By**: Task 1, Task 2

**Acceptance Criteria**:
- [ ] 使用supabase-py库批量导入
- [ ] 处理重复URL（跳过或更新）
- [ ] 验证数据库中sources数量与JSON一致
- [ ] Agent验证：`curl $SUPABASE_URL/rest/v1/rss_sources` 返回所有源数据

**Agent-Executed QA Scenarios**:
```
Scenario: 验证数据导入成功
  Tool: Bash
  Steps:
    1. 运行导入脚本: python scripts/import_sources.py
    2. 查询数量: curl -s "$SUPABASE_URL/rest/v1/rss_sources?select=id" | jq '. | length'
    3. 断言: 数量 >= 500
    4. 抽样验证: curl -s "$SUPABASE_URL/rest/v1/rss_sources?limit=1" | jq '.[0].name'
  Expected Result: 数据成功导入，可查询
  Evidence: 导入数量和抽样数据
```

**Commit**: YES
- Message: `feat(db): import RSS sources to Supabase`
- Files: `scripts/import_sources.py`

---

### Task 4: 开发Cloudflare Worker内容提取服务

**What to do**:
- 安装Wrangler CLI: `npm install -g wrangler`
- 登录Cloudflare账号
- 创建Worker项目：`wrangler init content-extractor`
- 实现API端点：
  - `POST /extract` - 接收URL，返回提取的正文
  - 使用 `@mozilla/readability` 解析HTML
  - 处理Cloudflare保护的站点（绕过反爬）
- 部署并测试

**Must NOT do**:
- 不处理非新闻页面（返回错误）
- 不存储数据（Worker只负责提取）
- 不超过10秒超时

**Recommended Agent Profile**:
- **Category**: `unspecified-medium`
- **Skills**: `wrangler` (Cloudflare部署)
- **Reason**: 需要Wrangler CLI进行Worker部署

**Parallelization**:
- **Can Run In Parallel**: NO
- **Parallel Group**: Wave 2
- **Blocks**: Task 5
- **Blocked By**: Task 3

**Acceptance Criteria**:
- [ ] Worker成功部署，返回worker.dev域名
- [ ] API `POST /extract` 可访问
- [ ] 返回JSON格式：`{title, content, excerpt, published_time}`
- [ ] 测试3个不同站点，提取成功
- [ ] Agent验证：`curl -X POST https://worker.xxx.workers.dev/extract -d '{"url":"https://..."}'` 返回正文

**Agent-Executed QA Scenarios**:
```
Scenario: 验证Worker部署成功
  Tool: Bash
  Preconditions: Worker已部署，URL已知
  Steps:
    1. 健康检查: curl -s https://worker.xxx.workers.dev/health
    2. 断言: 返回 {"status":"ok"}
    3. 测试提取: curl -s -X POST https://worker.xxx.workers.dev/extract \
       -H "Content-Type: application/json" \
       -d '{"url":"https://www.reuters.com/business/"}'
    4. 断言: 返回包含title和content的JSON
  Expected Result: Worker运行正常，能提取新闻内容
  Evidence: 提取结果JSON
```

**Worker代码结构**:
```javascript
// worker.js
import { Readability } from '@mozilla/readability';
import { JSDOM } from 'jsdom';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    
    if (url.pathname === '/health') {
      return new Response(JSON.stringify({status: 'ok'}));
    }
    
    if (url.pathname === '/extract' && request.method === 'POST') {
      const { targetUrl } = await request.json();
      
      // 使用Cloudflare的fetch（绕过反爬）
      const response = await fetch(targetUrl, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (compatible; NewsBot/1.0)'
        }
      });
      
      const html = await response.text();
      const doc = new JSDOM(html, { url: targetUrl });
      const reader = new Readability(doc.window.document);
      const article = reader.parse();
      
      return new Response(JSON.stringify({
        title: article.title,
        content: article.content,
        excerpt: article.excerpt,
        byline: article.byline,
        published_time: article.publishedTime
      }), {
        headers: { 'Content-Type': 'application/json' }
      });
    }
    
    return new Response('Not Found', { status: 404 });
  }
};
```

**Commit**: YES
- Message: `feat(worker): deploy Cloudflare content extraction service`
- Files: `workers/content-extractor/*`

---

### Task 5: 开发Python RSS爬虫核心

**What to do**:
- 安装依赖：`feedparser`, `aiohttp`, `asyncio`, `supabase-py`, `simhash`
- 实现异步RSS抓取：
  - 从Supabase获取所有active的sources
  - 使用aiohttp并发抓取（限制并发数20）
  - 解析RSS获取文章列表
  - 识别新文章（通过URL检查）
- 实现混合内容提取：
  - anti_scraping='None' → 本地newspaper3k提取
  - anti_scraping='Cloudflare'|'Paywall' → 调用Worker API
- 数据清洗：HTML标签去除、空白规范化
- 写入Supabase articles表

**Must NOT do**:
- 不阻塞主线程（全程异步）
- 不重复处理已存在的URL
- 不忽略提取失败的文章（记录到日志）

**Recommended Agent Profile**:
- **Category**: `unspecified-high`
- **Skills**: 无需特殊技能
- **Reason**: 复杂的异步Python爬虫，需要良好的错误处理

**Parallelization**:
- **Can Run In Parallel**: YES
- **Parallel Group**: Wave 3
- **Blocks**: Task 7, Task 8
- **Blocked By**: Task 4

**Acceptance Criteria**:
- [ ] 成功抓取所有active sources
- [ ] 异步并发限制在20以内
- [ ] 混合提取策略工作正常
- [ ] 新文章写入articles表
- [ ] Agent验证：`python scripts/crawler.py --test` 成功运行并返回统计

**Agent-Executed QA Scenarios**:
```
Scenario: 验证爬虫能抓取RSS并提取内容
  Tool: Bash
  Steps:
    1. 运行测试模式: python scripts/crawler.py --test --limit 10
    2. 检查输出: grep -E "Fetched|Extracted|Saved"
    3. 查询数据库: curl -s "$SUPABASE_URL/rest/v1/articles?order=fetched_at.desc&limit=5"
    4. 断言: 有新数据写入
  Expected Result: 成功抓取并存储文章
  Evidence: 抓取统计和数据库记录

Scenario: 验证混合提取策略
  Tool: Bash
  Steps:
    1. 检查本地提取: grep "extraction_method.*local" in logs
    2. 检查Worker提取: grep "extraction_method.*cloudflare" in logs
    3. 断言: 两种方法都有使用记录
  Expected Result: 两种提取方式都正常工作
  Evidence: 日志中的提取方法统计
```

**代码结构**:
```python
# scripts/crawler.py
import asyncio
import aiohttp
import feedparser
from supabase import create_client
from newspaper import Article as NewspaperArticle
import os

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
WORKER_URL = os.getenv('WORKER_URL')

async def fetch_rss(session, source):
    """抓取单个RSS源"""
    try:
        async with session.get(source['rss_url'], timeout=30) as resp:
            content = await resp.text()
            feed = feedparser.parse(content)
            return {
                'source_id': source['id'],
                'entries': feed.entries,
                'category': source['category'],
                'anti_scraping': source['anti_scraping']
            }
    except Exception as e:
        print(f"Error fetching {source['rss_url']}: {e}")
        return None

async def extract_content(session, url, anti_scraping):
    """混合内容提取"""
    if anti_scraping in ['Cloudflare', 'Paywall']:
        # 使用Cloudflare Worker
        async with session.post(WORKER_URL, json={'targetUrl': url}) as resp:
            data = await resp.json()
            return data
    else:
        # 本地提取
        article = NewspaperArticle(url)
        article.download()
        article.parse()
        return {
            'title': article.title,
            'content': article.text,
            'published_time': article.publish_date
        }

async def main():
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # 获取所有active sources
    sources = supabase.table('rss_sources').select('*').eq('status', 'active').execute().data
    
    async with aiohttp.ClientSession() as session:
        # 并发抓取RSS（限制20并发）
        semaphore = asyncio.Semaphore(20)
        
        async def fetch_with_limit(source):
            async with semaphore:
                return await fetch_rss(session, source)
        
        results = await asyncio.gather(*[fetch_with_limit(s) for s in sources])
        
        # 处理每篇文章...
        
if __name__ == '__main__':
    asyncio.run(main())
```

**Commit**: YES
- Message: `feat(crawler): implement async RSS crawler with hybrid extraction`
- Files: `scripts/crawler.py`, `requirements.txt`

---

### Task 6: 实现SimHash去重算法

**What to do**:
- 安装：`pip install simhash`
- 实现SimHash计算：
  - 输入：文章标题+内容（前500字符）
  - 输出：64位SimHash指纹
- 实现相似度检测：
  - 汉明距离 <= 3 认为是相似文章
  - 查询数据库已有文章的SimHash
  - 标记重复文章（不写入，只记录到dedup_logs）
- 集成到crawler.py

**Must NOT do**:
- 不比较所有历史文章（最近7天即可）
- 不误删相似但不重复的文章（汉明距离阈值要合理）

**Recommended Agent Profile**:
- **Category**: `unspecified-medium`
- **Skills**: 无需特殊技能
- **Reason**: 算法实现，需要理解SimHash原理

**Parallelization**:
- **Can Run In Parallel**: YES
- **Parallel Group**: Wave 3
- **Blocks**: Task 7, Task 8
- **Blocked By**: Task 4

**Acceptance Criteria**:
- [ ] SimHash计算函数实现
- [ ] 汉明距离相似度检测实现
- [ ] 集成到爬虫流程
- [ ] 测试：相似文章被正确识别
- [ ] Agent验证：运行测试脚本，相似度检测准确

**Agent-Executed QA Scenarios**:
```
Scenario: 验证SimHash能检测相似文章
  Tool: Bash
  Steps:
    1. 准备测试数据: 两篇相似文章文本
    2. 运行测试: python tests/test_simhash.py
    3. 检查输出: grep "Hamming distance"
    4. 断言: 距离 <= 3
    5. 测试不同文章: 距离应 > 10
  Expected Result: 相似文章检测准确
  Evidence: 汉明距离计算结果
```

**代码结构**:
```python
# scripts/dedup.py
from simhash import Simhash

def get_simhash(text):
    """计算文本的SimHash"""
    if not text:
        return None
    # 只取前1000字符，分词
    text = text[:1000].lower()
    return Simhash(text).value

def hamming_distance(hash1, hash2):
    """计算两个SimHash的汉明距离"""
    x = (hash1 ^ hash2) & ((1 << 64) - 1)
    ans = 0
    while x:
        ans += 1
        x &= x - 1
    return ans

def find_similar_articles(supabase, simhash, threshold=3):
    """查找相似文章（优化版：只查最近7天）"""
    from datetime import datetime, timedelta
    
    seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
    
    # 获取最近7天的文章SimHash
    articles = supabase.table('articles')\
        .select('id, simhash, url')\
        .gte('fetched_at', seven_days_ago)\
        .execute().data
    
    duplicates = []
    for article in articles:
        if article['simhash']:
            distance = hamming_distance(int(simhash), int(article['simhash']))
            if distance <= threshold:
                duplicates.append({
                    'id': article['id'],
                    'url': article['url'],
                    'distance': distance
                })
    
    return duplicates
```

**Commit**: YES
- Message: `feat(dedup): implement SimHash duplicate detection`
- Files: `scripts/dedup.py`, `tests/test_simhash.py`

---

### Task 7: 数据清洗模块

**What to do**:
- 实现HTML标签清理（使用BeautifulSoup）
- 实现空白字符规范化：
  - 多个空格/换行合并为单个
  - 去除首尾空白
- 实现特殊字符处理：
  - 统一编码为UTF-8
  - 处理HTML实体（&amp; → &）
- 实现图片链接保留（但标记为[IMAGE]）
- 集成到crawler.py的数据处理流程

**Must NOT do**:
- 不删除所有HTML（保留基础格式如<p>）
- 不截断超过长度限制的内容（记录警告）

**Recommended Agent Profile**:
- **Category**: `quick`
- **Skills**: 无需特殊技能
- **Reason**: 标准文本处理任务

**Parallelization**:
- **Can Run In Parallel**: YES
- **Parallel Group**: Wave 4
- **Blocks**: Task 9, Task 10
- **Blocked By**: Task 5, Task 6

**Acceptance Criteria**:
- [ ] HTML标签清理函数实现
- [ ] 空白规范化函数实现
- [ ] 特殊字符处理实现
- [ ] 集成到爬虫流程
- [ ] Agent验证：清洗后的文本格式正确

**Agent-Executed QA Scenarios**:
```
Scenario: 验证数据清洗效果
  Tool: Bash
  Steps:
    1. 运行测试: python tests/test_cleaner.py
    2. 输入带HTML的文本
    3. 检查输出: 无<script>标签，<p>保留，空白规范化
    4. 断言: 清洗后文本可读性良好
  Expected Result: 清洗效果符合预期
  Evidence: 清洗前后对比
```

**Commit**: YES
- Message: `feat(cleaner): add data cleaning module`
- Files: `scripts/cleaner.py`, `tests/test_cleaner.py`

---

### Task 8: GitHub Actions工作流配置

**What to do**:
- 创建 `.github/workflows/crawler.yml`
- 配置定时触发：`cron: '0 */6 * * *'`（每6小时）
- 配置环境变量（从GitHub Secrets读取）
- 配置步骤：
  1. Checkout代码
  2. Setup Python
  3. 安装依赖
  4. 运行爬虫
  5. 发送通知（可选）
- 配置caching加速（pip缓存）
- 配置超时（6小时上限）

**Must NOT do**:
- 不硬编码 Secrets（使用`${{ secrets.XXX }}`）
- 不超6小时运行（GitHub Actions限制）

**Recommended Agent Profile**:
- **Category**: `quick`
- **Skills**: 无需特殊技能
- **Reason**: 标准GitHub Actions配置

**Parallelization**:
- **Can Run In Parallel**: YES
- **Parallel Group**: Wave 4
- **Blocks**: Task 9, Task 10
- **Blocked By**: Task 5, Task 6

**Acceptance Criteria**:
- [ ] workflow文件创建
- [ ] 定时触发配置正确
- [ ] Secrets配置文档（README说明）
- [ ] 测试运行成功（手动触发）
- [ ] Agent验证：Actions日志显示成功

**Agent-Executed QA Scenarios**:
```
Scenario: 验证GitHub Actions配置正确
  Tool: Bash
  Steps:
    1. 推送workflow到main分支
    2. 手动触发: gh workflow run crawler.yml
    3. 检查运行状态: gh run list --workflow=crawler.yml
    4. 等待完成，查看日志
    5. 断言: 状态为success
  Expected Result: Actions成功运行
  Evidence: Actions运行记录链接
```

**Workflow配置**:
```yaml
# .github/workflows/crawler.yml
name: RSS Crawler

on:
  schedule:
    - cron: '0 */6 * * *'  # 每6小时
  workflow_dispatch:  # 支持手动触发

jobs:
  crawl:
    runs-on: ubuntu-latest
    timeout-minutes: 360  # 6小时上限
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
        cache: 'pip'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    
    - name: Run crawler
      env:
        SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
        SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
        WORKER_URL: ${{ secrets.WORKER_URL }}
      run: |
        python scripts/crawler.py
    
    - name: Cleanup old data
      env:
        SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
        SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
      run: |
        python scripts/cleanup.py
```

**Commit**: YES
- Message: `feat(ci): configure GitHub Actions scheduled crawler`
- Files: `.github/workflows/crawler.yml`

---

### Task 9: 90天自动清理脚本

**What to do**:
- 创建 `scripts/cleanup.py`
- 实现清理逻辑：
  - 计算90天前的日期
  - 删除articles表中fetched_at < 90天前的记录
  - 记录删除数量到cleanup_logs表
- 配置在GitHub Actions最后一步运行

**Must NOT do**:
- 不删除rss_sources表（永久保留）
- 不删除最近90天的数据

**Recommended Agent Profile**:
- **Category**: `quick`
- **Skills**: 无需特殊技能
- **Reason**: 简单的SQL删除操作

**Parallelization**:
- **Can Run In Parallel**: NO
- **Parallel Group**: Wave 5
- **Blocks**: None
- **Blocked By**: Task 7, Task 8

**Acceptance Criteria**:
- [ ] 清理脚本实现
- [ ] 删除90天前的articles记录
- [ ] 记录清理日志
- [ ] 集成到GitHub Actions
- [ ] Agent验证：测试删除旧数据

**Agent-Executed QA Scenarios**:
```
Scenario: 验证清理脚本工作正常
  Tool: Bash
  Steps:
    1. 插入测试旧数据（91天前）
    2. 运行清理: python scripts/cleanup.py --dry-run
    3. 检查将要删除的数量
    4. 实际运行（不带dry-run）
    5. 验证数据已删除
  Expected Result: 旧数据被清理，新数据保留
  Evidence: 清理前后数据量对比
```

**代码结构**:
```python
# scripts/cleanup.py
from supabase import create_client
from datetime import datetime, timedelta
import os
import sys

def cleanup_old_articles(dry_run=False):
    supabase = create_client(
        os.getenv('SUPABASE_URL'),
        os.getenv('SUPABASE_KEY')
    )
    
    # 计算90天前的日期
    cutoff_date = (datetime.now() - timedelta(days=90)).isoformat()
    
    # 查询将要删除的记录数
    count_result = supabase.table('articles')\
        .select('id', count='exact')\
        .lt('fetched_at', cutoff_date)\
        .execute()
    
    count = count_result.count
    
    if dry_run:
        print(f"[DRY RUN] Would delete {count} articles older than {cutoff_date}")
        return
    
    if count == 0:
        print("No old articles to cleanup")
        return
    
    # 删除旧数据
    result = supabase.table('articles')\
        .delete()\
        .lt('fetched_at', cutoff_date)\
        .execute()
    
    print(f"Deleted {count} articles older than {cutoff_date}")
    
    # 记录清理日志
    supabase.table('cleanup_logs').insert({
        'deleted_count': count,
        'cutoff_date': cutoff_date
    }).execute()

if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    cleanup_old_articles(dry_run)
```

**Commit**: YES
- Message: `feat(cleanup): add 90-day data retention cleanup script`
- Files: `scripts/cleanup.py`

---

### Task 10: 端到端集成测试与文档

**What to do**:
- 创建端到端测试：`tests/test_e2e.py`
  - 完整运行一次爬取流程
  - 验证数据正确写入
  - 验证SimHash去重
  - 验证清理功能
- 创建项目README：
  - 架构说明
  - 部署步骤
  - 环境变量配置
  - 运行方式
- 创建贡献指南（可选）

**Must NOT do**:
- 不在测试中使用真实Secrets（使用测试数据库）
- 不测试全部558个源（选取5个代表性源）

**Recommended Agent Profile**:
- **Category**: `unspecified-medium`
- **Skills**: 无需特殊技能
- **Reason**: 测试和文档编写

**Parallelization**:
- **Can Run In Parallel**: NO
- **Parallel Group**: Wave 5
- **Blocks**: None
- **Blocked By**: Task 7, Task 8

**Acceptance Criteria**:
- [ ] 端到端测试脚本
- [ ] 完整README文档
- [ ] 部署指南
- [ ] Agent验证：完整运行测试流程

**Agent-Executed QA Scenarios**:
```
Scenario: 验证端到端流程
  Tool: Bash
  Steps:
    1. 运行完整测试: python tests/test_e2e.py
    2. 检查所有组件: crawler, dedup, cleanup
    3. 验证数据库: 查询articles表有新数据
    4. 检查SimHash: 相似文章被识别
    5. 断言: 所有检查通过
  Expected Result: 系统完整运行正常
  Evidence: 测试报告
```

**Commit**: YES
- Message: `docs: add comprehensive README and E2E tests`
- Files: `README.md`, `tests/test_e2e.py`, `docs/`

---

## 提交策略

| After Task | Message | Files | Verification |
|------------|---------|-------|--------------|
| 1 | `feat(data): extract RSS sources from markdown files` | data/sources.json, scripts/extract_sources.py | jq验证JSON格式 |
| 2 | `feat(db): setup Supabase project and database schema` | sql/schema.sql, .env.example | curl验证连接 |
| 3 | `feat(db): import RSS sources to Supabase` | scripts/import_sources.py | curl验证数量 |
| 4 | `feat(worker): deploy Cloudflare content extraction service` | workers/content-extractor/* | curl验证API |
| 5 | `feat(crawler): implement async RSS crawler with hybrid extraction` | scripts/crawler.py, requirements.txt | 运行测试 |
| 6 | `feat(dedup): implement SimHash duplicate detection` | scripts/dedup.py, tests/test_simhash.py | 测试SimHash |
| 7 | `feat(cleaner): add data cleaning module` | scripts/cleaner.py, tests/test_cleaner.py | 测试清洗 |
| 8 | `feat(ci): configure GitHub Actions scheduled crawler` | .github/workflows/crawler.yml | Actions验证 |
| 9 | `feat(cleanup): add 90-day data retention cleanup script` | scripts/cleanup.py | 测试清理 |
| 10 | `docs: add comprehensive README and E2E tests` | README.md, tests/test_e2e.py | 完整测试 |

---

## 成功标准

### 验证命令
```bash
# 1. 验证数据提取
jq '. | length' data/sources.json  # Expected: ~558

# 2. 验证数据库连接
curl -s "$SUPABASE_URL/rest/v1/rss_sources?select=id" | jq '. | length'  # Expected: ~558

# 3. 验证Worker部署
curl -s "$WORKER_URL/health"  # Expected: {"status":"ok"}

# 4. 验证爬虫运行
python scripts/crawler.py --test  # Expected: 成功

# 5. 验证SimHash
python tests/test_simhash.py  # Expected: 通过

# 6. 验证Actions
gh run list --workflow=crawler.yml  # Expected: 成功运行记录

# 7. 验证清理
python scripts/cleanup.py --dry-run  # Expected: 显示统计
```

### 最终检查清单
- [ ] 所有558个RSS源录入数据库
- [ ] GitHub Actions每6小时自动运行
- [ ] SimHash去重识别转载文章
- [ ] 90天数据自动清理
- [ ] 零云服务费（在免费额度内）
- [ ] 完整README文档

---

## 附录

### 环境变量清单

创建 `.env` 文件（不提交到git）：
```bash
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=eyJ...  # service_role key
WORKER_URL=https://content-extractor.xxx.workers.dev
```

### 免费额度监控

每月检查点：
- **GitHub Actions**: Settings → Billing → Actions（确保<2000分钟）
- **Supabase**: Dashboard → Database Usage（确保<500MB）
- **Cloudflare Workers**: Dashboard → Analytics（确保<100k请求/天）

### 故障排查

**问题1**: Actions超时（>6小时）
- 解决：减少每批处理数量，分批运行

**问题2**: Supabase存储满（500MB）
- 解决：减少保留天数（90→60→30）

**问题3**: Worker请求超限
- 解决：减少反爬站点的提取频率

**问题4**: SimHash误判
- 解决：调整汉明距离阈值（3→2或4）
