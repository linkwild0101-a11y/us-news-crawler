# US-Monitor 热点分析系统 - 配置与使用手册

## 目录
1. [新增数据源配置](#1-新增数据源配置)
2. [API配置方式](#2-api配置方式)
3. [系统使用指南](#3-系统使用指南)
4. [故障排查](#4-故障排查)

---

## 1. 新增数据源配置

### 1.1 添加到数据库

**方式一：直接操作Supabase**

```sql
-- 插入新RSS源
INSERT INTO rss_sources (name, rss_url, category, status, anti_scraping)
VALUES (
    'Source Name',                    -- 源名称
    'https://example.com/feed.xml',   -- RSS地址
    'politics',                       -- 分类：military/politics/economy
    'active',                         -- 状态
    'None'                            -- 反爬标记：None/Cloudflare/Paywall
);
```

**方式二：使用Python脚本**

```python
from supabase import create_client
import os

supabase = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

# 添加单个源
supabase.table('rss_sources').insert({
    'name': 'New Source',
    'rss_url': 'https://example.com/feed.xml',
    'category': 'politics',
    'status': 'active',
    'anti_scraping': 'None'
}).execute()

# 批量添加
sources = [
    {'name': 'Source 1', 'rss_url': '...', 'category': 'military'},
    {'name': 'Source 2', 'rss_url': '...', 'category': 'economy'},
]
supabase.table('rss_sources').insert(sources).execute()
```

### 1.2 源分类说明

| 分类 | 说明 | 示例 |
|------|------|------|
| `military` | 军事/国防相关 | DoD, Jane's, RAND |
| `politics` | 政治/地缘政治 | 白宫, 国务院, Politico |
| `economy` | 经济/金融 | Fed, WSJ, Bloomberg |

### 1.3 反爬标记说明

| 标记 | 含义 | 处理方式 |
|------|------|----------|
| `None` | 普通源 | 直接访问 |
| `Cloudflare` | Cloudflare保护 | 尝试Worker → Railway代理 |
| `Paywall` | 付费墙 | 尝试Worker → Railway代理 |
| `railway` | 仅Railway可访问 | 直接通过Railway代理 |

### 1.4 验证新源

添加后运行验证工作流测试：

```bash
# 本地验证
python scripts/validate_rss.py

# 或GitHub Actions页面手动触发 "Validate RSS Sources"
```

---

## 2. API配置方式

### 2.1 必需API配置

#### 2.1.1 Supabase (数据库)

**获取方式**：
1. 访问 https://supabase.com
2. 创建项目
3. 进入 Project Settings → API
4. 复制 URL 和 anon/service_role key

**GitHub Secrets配置**：
```
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIs...
```

**本地环境变量** (`.env`):
```bash
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIs...
```

#### 2.1.2 阿里DashScope (LLM)

**获取方式**：
1. 访问 https://dashscope.aliyun.com
2. 注册/登录阿里云账号
3. 进入控制台 → API Key管理
4. 创建新的API Key

**支持的模型**：
- `qwen3-plus` (推荐，性价比高)
- `qwen3-max` (质量更好，更贵)

**GitHub Secrets配置**：
```
ALIBABA_API_KEY=sk-xxxxx
```

**费用**：
- 输入：¥0.002 / 1K tokens
- 输出：¥0.006 / 1K tokens
- 每次分析约 ¥1-2 元

### 2.2 可选API配置

#### 2.2.1 FRED (美国经济数据)

**获取方式**：
1. 访问 https://fred.stlouisfed.org
2. 注册账号
3. 访问 https://fred.stlouisfed.org/docs/api/api_key.html
4. 申请API Key（免费）

**GitHub Secrets配置**：
```
FRED_API_KEY=xxxxxxxx
```

**功能**：
- 联邦基金利率
- CPI/PPI数据
- 失业率
- GDP增长

**限制**：
- 120 requests/minute
- 完全免费

#### 2.2.2 GDELT (全球事件数据库)

**特点**：
- ✅ 无需API Key
- ✅ 完全免费
- ✅ 无访问限制

**直接使用**，无需配置

**功能**：
- 全球冲突事件
- 抗议活动
- 地缘政治事件

#### 2.2.3 USGS (地震数据)

**特点**：
- ✅ 无需API Key
- ✅ 完全免费

**直接使用**，无需配置

**功能**：
- 4.5级以上地震
- 实时数据

#### 2.2.4 World Bank (世界银行)

**特点**：
- ✅ 无需API Key
- ✅ 完全免费

**直接使用**，无需配置

**功能**：
- 各国GDP
- 研发支出
- 互联网普及率

### 2.3 Railway代理配置

**Railway已部署**：
```
RAILWAY_URL=https://us-news-crawler-production.up.railway.app
```

**GitHub Secrets配置**：
```
RAILWAY_URL=https://your-app.up.railway.app
```

**本地测试**：
```bash
curl https://us-news-crawler-production.up.railway.app/health
```

### 2.4 Cloudflare Worker (备用)

**Worker URL**:
```
WORKER_URL=https://content-extractor.linkwild0101.workers.dev
```

**GitHub Secrets配置**：
```
WORKER_URL=https://your-worker.your-subdomain.workers.dev
```

---

## 3. 系统使用指南

### 3.1 自动运行 (GitHub Actions)

**默认调度**：
- 爬虫：美东时间 9:00 AM / 9:00 PM
- 分析器：爬虫完成后1小时

**查看运行状态**：
1. 访问 https://github.com/[username]/us-news-crawler/actions
2. 查看工作流：
   - `RSS Crawler` - 爬虫
   - `Hotspot Analysis` - 分析器
   - `Validate RSS Sources` - 验证器

**手动触发**：
```bash
# 在GitHub Actions页面点击 "Run workflow"
```

### 3.2 手动运行分析

#### 基础分析

```bash
# 分析所有未分析文章（限制500篇）
python scripts/analyzer.py

# 限制分析数量
python scripts/analyzer.py --limit 100

# 试运行（不保存到数据库）
python scripts/analyzer.py --limit 50 --dry-run
```

#### 增强分析（带外部数据源）

```bash
# 需要配置 FRED_API_KEY
export FRED_API_KEY=your_key

# 运行增强分析
python scripts/enhanced_analyzer.py --limit 100
```

#### 本地测试

```bash
# 测试聚类
python scripts/clustering.py

# 测试信号检测
python scripts/signal_detector.py

# 端到端测试
python tests/test_e2e.py
```

### 3.3 Web仪表板

#### 本地启动

```bash
cd web

# 安装依赖
pip install -r requirements.txt

# 设置环境变量
export SUPABASE_URL=your_url
export SUPABASE_KEY=your_key

# 启动
streamlit run app.py
```

**访问**：http://localhost:8501

#### 页面说明

**🏠 概览首页**：
- 今日统计（聚类数、信号数、文章数）
- TOP 5 热点（带中文摘要）
- 最新信号

**🔥 热点详情**：
- 按分类浏览（军事/政治/经济）
- 聚类详情（摘要、关键实体、影响分析）
- 原文链接跳转

**📡 信号中心**：
- 信号列表（带置信度）
- 按类型筛选
- 统计图表

**📈 数据统计**：
- 聚类趋势图
- 分类占比饼图
- 总体统计

### 3.4 查看分析结果

#### 数据库查询

```sql
-- 查看今日聚类
SELECT * FROM analysis_clusters 
WHERE created_at >= CURRENT_DATE
ORDER BY confidence DESC;

-- 查看今日信号
SELECT * FROM analysis_signals 
WHERE created_at >= CURRENT_DATE
ORDER BY confidence DESC;

-- 查看热点统计
SELECT 
    category,
    COUNT(*) as cluster_count,
    AVG(confidence) as avg_confidence
FROM analysis_clusters
WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY category;
```

#### Python查询

```python
from supabase import create_client
import os

supabase = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

# 获取今日聚类
clusters = supabase.table('analysis_clusters')\
    .select('*')\
    .gte('created_at', '2025-02-17')\
    .order('confidence', desc=True)\
    .execute()

# 获取高置信度信号
signals = supabase.table('analysis_signals')\
    .select('*')\
    .gte('confidence', 0.8)\
    .execute()
```

### 3.5 系统架构图

```
RSS源 (199个)
    ↓
GitHub Actions - 爬虫 (每天2次)
    ↓
Supabase - articles表
    ↓
GitHub Actions - 分析器 (爬虫后1小时)
    ├── 聚类 (Jaccard相似度)
    ├── LLM摘要 (阿里Qwen3-Plus)
    ├── 信号检测 (4种算法)
    └── 保存结果
    ↓
Supabase - analysis_clusters/signals表
    ↓
Web仪表板 (Streamlit)
```

---

## 4. 故障排查

### 4.1 常见问题

#### Q: GitHub Actions运行失败

**检查**：
1. Secrets是否配置正确
2. 查看Actions日志中的具体错误
3. 确认Supabase表结构已创建

**解决**：
```bash
# 重新应用数据库结构
psql $SUPABASE_URL -f sql/analysis_schema.sql
```

#### Q: LLM API调用失败

**检查**：
1. ALIBABA_API_KEY是否正确
2. 账户余额是否充足
3. 是否触发速率限制

**解决**：
- 检查API Key权限
- 充值DashScope账户
- 减少MAX_LLM_CALLS配置

#### Q: Railway代理返回502

**检查**：
1. Railway服务是否运行
2. 查看Railway部署日志

**解决**：
- 在Railway Dashboard重启服务
- 检查端口配置 (PORT=8080)

#### Q: 聚类数量过少

**原因**：
- 相似度阈值太高
- 文章差异大

**调整**：
```python
# 修改 config/analysis_config.py
SIMILARITY_THRESHOLD = 0.4  # 从0.5降低到0.4
```

### 4.2 日志查看

**GitHub Actions日志**：
- Actions页面 → 点击运行记录 → 查看日志

**本地日志**：
```bash
# 运行并查看详细日志
python scripts/analyzer.py --limit 10 2>&1 | tee analyzer.log
```

### 4.3 联系支持

如有问题：
1. 查看GitHub Issues
2. 检查日志中的错误信息
3. 验证所有配置是否正确

---

## 5. 快速参考卡

### 常用命令

```bash
# 手动运行分析
python scripts/analyzer.py --limit 100

# 测试聚类
python scripts/clustering.py

# 测试信号
python scripts/signal_detector.py

# 验证RSS源
python scripts/validate_rss.py

# 启动Web
streamlit run web/app.py

# 端到端测试
python tests/test_e2e.py
```

### 环境变量清单

```bash
# 必需
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJhbGci...
ALIBABA_API_KEY=sk-xxxxx

# 可选
FRED_API_KEY=xxxxxxxx
RAILWAY_URL=https://xxxxx.up.railway.app
WORKER_URL=https://xxxxx.workers.dev
```

### GitHub Secrets清单

| Secret | 用途 | 必需 |
|--------|------|------|
| SUPABASE_URL | 数据库连接 | ✅ |
| SUPABASE_KEY | 数据库认证 | ✅ |
| ALIBABA_API_KEY | LLM API | ✅ |
| FRED_API_KEY | 经济数据 | ❌ |
| RAILWAY_URL | 代理服务 | ❌ |
| WORKER_URL | Cloudflare代理 | ❌ |

---

**文档版本**: v1.0  
**更新日期**: 2025-02-17  
**适用系统**: US-Monitor Hotspot Analysis System v1.0
