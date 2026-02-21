# Source Health SLI/SLO v1（规格草案）

- 日期: 2026-02-21
- 版本: v1
- 目标: 统一度量外部/内部数据源健康状态，支撑降级与告警

## 1. SLI 指标定义

1. `success_rate`
   - 定义: 成功请求数 / 总请求数
   - 窗口: 24h
2. `p95_latency_ms`
   - 定义: 95 分位请求耗时
   - 窗口: 24h
3. `freshness_sec`
   - 定义: 当前时间与最近有效数据时间差（秒）
4. `null_rate`
   - 定义: 关键字段为空的记录占比
5. `error_rate`
   - 定义: 错误请求占比

## 2. SLO 建议阈值

| source_type | success_rate | p95_latency_ms | freshness_sec | null_rate |
|---|---:|---:|---:|---:|
| market_price | >=99.0% | <=3000 | <=86400 | <=5% |
| macro | >=98.5% | <=5000 | <=172800 | <=8% |
| news | >=99.0% | <=4000 | <=7200 | <=3% |
| event_api | >=98.0% | <=6000 | <=21600 | <=10% |

## 3. 健康状态映射

1. `healthy`: 所有核心 SLO 满足
2. `degraded`: 至少一项 SLO 轻度超阈
3. `critical`: success_rate 或 freshness 严重失真

## 4. 降级策略

1. `degraded`
   - 继续主链路
   - 打标并降低相关数据权重
2. `critical`
   - 启用 fallback source 或 stale cache
   - 触发告警并记录 incident

## 5. 报表字段建议

`source_id, date, success_rate, p95_latency_ms, freshness_sec, null_rate, status, notes`
