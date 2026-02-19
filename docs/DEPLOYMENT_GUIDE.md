# US-Monitor 全量分析系统 - 开发文档

**版本**: Phase 3 (v0.3.0)  
**日期**: 2026-02-18  
**状态**: ✅ 已完成并部署

---

## 目录

1. [系统概述](#系统概述)
2. [架构设计](#架构设计)
3. [Phase 1: 分层并发分析（历史）](#phase-1-分层并发分析历史)
4. [Phase 2: 按需深度分析（历史）](#phase-2-按需深度分析历史)
5. [Phase 3: 全量完整分析](#phase-3-全量完整分析)
6. [实体追踪系统](#实体追踪系统)
7. [前端界面](#前端界面)
8. [配置文件](#配置文件)
9. [性能优化](#性能优化)
10. [部署指南](#部署指南)
11. [故障排除](#故障排除)

---

## 系统概述

### 目标
- **准确性优先**: 全聚类统一完整分析，避免浅层摘要丢信息
- **稳定性优先**: 批量入库、重试与异步补充，降低外部服务抖动影响
- **可读性优先**: 前端高对比主题、原文可跳转、信号解释可快速理解

### 核心功能
1. **全量完整分析**: 所有聚类统一走完整 LLM 分析链路
2. **并发处理**: 默认 10 个 worker 并发处理聚类
3. **LLM 实体分类**: 在总结阶段直接输出实体类型，程序仅做标准化与兜底校验
4. **信号解释增强**: 先规则解释入库，再异步 LLM 增强（可独立补跑）
5. **前端可读性重构**: 强制高对比样式，热点/详情/信号均支持原文链接

---

## 架构设计

### 数据流

```
RSS源 → 爬虫 → 数据库 → 分析器 → 聚类 → LLM处理 → 数据库
                                    ↓
                              全量完整分析
                                    ↓
                         信号检测 → 解释增强 → 实体追踪
```

### 核心组件

| 组件 | 文件 | 职责 |
|------|------|------|
| **分析器** | `scripts/analyzer.py` | 主分析流程，全量完整分析并发处理 |
| **增强分析器** | `scripts/enhanced_analyzer.py` | 扩展外部数据源(FRED/USGS/GDELT) |
| **LLM客户端** | `scripts/llm_client.py` | LLM调用，缓存，翻译 |
| **Web界面** | `web/app.py` | Streamlit前端，热点/信号/详情可跳原文 |
| **实体标准化** | `scripts/entity_classification.py` | LLM实体分类标准化与规则兜底 |

---

## Phase 1: 分层并发分析（历史）

### 1.1 热点/冷门分层逻辑

```python
# 判断标准
hot_threshold = 3  # 文章数阈值

if article_count >= hot_threshold:
    # 热点聚类 → 完整分析
    depth = "full"
    model = "qwen-plus"
else:
    # 冷门聚类 → 快速翻译
    depth = "shallow"
    model = "qwen-flash"
```

### 1.2 并发处理

```python
# ThreadPoolExecutor 5并发
with ThreadPoolExecutor(max_workers=5) as executor:
    future_to_cluster = {
        executor.submit(
            self.generate_cluster_summary, cluster, depth
        ): cluster 
        for cluster in clusters
    }
```

### 1.3 数据库字段

新增字段到 `analysis_clusters` 表:
- `analysis_depth` (varchar): "full" 或 "shallow"
- `is_hot` (boolean): 是否为热点
- `full_analysis_triggered` (boolean): 是否已触发深度分析
- `processing_time` (float): 处理耗时(秒)

### 1.4 成本对比

| 场景 | 原方案 | 新方案 | 节省 |
|------|--------|--------|------|
| 483个聚类(全热点) | ¥48 | ¥48 | 0% |
| 400冷 + 83热 | ¥48 | ~¥10 | 80% |
| 全冷门 | ¥48 | ~¥5 | 90% |

---

## Phase 2: 按需深度分析（历史）

### 2.1 功能说明

在 Web 界面上，对冷门聚类显示 **"🔍 深度分析"** 按钮，点击后:
1. 调用后端 LLM 进行完整分析
2. 更新数据库为完整分析结果
3. 提取并保存实体信息

> 当前主流程已切换为全量完整分析，`trigger_deep_analysis` 与浅层分析入口已移除。

## Phase 3: 全量完整分析

### 3.1 主流程调整

- 移除冷门快速翻译路径，统一完整分析
- 分析并发调整为 `10`（`HotspotAnalyzer.concurrent_workers`）
- 信号检测仍以 `article_count >= 3` 的聚类为目标，但聚类摘要均为完整分析结果

### 3.2 实体分类改造

- LLM 提示词直接输出实体类型（person / organization / location / ...）
- `scripts/entity_classification.py` 负责：
  - 类型归一化（别名映射）
  - 低置信度兜底
  - 人名/组织/节日/地点强规则纠偏
- 入库时统一走标准化后的实体数据结构，减少错分污染

### 3.3 信号解释增强

- 规则解释先入库，保障分析主链路稳定
- 新增异步补充解释能力（已整合进 `scripts/analyzer.py`）：
  - `--enrich-signals-only`
  - `--enrich-signals-after-run`
  - `--enrich-hours`
  - `--enrich-limit`
  - `--enrich-workers`
- `scripts/enhanced_analyzer.py` 同步支持 `--enrich-signals-after-run`

### 3.4 重置能力增强

- `scripts/reset_analysis.py --all` 除文章分析状态外，同时清理：
  - 聚类结果
  - 信号表
  - 实体档案与实体关联

### 3.5 前端改造

- 统一高对比技术风配色，弱化系统亮暗模式干扰
- 热点页仅显示 `is_hot=true`
- 首页与信号中心改为“解释优先”展示，不再堆叠长文本
- 热点、新闻详情、信号关联事件均支持跳转新闻原文链接

---

## 实体追踪系统

### 4.1 实体分类

5种实体类型:

| 类型 | 英文 | 中文关键词 | 英文关键词 |
|------|------|-----------|-----------|
| **event** | 事件 | 事件、战争、冲突、会议 | crisis, war, summit |
| **organization** | 组织 | 公司、银行、大学 | Inc, Corp, University |
| **location** | 地点 | 国、州、市、区 | America, China, City |
| **person** | 人名 | 2-6字符 | James Smith, 张三四 |
| **concept** | 概念 | 其他 | 其他 |

### 4.2 配置文件

文件: `config/entity_config.py`

```python
ENTITY_TYPES = {
    "event": {
        "description": "事件",
        "keywords": {
            "zh": ["事件", "战争", "冲突", ...],
            "en": ["crisis", "war", "summit", ...]
        }
    },
    # ... 其他类型
}

PERSON_RULES = {
    "chinese_name_length": {"min": 2, "max": 6},
    "english_indicators": ["contains_space", "title_capitalized"],
    "common_english_names": ["James", "John", "Mary", ...]  # 600+个
}
```

### 4.3 数据库表

**entities 表**:
- `id` (PK): 实体ID
- `name`: 实体名称
- `entity_type`: 类型(event/org/loc/person/concept)
- `category`: 分类(military/politics/economy/tech)
- `mention_count_total`: 总提及次数
- `mention_count_24h`: 24小时提及
- `mention_count_7d`: 7天提及
- `first_seen`: 首次出现时间
- `last_seen`: 最后出现时间
- `trend_direction`: 趋势(rising/falling/stable)

**entity_cluster_relations 表**:
- `entity_id` (FK)
- `cluster_id` (FK)
- `mention_count`

### 4.4 实体档案页面

Web界面 "📁 实体档案" 页面:
- 显示前10热门实体（卡片形式）
- 实体列表（可展开）
- 按类型筛选（全部/person/organization/location/event/concept）
- 按分类筛选（全部/military/politics/economy/tech）
- 统计图表：类型分布、提及次数分布

---

## 前端界面

### 5.1 主题设计

单一主题：简洁黑白风，高对比度

```python
THEME = {
    "bg_main": "#111111",
    "bg_card": "#1a1a1a",
    "text_main": "#ffffff",
    "accent": "#00ff88",
    # ...
}
```

### 5.2 页面结构

侧边栏导航:
- 🏠 概览首页
- 🔥 热点详情
- 📡 信号中心
- 📁 实体档案（新增）
- 📈 数据统计

### 5.3 信号显示

信号类型映射:

| signal_type | 显示名称 |
|------------|---------|
| velocity_spike | 🚀 速度激增 |
| convergence | 🔄 多源聚合 |
| triangulation | 📐 三角验证 |
| hotspot_escalation | 🔥 热点升级 |
| economic_indicator_alert | 📊 经济指标异常 |
| natural_disaster_signal | 🌋 自然灾害 |
| geopolitical_intensity | 🌍 地缘政治紧张 |

---

## 配置文件

### 6.1 实体配置

**文件**: `config/entity_config.py`

可自定义内容:
1. **关键词**: 添加新的中英文关键词
2. **人名规则**: 调整长度限制
3. **优先级**: 修改检测优先级
4. **常见英文名**: 扩展姓名库

示例:
```python
# 添加新的事件关键词
ENTITY_TYPES["event"]["keywords"]["zh"].append("罢工")
ENTITY_TYPES["event"]["keywords"]["en"].append("strike")

# 添加新的组织关键词
ENTITY_TYPES["organization"]["keywords"]["en"].append("Startup")

# 添加新的地点
ENTITY_TYPES["location"]["keywords"]["en"].append("Singapore")
```

### 6.2 分析配置

**文件**: `config/analysis_config.py`

可调参数:
- `MAX_ARTICLES_PER_RUN`: 每次最大处理文章数
- `LLM_PROMPTS`: LLM提示词模板
- `SIGNAL_TYPES`: 信号类型定义
- `HOT_THRESHOLD`: 热点阈值（默认3篇）

---

## 性能优化

### 7.1 速度优化

| 优化项 | 效果 |
|--------|------|
| ThreadPoolExecutor(10) | 并发处理聚类 |
| 实体批量更新 | 降低 DB 往返次数 |
| LLM缓存 | 避免重复调用 |
| 无时间窗口 | 加载所有未分析文章 |

### 7.2 成本优化

| 优化项 | 节省 |
|--------|------|
| 聚类摘要复用 | 减少重复调用 |
| 异步信号解释 | 降低主流程阻塞 |
| 缓存命中 | 避免重复付费 |

---

## 部署指南

### 8.1 环境要求

```bash
# Python 3.11+
pip install -r requirements.txt

# 额外依赖（代理环境）
pip install socksio
```

### 8.2 环境变量

```bash
# Supabase
export SUPABASE_URL="your-supabase-url"
export SUPABASE_KEY="your-supabase-key"

# LLM (通义千问)
export DASHSCOPE_API_KEY="your-api-key"

# 增强分析（可选）
export FRED_API_KEY="your-fred-key"
export WORLDMONITOR_BASE_URL="https://worldmonitor.app"
export ENABLE_WORLDMONITOR_ENDPOINTS="true"
export WORLDMONITOR_MAX_PRIORITY="2"
```

### 8.3 数据库迁移

执行 SQL:
```sql
-- 添加新字段
ALTER TABLE analysis_clusters 
ADD COLUMN analysis_depth VARCHAR(20) DEFAULT 'full',
ADD COLUMN is_hot BOOLEAN DEFAULT FALSE,
ADD COLUMN full_analysis_triggered BOOLEAN DEFAULT FALSE,
ADD COLUMN processing_time FLOAT DEFAULT 0.0;

-- 创建实体表
CREATE TABLE entities (...);
CREATE TABLE entity_cluster_relations (...);
```

### 8.4 运行方式

**本地分析**:
```bash
# 基础分析
python scripts/analyzer.py --limit 1000

# 基础分析 + 分析后补充信号解释
python scripts/analyzer.py --limit 1000 --enrich-signals-after-run

# 增强分析（含外部数据）
python scripts/enhanced_analyzer.py --limit 1000

# 增强分析 + 分析后补充信号解释
python scripts/enhanced_analyzer.py --limit 1000 --enrich-signals-after-run

# 重置分析状态
python scripts/reset_analysis.py --all
```

**Web界面**:
```bash
streamlit run web/app.py
```

**GitHub Actions**:
- RSS爬取: `.github/workflows/crawler.yml` ✅ 保留
- 热点分析: ~~`.github/workflows/analyzer.yml`~~ ❌ 已删除

---

## 故障排除

### 9.1 常见问题

**Q: 显示 "没有未分析的文章"，但前端显示有待分析**

A: 检查时间窗口设置。默认现在加载所有未分析文章（hours=None）。如需限制时间:
```python
# 修改 analyzer.py
articles = self.load_unanalyzed_articles(limit=1000, hours=24)
```

**Q: 信号标题显示 N/A**

A: 已修复。现在会根据 signal_type 自动映射为中文名称。

**Q: 实体分类明显错误（如人名进 organization）**

A: 现已改为“LLM 分类 + 规则兜底”，可通过 `scripts/entity_classification.py` 继续微调关键词和纠偏规则。

**Q: 保存分析结果遇到 Supabase 5xx**

A: 建议先缩小批量（降低 `--limit`），或重试运行。当前已在核心写入路径使用重试机制，仍可能受上游瞬时故障影响。

### 9.2 日志位置

```
logs/
├── analyzer.log          # 分析器日志
├── enhanced_analyzer.log # 增强分析器日志
├── llm_client.log        # LLM调用日志
└── crawler.log           # 爬虫日志
```

### 9.3 调试技巧

```bash
# 查看最近日志
tail -f logs/analyzer.log

# 检查LLM调用
grep "SUMMARIZE" logs/llm_client.log

# 检查错误
grep "ERROR" logs/*.log
```

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| Phase 1 | 2026-02-18 | 分层并发分析系统 |
| Phase 2 | 2026-02-18 | 按需深度分析、实体追踪、Web界面 |
| Phase 3 (v0.3.0) | 2026-02-18 | 全量完整分析、LLM实体分类、信号解释增强、前端可读性重构 |

---

## 待办事项 (Next)

- [ ] 实体关系图谱可视化
- [ ] 实体时间线追踪
- [ ] 智能推荐相关实体
- [ ] 实体预警（热度突增）
- [ ] 多语言实体识别优化

---

## 联系与贡献

**项目**: US-Monitor  
**技术栈**: Python, Streamlit, Supabase, LLM (通义千问)  
**最后更新**: 2026-02-18 (v0.3.0)

---

*本文档由 Sisyphus 自动生成*
