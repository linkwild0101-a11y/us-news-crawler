# US-Monitor 热点分析系统

## TL;DR（概要）

> **快速概述**：构建一个智能分析流水线，使用 Jaccard 相似度算法对爬取的 RSS 新闻文章（199个来源）进行聚类，按领域分类（政治/地缘政治、经济、军事），并使用阿里 Qwen3-Plus 大模型生成热点分析和趋势检测。作为独立的 GitHub Actions 工作流在爬虫完成后运行。
>
> **交付物**：
> 
> **核心分析**：
> - 数据库表结构：`analysis_clusters`、`analysis_signals` 表
> - Python 分析流水线：`scripts/analyzer.py`（中文输出）
> - LLM 集成：阿里 Qwen3-Plus API 客户端（中文提示词）
> - 聚类引擎：Jaccard 相似度 + 倒排索引
> - 信号检测：新闻速度激增、来源汇聚、情报三角验证、热点升级
> - GitHub Actions 工作流：`.github/workflows/analyzer.yml`
> 
> **免费数据源**：
> - FRED 客户端：美国经济数据（免费，需API key）
> - GDELT 客户端：全球事件数据库（完全免费）
> - USGS 客户端：地震数据（完全免费）
> - 世界银行客户端：经济指标（完全免费）
> - 增强信号：数据源融合增强信号
> 
> **UI 仪表板**：
> - Streamlit Web应用：中文界面
> - 页面：概览首页、热点详情、信号中心、数据统计
> - 移动端响应式支持
> - 一键部署文档
>
> **预计工作量**：大型项目（10-12小时）
> **并行执行**：是 - 6个波次（基础→核心→集成→验证→增强→最终）
> **关键路径**：数据库表结构→聚类引擎→分析器→增强分析器→最终测试
> **新增功能**：中文输出、Web UI仪表板、4个免费数据源集成

---

## 背景

### 原始需求
"帮我学习worldmonitor，设计一个基于现在爬取数据的热点分析功能，可以分为政治/地缘 经济 军事三个分类。总结分析使用阿里qwen3-plus的在线大模型。"

（学习 worldmonitor，基于当前爬取的数据设计热点分析功能，分为政治/地缘政治、经济、军事三个分类。使用阿里 Qwen3-Plus 大模型进行总结分析。）

### 访谈总结

**关键讨论**：
- 修复了爬虫 bug（时间戳格式、Twitter/X 头信息溢出）
- RSS 来源从 172 扩展到 199（添加了 worldmonitor 的优质来源）
- 当前数据库：1000+ 篇独立文章，SimHash 去重正常工作
- 调度：GitHub Actions 每天两次（美国东部时间上午9点/晚上9点）
- Cloudflare Worker 已部署用于内容提取

**用户意图**：在现有爬虫基础设施上构建智能分析层，借鉴 worldmonitor 的架构，但适配美国新闻监控场景。

### 研究发现

**WorldMonitor 架构分析**：
- **analysis-core.ts**：Jaccard 相似度聚类（相似度阈值=0.5）、停用词分词、倒排索引高效匹配
- **hotspot-escalation.ts**：动态升级评分，加权组件（新闻35%、国家不稳定指数25%、地理汇聚25%、军事活动15%）、信号冷却（2小时）、历史趋势追踪
- **analysis.worker.ts**：Web Worker 离线处理 O(n²) 聚类、分析间状态持久化、信号去重
- **analysis-constants.ts**：信号类型及上下文说明（重要性、可执行建议、置信度说明）、主题关键词映射

**需采用的关键模式**：
1. 核心分析使用纯函数（无副作用）
2. 聚类流程：分词→Jaccard 相似度→倒排索引优化
3. 信号类型：新闻速度激增、来源汇聚、情报三角验证、热点升级
4. 通过 generateDedupeKey 进行信号去重
5. 升级评分加权（新闻速度、来源多样性、地理汇聚）

### Metis 审查

