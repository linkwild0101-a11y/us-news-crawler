# Event Taxonomy v1（规格草案）

- 日期: 2026-02-23
- 版本: v1
- 目标: 统一 Stock V2/V3 事件分类与证据字段，支撑评估、回放与解释层

## 1. 一级事件类型

1. `earnings`：财报/指引
2. `macro`：宏观与利率
3. `policy`：政策与监管
4. `flow`：资金流与仓位
5. `sector`：行业主题
6. `news`：其他新闻

## 2. 标准字段（stock_events_v2.details）

- `title` / `summary`
- `title_zh` / `summary_zh`
- `source_id`
- `category`
- `bias`
- `llm_used`
- `evidence_refs`（可选，数组）

## 3. 证据字段最小要求

1. 至少一个可读摘要（优先中文）
2. source 可追踪（url 或 source_ref）
3. 方向推断来源可追溯（规则/LLM）

## 4. 兼容策略

1. v2 沿用 `event_type`，通过映射表进入 v3 taxonomy
2. 未命中规则统一落 `news`
3. 前端分类展示使用中文映射，不直接展示内部代码
