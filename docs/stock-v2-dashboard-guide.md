# 美股机会看板说明（Stock V2）

更新时间：2026-02-21  
适用对象：使用 `frontend/` 移动端看板进行美股机会筛选的研究/交易用户

---

## 1. 看板目标与使用方式

美股机会看板的目标是：把“新闻事件 → 信号分级 → 多空机会”压缩成一页可执行信息，帮助你更快发现
可跟踪标的（LONG/SHORT 都保留），并给出失效条件和证据链。

看板分为 4 个页签：

1. **机会（🎯）**：直接给出可操作机会列表（优先看这里）
2. **市场（📈）**：宏观环境 + 标的信号热度
3. **信号（🚨）**：L1-L4 哨兵信号明细（仅美股相关）
4. **证据（🧩）**：热点事件簇与实体关系，作为“为什么”的证据层

---

## 2. 顶部总览区字段解释

- **数据更新时间**：`dataUpdatedAt`，取各模块最新时间中的最大值（机会/信号/证据/快照）
- **市场状态**：来自 `stock_market_regime_v2.summary`，展示 `risk_on/risk_off` + VIX/10Y/DXY
- **风险 Lx**：显示 `marketSnapshot.risk_level`（在 V2 模式下由 `risk_badge` 覆盖）

---

## 3. 各页签指标含义

## 3.1 机会页（核心）

### 顶部 4 个统计卡

- **总机会数**：当前有效机会条数（`stock_opportunities_v2` 的 active 行）
- **Horizon A**：短周期机会数量（`horizon=A`）
- **LONG / SHORT**：多空机会数量分布

### 机会卡片字段

- **Ticker**：机会对应标的
- **LONG / SHORT**：方向
- **H A / H B**：
  - `A`：偏短周期（高分信号）
  - `B`：偏中周期（次高分信号）
- **L1-L4**：该机会继承的风险等级（来自信号等级）
- **机会分（0-100）**：综合可交易性分数，越高优先级越高
- **置信度（0-100%）**：当前模型对该机会的把握程度
- **为什么是现在（why_now）**：方向、分数、市场状态的组合解释
- **失效条件（invalid_if）**：该机会何时应降级/取消
- **催化剂（catalysts）**：触发该机会的主因摘要（如 earnings/macro/policy）
- **证据计数**：
  - `信号证据`：关联 signal id 数
  - `聚类证据`：关联 cluster id 数（V2 当前多为 0，后续可增强）
- **到期时间**：机会失效时间（`expires_at`）

---

## 3.2 市场页

### 宏观价格区

- **SPY / QQQ / DIA**：主要指数 ETF 价格
- **VIX**：波动率指数，越高通常风险偏好越弱
- **10Y**：美债 10 年期收益率
- **DXY**：美元指数

> 价格来源：无鉴权源（Stooq + FRED）；抓不到会显示 `--`

### 股票信号热度（Top 10）

- **ticker**
- **风险等级（L1-L4）**
- **24h 信号**：24 小时该标的信号条数
- **关联热点**：24 小时关联热点数量

---

## 3.3 信号页（L1-L4 哨兵）

每张卡片表示一条可读信号：

- **sentinel_id**：信号来源标识（V2 常见 `stock_v2:TICKER`）
- **Lx · 分数**：风险等级 + 标准化风险分
- **description**：信号解释文本
- **trigger_reasons**：触发原因（最多显示前 2 条）
- **时间**：信号生成时间

仅展示**美股相关**信号，并且在有机会标的时优先保留与这些标的相关的信号。

---

## 3.4 证据页

### 热点聚类（股票相关）

- 按 `event_type` 聚合 V2 事件，显示：
  - 标题
  - 摘要（同类事件最近几条拼接）
  - 分类
  - 文章数（该类事件计数）
  - 时间

### 实体关系（股票相关）

- 由同一事件中的 ticker 共现构建
- 展示：
  - `A ↔ B`
  - 关系文本（共同出现次数）
  - 置信度（共现次数 + 映射置信度）
  - 最后出现时间

---

## 4. 分数与等级是怎么来的（关键逻辑）

## 4.1 事件层（stock_events_v2）

每篇文章先转为事件，提取 ticker，并判定方向/强度：

- 方向：`LONG / SHORT / NEUTRAL`
- 强度：`0~1`
- 可选 LLM 修正：在规则结果上做二次校正（cap 限流 + workers 并发）

## 4.2 信号层（stock_signals_v2）

按 ticker 聚合最近事件，计算：

- `signal_score`（0-100）
- `level`（L0-L4）
- `confidence`（0-1）
- `side`（LONG/SHORT）

等级阈值：

- `L4 >= 82`
- `L3 >= 72`
- `L2 >= 60`
- `L1 >= 45`
- `<45 => L0`

## 4.3 机会层（stock_opportunities_v2）

基于 signal + 市场状态（regime）计算：

- `opportunity_score`（0-100）
- `confidence`（0-1）
- `horizon`：`signal_score >= 65 => A`，否则 `B`
- `expires_at`：A 默认更短，B 默认更长

同时输出 `why_now` 与 `invalid_if`，让你可以快速做“入选/剔除”。

---

## 5. 数据来源与刷新链路

主链路（自动）：

1. RSS Crawler 抓取新闻
2. `stock_pipeline_v2.py --mode incremental` 写入事件/信号/机会/快照
3. `refresh_market_digest.py` 刷新市场价格和聚合摘要
4. 前端读取 V2 表（`NEXT_PUBLIC_DASHBOARD_READ_V2=true`）

关键表：

- 事件层：`stock_events_v2`, `stock_event_tickers_v2`
- 服务层：`stock_signals_v2`, `stock_opportunities_v2`, `stock_market_regime_v2`,
  `stock_dashboard_snapshot_v2`
- 市场辅助：`market_snapshot_daily`, `ticker_signal_digest`

---

## 6. 空值/数据少时怎么理解

- `SPY/QQQ/VIX` 显示 `--`：通常是行情源短时不可用，不影响机会引擎主流程
- 机会很少：一般是最近窗口内美股相关事件不足，或过滤后集中到少数 ticker
- 信号为 0：检查 V2 pipeline 是否成功写入 `stock_signals_v2`
- 证据为空：说明当前活跃事件中共现关系不足，或股票相关过滤后无结果

---

## 7. 使用建议（交易视角）

1. 先看**机会页**，优先处理 `A + 高机会分 + 高置信度`
2. 再看**市场状态**确认是否与方向一致（risk_on 更偏 LONG，risk_off 更偏 SHORT）
3. 用**信号页 + 证据页**做二次确认，避免单一文本叙事误导
4. 严格执行卡片里的 **invalid_if（失效条件）**