**已识别的缺口**（本计划已解决）：
1. 输出格式定义：结构化 JSON，包含摘要、信号、升级评分
2. 时间窗口：最近24小时的未分析文章
3. 增量处理：只分析 `analyzed_at IS NULL` 的文章
4. LLM 策略：每聚类摘要（非每篇文章，控制成本）
5. 范围锁定：无实时处理、无自定义 ML
6. 热点定义：基于主题/话题的聚类（非 worldmonitor 的地理方式）
7. 语言：英文输出（数据来源为英文）
8. 分析工作流：独立于爬虫，爬虫完成后触发

**应用的防护栏**：
- 每次运行最多 500 篇文章（GitHub Actions 时间限制）
- 每次运行最多 200 次 LLM API 调用（成本控制）
- API 调用前估算 token
- 指数退避重试逻辑（3次尝试）
- 长内容截断至 4000 字符
- 跳过内容<100字符、标题<10字符的文章
- 分析结果保留 90 天

---

## 工作目标

### 核心目标
实现一个智能新闻分析流水线，使用 LLM 驱动的摘要和借鉴 worldmonitor 的聚类及信号检测算法，将原始爬取的 RSS 文章转化为可操作的热点情报。

### 具体交付物
#### 核心分析
- `sql/analysis_schema.sql` - 分析结果的数据库表
- `scripts/analyzer.py` - 主分析流水线
- `scripts/clustering.py` - Jaccard 相似度聚类引擎
- `scripts/llm_client.py` - 阿里 Qwen3-Plus API 客户端（中文输出）
- `scripts/signal_detector.py` - 信号检测算法
- `.github/workflows/analyzer.yml` - GitHub Actions 工作流
- `.env.example` - 更新分析配置
- `config/analysis_config.py` - 阈值、提示词（中文）、常量

#### 数据源（免费/低成本）
- `scripts/datasources/fred_client.py` - FRED 美国经济数据（免费，需API key）
- `scripts/datasources/gdelt_client.py` - GDELT 全球事件数据库（免费）
- `scripts/datasources/earthquake_client.py` - USGS 地震数据（免费）
- `scripts/datasources/worldbank_client.py` - 世界银行指标（免费）
- `scripts/datasources/enhanced_signals.py` - 增强信号检测（结合多数据源）

#### UI 仪表板
- `web/app.py` - Flask/Streamlit Web 应用主入口
- `web/templates/index.html` - 主仪表板页面（中文界面）
- `web/templates/hotspots.html` - 热点详情页
- `web/templates/signals.html` - 信号列表页
- `web/static/css/style.css` - 样式表
- `web/static/js/dashboard.js` - 前端交互
- `web/data_api.py` - 数据查询API
- `web/README.md` - UI部署说明

### 完成定义
- [ ] 分析流水线在30分钟内完成500篇文章
- [ ] 成功调用阿里 Qwen3-Plus API 并存储结构化 JSON 结果
- [ ] 将1000篇文章聚类为50-200个有意义的聚类（通过数据库查询验证）
- [ ] 在有重大新闻时每次运行至少检测1个信号
- [ ] 只处理未分析的文章（验证增量处理）
- [ ] 所有验收标准通过代理执行的 QA 场景

### 必须有
- 聚类和信号的数据库表结构
- Jaccard 相似度聚类 + 倒排索引
- 阿里 Qwen3-Plus LLM 集成
- 每聚类摘要
- 信号检测：新闻速度激增、来源汇聚
- 增量处理（仅新文章）
- 优雅降级的错误处理
- GitHub Actions 工作流

### 必须不包含（防护栏）
- **无实时处理** - 仅批处理，通过 GitHub Actions 调度
- **无自定义 ML 模型** - 仅使用 Qwen3-Plus，不训练模型
- **无市场数据集成** - 跳过预测市场领先新闻、新闻领先市场信号（无市场数据源）
- **无高级信号（初期）** - 仅4个核心信号

### 与原始计划的关键变更
1. **中文输出** - 所有分析摘要用中文输出，但保留英文原文链接供溯源
2. **UI展示** - 添加 Web 仪表板，展示热点分析结果（Python Flask/Streamlit）
3. **免费数据源增强** - 集成 worldmonitor 中可用的免费/低成本数据源

---

## 验证策略

> **通用规则：零人工干预**
>
> 所有任务必须通过代理使用工具验证，无需人工测试。

