# 智能分层分析系统改造计划

## 背景
当前 analyzer.py 串行处理所有聚类，483个聚类 × 1分钟 = 8小时，太慢太烧钱。

## 目标
1. **分层处理**：热点完整分析，冷门快速翻译
2. **并发加速**：默认5并发，用户可配置
3. **按需加载**：冷门新闻点击后再深度分析
4. **实体利用**：让提取的关键实体产生价值

---

## Phase 1: 核心架构改造

### 1.1 分层处理策略

```python
# 聚类分类标准
HOT_CLUSTER_THRESHOLD = 3  # 文章数≥3为热点

热点聚类 (Hot):
- 完整LLM分析：摘要 + 实体 + 影响 + 趋势
- 立即入库
- 参与信号检测

冷门聚类 (Cold):
- 快速翻译：只翻译标题（1/10成本）
- 标记为"浅层分析"
- 不参与信号检测
- 用户点击后触发深度分析
```

### 1.2 并发处理架构

```python
# 并发配置（用户可自定义）
CONCURRENT_WORKERS = 5  # 默认5个并发

实现方式：
- ThreadPoolExecutor 处理 I/O 密集型（API调用）
- 每个 worker 独立调用 LLM
- 共享进度计数器和日志
- 异常隔离：一个失败不影响其他
```

### 1.3 按需分析机制

```python
# 数据库新增字段
analysis_clusters:
  - analysis_depth: "full" | "shallow"  # 分析深度标记
  - analyzed_at: timestamp
  - full_analysis_triggered: bool  # 是否已触发完整分析

# 点击触发流程
用户点击冷门新闻 → 
  检查是否已深度分析 → 
  否 → 实时调用LLM → 
  更新数据库 → 
  展示完整分析
```

---

## Phase 2: 关键实体价值挖掘

### 2.1 实体能做什么？

提取的实体（人名、组织、地点、事件）可用于：

#### A. 实体关联图谱
```
特朗普 --提到--> 美联储
  |                 |
  |                 v
  +----------> 加息政策 <------ 鲍威尔
```
- 可视化：人物关系网络图
- 价值：发现隐藏的关联

#### B. 实体热度追踪
```python
# 追踪实体出现频率
"特朗普": {
  "24h": 15次,
  "7天": 89次,
  "趋势": "上升"
}
```
- 价值：发现谁/什么正在被热议

#### C. 实体档案卡片
```python
# 为每个重要实体建立档案
{
  "entity": "美联储",
  "type": "组织",
  "first_seen": "2024-01-15",
  "mention_count": 234,
  "related_clusters": ["加息", "通胀", "就业数据"],
  "sentiment_trend": "中性偏负"
}
```
- 价值：长期跟踪特定主题

#### D. 跨语言实体对齐
```python
# 中英文实体对应
"Fed" -> "美联储"
"Powell" -> "鲍威尔"
"Inflation" -> "通胀"
```
- 价值：统一搜索和分析

#### E. 实体预警
```python
# 敏感实体出现立即通知
if entity in ["战争", "制裁", "破产", "恐怖袭击"]:
    send_alert(f"⚠️ 检测到敏感实体: {entity}")
```
- 价值：实时风险监控

---

## Phase 3: 技术实现方案

### 3.1 文件修改清单

```
scripts/analyzer.py
  - 添加分层处理逻辑
  - 实现并发处理
  - 修改 run_analysis() 主流程

scripts/llm_client.py
  - 添加 quick_translate() 方法
  - 添加并发安全机制
  
scripts/enhanced_analyzer.py
  - 继承改造后的 analyzer
  - 只分析热点聚类

sql/analysis_schema.sql
  - 添加 analysis_depth 字段
  - 添加 entities 索引

web/app.py
  - 添加点击触发分析功能
  - 显示分析深度标记
  - 实体可视化展示
```

### 3.2 配置参数

```python
# config/analysis_config.py
ANALYSIS_CONFIG = {
    "hot_threshold": 3,           # 热点阈值（文章数）
    "concurrent_workers": 5,       # 并发数
    "max_llm_calls_per_run": 200,  # 每轮最大LLM调用
    "enable_cold_analysis": True,  # 是否分析冷门
    "cold_analysis_mode": "translate_only",  # 冷门处理模式
    "on_demand_analysis": True,    # 启用按需分析
}
```

### 3.3 性能预期

| 指标 | 当前 | 优化后 |
|------|------|--------|
| 处理时间 | 8小时 | 1.5小时 |
| LLM调用 | 483次 | ~80次 |
| 成本 | ¥48 | ¥8 |
| 热点覆盖率 | 100% | 100% |
| 冷门覆盖率 | 100%深度 | 100%浅层+按需 |

---

## Phase 4: 实施步骤

### Step 1: 基础改造（1-2天）
- [ ] 修改 analyzer.py 实现分层处理
- [ ] 添加并发处理（ThreadPoolExecutor）
- [ ] 修改数据库表结构
- [ ] 添加配置参数

### Step 2: 按需分析（1天）
- [ ] 实现 quick_translate()
- [ ] 修改 web 界面支持点击触发
- [ ] 添加分析状态标记

### Step 3: 实体利用（2-3天）
- [ ] 实现实体关联图谱
- [ ] 添加实体热度追踪
- [ ] 创建实体档案页面

### Step 4: 增强分析适配（1天）
- [ ] 改造 enhanced_analyzer.py
- [ ] 只分析热点聚类
- [ ] 集成外部数据源

---

## 决策点

### Q1: 冷门新闻翻译用哪个模型？
**选项A**: 继续使用 qwen-plus（质量好，贵）
**选项B**: 使用 qwen-turbo（快，便宜，质量够用）
**建议**: B，冷门新闻只需要看懂标题，turbo足够

### Q2: 并发数怎么确定？
**公式**: min(5, API速率限制/2, 用户配置)
**默认**: 5
**最大**: 10（避免触发API限流）

### Q3: 实体数据怎么存储？
**选项A**: 存在 analysis_clusters 表（简单，重复存储）
**选项B**: 独立 entities 表（规范，可关联）
**建议**: B，长期看更灵活

---

## 立即行动项

请确认以下问题，我们开始实施：

1. **并发数默认5是否合适？** 你的API速率限制是多少？
2. **冷门新闻用 qwen-turbo 可以吗？** 还是要用 qwen-plus？
3. **Phase 1-4 要全部做吗？** 还是只做 Phase 1（核心改造）？
4. **实体利用功能先做哪个？** 图谱/热度/档案/预警？

确认后立即开始实施！