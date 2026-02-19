# 实体关系发现设计文档

- 日期: 2026-02-19
- 适用系统: US-Monitor
- 设计范围: 跨类别实体（人物/组织/地点/事件）关系网络构建
- 与其他系统关系: 与哨兵系统并行开发，底层数据共享，展示层独立

## 1. 目标与成功指标

### 1.1 目标
构建跨类别的实体关系网络，自动从新闻中提取实体间的关联关系，为知识图谱和关联分析提供底层数据支撑。

### 1.2 成功指标
- 关系提取准确率 >= 75%（抽样评估）
- 每天处理文章数量: 1000-5000篇
- 关系去重合并率 >= 60%（跨文章相同关系合并）
- 与哨兵系统数据共享无冲突

## 2. 数据基础

### 2.1 现有数据
- 607+ RSS新闻源（军事、政治、经济、科技）
- 已爬取文章（标题、内容、发布时间、simhash去重）
- 新闻聚类结果（Jaccard相似度）
- 热点检测信号
- 实体数据（人物、组织、地点、事件）

### 2.2 外部数据源
- FRED 经济数据
- GDELT 全球事件
- USGS 地震数据
- ACLED 冲突数据
- UCDP 武装冲突

## 3. 技术方案

### 3.1 推荐方案: 混合模式

**核心思路：**
- 热点信号优先：对触发信号检测的聚类优先提取关系
- 后台增量处理：逐步处理普通文章
- 关系合并去重：跨文章聚合相同关系

**优势：**
- 与现有信号检测系统无缝集成
- 成本可控，减少LLM调用次数
- 优先处理热点内容更有价值

### 3.2 替代方案对比

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| 方案1: 逐篇LLM提取 | 灵活，处理复杂关系 | 成本高 | 小规模实验 |
| 方案2: 聚类后提取 | 成本可控 | 可能遗漏关系 | 大规模生产 |
| 方案3: 混合模式（推荐） | 成本效益平衡 | 关系图谱需时间积累 | 中等规模 |

### 3.3 LLM提取策略

**关系类型：开放式发现**
- 不预定义固定关系类型
- 让LLM自由提取任何有意义的关系
- 关系描述使用自然语言

**提取内容：**
- 实体1: 名称、类型（人物/组织/地点/事件）
- 实体2: 名称、类型
- 关系描述: 自然语言描述两者关系
- 置信度: LLM评估的提取可信度
- 来源文章: 关系来源

## 4. 数据模型

### 4.1 实体表 (entities) - 已有字段参考
```sql
-- 现有表结构已包含：
- id
- name
- type (person/organization/location/event)
- article_id
- first_seen
- last_seen
```

### 4.2 关系表 (entity_relations) - 新建
```sql
CREATE TABLE entity_relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity1_id UUID REFERENCES entities(id),
    entity2_id UUID REFERENCES entities(id),
    relation_text TEXT NOT NULL,  -- 自然语言关系描述
    confidence FLOAT DEFAULT 0.5,  -- 置信度 0-1
    source_article_ids UUID[],    -- 来源文章ID数组
    source_count INT DEFAULT 1,  -- 跨文章来源数量
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(entity1_id, entity2_id, relation_text)
);

CREATE INDEX idx_relations_entity1 ON entity_relations(entity1_id);
CREATE INDEX idx_relations_entity2 ON entity_relations(entity2_id);
CREATE INDEX idx_relations_text ON entity_relations USING gin(to_tsvector('english', relation_text));
```

### 4.3 关系证据表 (relation_evidence) - 新建
```sql
CREATE TABLE relation_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    relation_id UUID REFERENCES entity_relations(id),
    article_id UUID REFERENCES articles(id),
    extracted_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(relation_id, article_id)
);
```

## 5. 处理流程

### 5.1 主流程
```
每日文章
    ↓
聚类处理 (现有) → 触发信号检测 (现有)
    ↓                    ↓
              热点聚类优先 → LLM关系提取
                    ↓
              普通文章队列 → 后台增量处理
                    ↓
              关系合并去重 → 存储到 entity_relations
                    ↓
              更新实体 last_seen
```

### 5.2 LLM提取 Prompt 设计
```
从以下新闻文章中提取所有实体（人物、组织、地点、事件）及其之间的关系。

文章标题: {title}
文章内容: {content}

请以JSON格式输出：
{{
  "entities": [
    {{"name": "实体名", "type": "person|organization|location|event"}}
  ],
  "relations": [
    {{"from": "实体1", "to": "实体2", "description": "关系描述", "confidence": 0.0-1.0}}
  ]
}}
```

### 5.3 关系合并策略
- 相同实体对 + 相似关系描述 → 合并
- 合并时: source_count++, 更新 last_seen
- 相似度判断: 使用embedding或简单字符串匹配

## 6. 与哨兵系统的协作

### 6.1 数据共享
- 实体数据: 双方共享
- 关系数据: 哨兵可查询用于增强判断
- 不共享: 展示层独立

### 6.2 协作场景
- 哨兵收敛判断: 可查询相关实体是否有多个来源报道
- 告警上下文: 告警详情可链接到相关实体关系

### 6.3 展示层分离
```
前端展示
├── /monitor (哨兵态势) - 告警卡片
├── /graph (实体关系) - 关系图谱
└── /signals (信号列表) - 传统信号
```

## 7. 实施计划

### 7.1 Phase 1: 基础设施（1周）
- [ ] 设计并创建 entity_relations 表
- [ ] 设计并创建 relation_evidence 表
- [ ] 在 entity_classification.py 基础上扩展关系提取逻辑
- [ ] 编写 LLM 关系提取 prompt

### 7.2 Phase 2: 核心功能（1周）
- [ ] 实现热点聚类优先提取逻辑
- [ ] 实现后台增量处理队列
- [ ] 实现关系合并去重逻辑
- [ ] 对接现有聚类输出

### 7.3 Phase 3: 展示与集成（1周）
- [ ] 创建 /graph 页面展示关系图谱
- [ ] 实现关系图基本交互（点击展开、筛选）
- [ ] 与哨兵系统数据对接

### 7.4 Phase 4: 优化与测试（1周）
- [ ] 准确率评估与调优
- [ ] 性能优化（LLM调用成本控制）
- [ ] 与哨兵系统联合测试

## 8. 风险与边界

### 8.1 已知风险
- LLM 提取成本：每天1000-5000篇文章需要控制调用次数
- 关系噪声：开放式提取可能产生无意义关系
- 实体对齐：同一实体不同表述需要消歧

### 8.2 缓解措施
- 热点优先处理，控制LLM总调用量
- 设置最低置信度阈值过滤噪声
- 逐步积累实体别名库用于消歧

### 8.3 边界说明
- 本系统为底层数据能力，不直接面向最终用户
- 与哨兵系统并行开发，展示层独立
- 关系图谱需要时间积累，早期可能数据稀疏

## 9. 后续扩展

- 社区检测：发现紧密关联的实体群体
- 影响路径分析：找出从A到B的关联路径
- 时序演化：追踪实体关系随时间的变化
- 与外部知识库对接：丰富实体属性