### 测试决策
- **基础设施存在**：是 - Supabase PostgreSQL 已配置
- **自动化测试**：事后测试（核心实现后添加单元测试）
- **框架**：Python unittest（与现有脚本一致）

### 代理执行的 QA 场景（强制）

每个任务包含具体场景，包括确切命令、断言和证据路径。

**按类型分类的验证工具：**
| 类型 | 工具 | 代理如何验证 |
|------|------|--------------|
| **数据库** | Bash (psql) | 查询表、断言行数、验证表结构 |
| **Python** | Bash (python) | 运行脚本、检查退出码、验证输出 |
| **API** | Bash (curl) | 发送请求、解析 JSON、断言状态码 |
| **GitHub Actions** | Web | 检查工作流运行、查看日志 |

---

## 执行策略

### 并行执行波次

```
波次 1（基础 - 可立即开始）：
├── 任务 1：数据库表结构（无依赖）
├── 任务 2：LLM 客户端模块（无依赖）
└── 任务 3：配置与常量（无依赖）

波次 2（核心逻辑 - 波次1后）：
├── 任务 4：聚类引擎（依赖：任务3）
└── 任务 5：信号检测（依赖：任务3）

波次 3（集成 - 波次2后）：
├── 任务 6：主分析器流水线（依赖：1, 2, 4, 5）
└── 任务 7：GitHub Actions 工作流（依赖：6）

波次 4（验证 - 波次3后）：
└── 任务 8：端到端测试（依赖：7）

波次 5（增强 - 波次1后可开始）：
├── 任务 9：免费数据源
└── 任务 10：UI 仪表板

波次 6（最终集成）：
├── 任务 11：增强分析器
└── 任务 12：最终 E2E 测试

关键路径：任务 1 → 任务 4 → 任务 6 → 任务 11 → 任务 12
UI 路径：任务 1 → 任务 10（独立，可单独使用）
```

### 依赖矩阵

| 任务 | 依赖于 | 阻塞 | 可与以下并行 |
|------|--------|------|--------------|
| 1 | 无 | 6 | 2, 3 |
| 2 | 无 | 6 | 1, 3 |
| 3 | 无 | 4, 5 | 1, 2 |
| 4 | 3 | 6 | 5 |
| 5 | 3 | 6 | 4 |
| 6 | 1, 2, 4, 5 | 7 | 无 |
| 7 | 6 | 8 | 无 |
| 8 | 7 | 无 | 无 |
| 9 | 3 | 11 | 10 |
| 10 | 1 | 无 | 9 |
| 11 | 6, 9 | 12 | 无 |
| 12 | 11 | 无 | 无 |

---

## TODO清单

### 任务 1：数据库表结构

**做什么**：
创建分析结果的 SQL 表结构：
1. `analysis_clusters` 表 - 存储聚类信息
2. `analysis_signals` 表 - 存储检测到的信号
3. `article_analyses` 关联表 - 关联文章与聚类
4. 在现有 `articles` 表添加 `analyzed_at` 列
5. 创建性能索引

**禁止做**：
- 不要修改现有 `articles` 表结构（添加 `analyzed_at` 除外）
- 不要删除现有表
- 不要创建会阻塞删除的外键约束

**推荐代理配置**：
- **类别**：unspecified-low
- **原因**：SQL 表结构创建简单，复杂度低
- **技能**：无需

**并行化**：
- **可并行**：是 - 波次 1
- **阻塞**：任务 6（主分析器）
- **被阻塞于**：无

**参考**：
- 模式：遵循 `sql/schema.sql` 中的现有表结构
- 相似表：`articles` 表的列类型
- WorldMonitor：`analysis-core.ts:ClusteredEventCore` 接口的数据结构

**验收标准**：

**代理执行的 QA 场景：**

```
场景：表结构创建成功
  工具：Bash (psql)
  前置条件：Supabase 凭证在环境中
  步骤：
    1. 运行：psql $SUPABASE_URL -f sql/analysis_schema.sql
    2. 断言：退出码 0
    3. 查询：\dt analysis_*
    4. 断言：显示 analysis_clusters、analysis_signals、article_analyses

场景：表结构正确
  工具：Bash (psql)
  步骤：
    1. 查询：SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'analysis_clusters'
    2. 断言：列包含 id、cluster_key、category、primary_title、summary、article_count、created_at、updated_at
    3. 查询：SELECT column_name FROM information_schema.columns WHERE table_name = 'articles' AND column_name = 'analyzed_at'
    4. 断言：存在 analyzed_at 列
    5. 证据：查询结果截图

场景：为性能创建索引
  工具：Bash (psql)
  步骤：
    1. 查询：SELECT indexname FROM pg_indexes WHERE tablename = 'analysis_clusters'
    2. 断言：存在 cluster_key 索引
    3. 断言：存在 created_at 索引
    4. 证据：保存查询输出
```

**提交**：是
- 消息：`feat(db): add analysis schema for hotspot detection`
- 文件：`sql/analysis_schema.sql`
- 提交前：验证表结构应用无错误

---

### 任务 2：LLM 客户端模块

**做什么**：
创建阿里 Qwen3-Plus API 集成的 Python 模块：
1. `scripts/llm_client.py` - API 客户端类
2. 使用 API key 实现认证
3. JSON 模式的请求/响应处理
4. Token 估算和成本追踪
5. 指数退避重试逻辑（3次尝试）
6. 响应缓存避免重复调用
7. 速率限制、超时、畸形响应的错误处理

**禁止做**：
- 不要实现流式响应（不需要）
- 初期不要支持多个 LLM 提供商
- 不要实现微调或自定义模型

**推荐代理配置**：
- **类别**：unspecified-high
- **原因**：API 集成需要健壮的错误处理、重试逻辑、异步模式
- **技能**：无需（纯 Python）

**并行化**：
- **可并行**：是 - 波次 1
- **阻塞**：任务 6（主分析器）
- **被阻塞于**：无

**参考**：
- WorldMonitor：`api/groq-summarize.js` 的 API 调用模式和缓存策略
- 现有代码：`scripts/crawler.py` 的 Supabase 客户端模式
- 外部：阿里 DashScope API 文档 (https://help.aliyun.com/zh/dashscope/)

**验收标准**：

**代理执行的 QA 场景：**

```
场景：LLM 客户端用 API key 初始化
  工具：Bash (python)
  前置条件：ALIBABA_API_KEY 在环境中设置
  步骤：
    1. 运行：python -c "from scripts.llm_client import LLMClient; c = LLMClient(); print('Initialized')"
    2. 断言：输出包含 "Initialized"
    3. 断言：退出码 0

场景：API 调用返回结构化 JSON
  工具：Bash (python)
  步骤：
    1. 创建测试脚本：test_llm.py（任务中提供）
    2. 运行：python test_llm.py
    3. 断言：响应是有效 JSON
    4. 断言：响应包含预期字段（summary, keywords, sentiment）
    5. 证据：保存响应到 .sisyphus/evidence/task-2-llm-response.json

场景：失败时重试有效
  工具：Bash (python)
  步骤：
    1. 临时配置无效 API key
    2. 运行：python -c "from scripts.llm_client import LLMClient; c = LLMClient(); c.summarize('test')" 2>&1
    3. 断言：日志显示 3 次重试尝试
    4. 断言：最终错误是优雅的（非崩溃）
    5. 证据：重试日志截图

场景：缓存防止重复调用
  工具：Bash (python)
  步骤：
    1. 用相同输入调用 LLM 两次
    2. 断言：第二次调用返回缓存结果（更快，无 API 日志）
    3. 证据：比较日志中的时间戳
```

**提交**：是
- 消息：`feat(llm): add Alibaba Qwen3-Plus client with retry and caching`
- 文件：`scripts/llm_client.py`, `.env.example`（更新）
- 提交前：验证客户端导入无错误

---

### 任务 3：配置与常量

**做什么**：
创建集中配置模块：
1. `config/analysis_config.py` - 所有阈值和常量
2. 定义 Jaccard 相似度阈值（默认：0.5）
3. 定义分词停用词
4. 定义每个分类的主题关键词（军事、政治、经济）
5. 定义信号检测阈值
6. 定义 LLM 提示词（聚类摘要、信号解释）
7. 定义批大小和限制

**禁止做**：
- 不要硬编码值到其他模块
- 不要创建循环依赖

**推荐代理配置**：
- **类别**：quick
- **原因**：简单常量定义，低复杂度
- **技能**：无需

**并行化**：
- **可并行**：是 - 波次 1
- **阻塞**：任务 4、5（聚类、信号检测）
- **被阻塞于**：无

**参考**：
- WorldMonitor：`analysis-constants.ts` 的停用词、主题关键词、阈值
- WorldMonitor：`analysis-core.ts` 的信号类型定义
- 现有：`scripts/crawler.py` 的批大小模式

**验收标准**：

**代理执行的 QA 场景：**

```
场景：配置正确加载
  工具：Bash (python)
  步骤：
    1. 运行：python -c "from config.analysis_config import SIMILARITY_THRESHOLD, STOP_WORDS; print(f'Threshold: {SIMILARITY_THRESHOLD}')"
    2. 断言：退出码 0
    3. 断言：输出显示阈值值（0.5）

场景：停用词已定义
  工具：Bash (python)
  步骤：
    1. 运行：python -c "from config.analysis_config import STOP_WORDS; print(f'Count: {len(STOP_WORDS)}')"
    2. 断言：STOP_WORDS 包含常见词（the, a, an, and）
    3. 断言：数量 > 20
    4. 证据：打印停用词样本

场景：主题关键词已分类
  工具：Bash (python)
  步骤：
    1. 运行：python -c "from config.analysis_config import TOPIC_KEYWORDS; print(TOPIC_KEYWORDS)"
    2. 断言：有键：'military'、'politics'、'economy'
    3. 断言：每个分类有 10+ 关键词
    4. 证据：保存输出

场景：LLM 提示词已定义
  工具：Bash (python)
  步骤：
    1. 运行：python -c "from config.analysis_config import LLM_PROMPTS; print(LLM_PROMPTS.keys())"
    2. 断言：包含 'cluster_summary' 键
    3. 断言：提示词是非空字符串且包含说明
    4. 证据：保存提示词内容
```

**提交**：是
- 消息：`feat(config): add analysis configuration with thresholds and prompts`
- 文件：`config/analysis_config.py`, `config/__init__.py`
- 提交前：验证导入有效

---

### 任务 4：聚类引擎

**做什么**：
实现 Jaccard 相似度聚类（纯函数）：
1. `scripts/clustering.py` - 核心聚类逻辑
2. `tokenize(title)` - 停用词分词
3. `jaccard_similarity(set1, set2)` - 相似度计算
4. `cluster_news(articles)` - 带倒排索引优化的主聚类
5. 基于内容哈希生成聚类 ID
6. 按来源等级和时效排序聚类
7. 返回带元数据的聚类对象

**禁止做**：
- 不要使用 scikit-learn 或外部 ML 库（保持纯 Python）
- 不要修改输入文章
- 不要访问数据库（纯函数）

**推荐代理配置**：
- **类别**：unspecified-high
- **原因**：算法实现需要仔细优化，管理 O(n²) 复杂度
- **技能**：无需（纯 Python 算法）

**并行化**：
- **可并行**：是 - 波次 2
- **阻塞**：任务 6（主分析器）
- **被阻塞于**：任务 3（配置）

**参考**：
- WorldMonitor：`analysis-core.ts:154-280` - clusterNewsCore 实现
- WorldMonitor：`analysis-constants.ts:59-73` - tokenize 和 jaccardSimilarity
- 模式：倒排索引实现 O(n) 候选选择而非 O(n²) 比较

**验收标准**：

**代理执行的 QA 场景：**

```
场景：分词正确工作
  工具：Bash (python)
  步骤：
    1. 运行：python -c "from scripts.clustering import tokenize; print(tokenize('The quick brown fox'))"
    2. 断言：返回不含停用词（the）的集合
    3. 断言：包含 'quick'、'brown'、'fox'
    4. 证据：输出显示正确的 tokens

场景：Jaccard 相似度正确计算
  工具：Bash (python)
  步骤：
    1. 运行：python -c "from scripts.clustering import jaccard_similarity; print(jaccard_similarity({'a','b'}, {'a','b'}))"
    2. 断言：相同集合返回 1.0
    3. 用 {'a','b'}, {'c','d'} 运行
    4. 断言：不相交集合返回 0.0
    5. 证据：测试结果截图

场景：聚类将相似文章分组
  工具：Bash (python)
  步骤：
    1. 创建5篇文章的测试数据（3篇相似，2篇不同）
    2. 运行：python -c "from scripts.clustering import cluster_news; import json; clusters = cluster_news(test_data); print(f'Clusters: {len(clusters)}')"
    3. 断言：创建 2-3 个聚类（非5个独立）
    4. 断言：相似文章分组在一起
    5. 证据：打印聚类分配

场景：倒排索引优化有效
  工具：Bash (python)
  步骤：
    1. 用100篇文章测试
    2. 测量有/无倒排索引的时间
    3. 断言：有倒排索引明显更快
    4. 证据：保存计时日志
```

**提交**：是
- 消息：`feat(clustering): implement Jaccard similarity clustering with inverted index`
- 文件：`scripts/clustering.py`
- 提交前：单元测试通过

---

### 任务 5：信号检测

**做什么**：
实现信号检测算法：
1. `scripts/signal_detector.py` - 信号检测模块
2. `detect_velocity_spike(clusters)` - 新闻速度激增检测
3. `detect_convergence(clusters)` - 多来源类型确认
4. `detect_triangulation(clusters)` - 通讯社+政府+情报机构对齐
5. `detect_hotspot_escalation(clusters)` - 复合升级评分
6. `generate_signal_id()`, `generate_dedupe_key()` - 工具函数
7. 返回带置信度评分的信号对象

**禁止做**：
- 不要实现 prediction_leads_news 或 news_leads_markets（无市场数据）
- 不要实现 flow_drop 或 flow_price_divergence（无管道数据）
- 不要访问外部 API

**推荐代理配置**：
- **类别**：unspecified-high
- **原因**：算法逻辑需要仔细的阈值调整和权重计算
- **技能**：无需

**并行化**：
- **可并行**：是 - 波次 2
- **阻塞**：任务 6（主分析器）
- **被阻塞于**：任务 3（配置）

**参考**：
- WorldMonitor：`analysis-core.ts:302-434` - detectPipelineFlowDrops、detectConvergence、detectTriangulation
- WorldMonitor：`hotspot-escalation.ts` - 加权组件的升级评分
- WorldMonitor：`analysis-constants.ts` - 解释的 SIGNAL_CONTEXT

**验收标准**：

**代理执行的 QA 场景：**

```
场景：检测到速度激增
  工具：Bash (python)
  步骤：
    1. 创建一个聚类在1小时内有10+来源的测试聚类
    2. 运行：python -c "from scripts.signal_detector import detect_velocity_spike; signals = detect_velocity_spike(clusters)"
    3. 断言：返回 velocity_spike 信号
    4. 断言：置信度 > 0.6
    5. 证据：打印信号详情

场景：检测到汇聚
  工具：Bash (python)
  步骤：
    1. 创建有3+不同来源类型的测试聚类
    2. 运行：python -c "from scripts.signal_detector import detect_convergence; signals = detect_convergence(clusters)"
    3. 断言：返回 convergence 信号
    4. 断言：描述中列出来源类型
    5. 证据：保存信号输出

场景：检测到三角验证
  工具：Bash (python)
  步骤：
    1. 创建有通讯社+政府+情报来源的测试聚类
    2. 运行：python -c "from scripts.signal_detector import detect_triangulation; signals = detect_triangulation(clusters)"
    3. 断言：返回 triangulation 信号
    4. 断言：置信度 >= 0.9
    5. 证据：截图

场景：信号去重有效
  工具：Bash (python)
  步骤：
    1. 用相同聚类两次调用 detect_velocity_spike
    2. 断言：generate_dedupe_key 对相同输入返回相同键
    3. 断言：第二次调用会被去重逻辑过滤
    4. 证据：显示去重键匹配
```

**提交**：是
- 消息：`feat(signals): implement velocity, convergence, triangulation detection`
- 文件：`scripts/signal_detector.py`
- 提交前：单元测试通过

---

*【由于文件很长，我将继续翻译剩余部分...】*