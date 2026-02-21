# Provider Registry v1（规格草案）

- 日期: 2026-02-21
- 版本: v1
- 目标: 为新闻/行情/宏观等数据源提供统一注册与调用契约

## 1. 统一字段

每个 provider 必须定义：

1. `provider_id`（唯一标识）
2. `source_type`（`news|market_price|macro|event_api`）
3. `endpoint`（主地址）
4. `auth_type`（`none|token|key`）
5. `sla_target`（可用性目标，如 `99.5%`）
6. `retry_policy`（重试次数、退避策略）
7. `fallback_policy`（失败后的降级行为）
8. `freshness_slo_sec`（新鲜度目标）
9. `owner`（负责人）

## 2. 配置示例（YAML）

```yaml
provider_id: stooq_daily
source_type: market_price
endpoint: https://stooq.com/q/l/
auth_type: none
sla_target: "99.0%"
freshness_slo_sec: 86400
retry_policy:
  max_retries: 2
  backoff: exponential
fallback_policy:
  mode: stale_allowed
  max_stale_sec: 172800
owner: market-data
```

## 3. 运行时行为

1. 正常：返回 `data + meta(provider_id, latency_ms, fetched_at)`
2. 部分失败：打 `degraded=true` 标记，允许下游继续
3. 全失败：触发 fallback 并记录 source health 事件

## 4. 验证规则

1. `provider_id` 唯一
2. `source_type` 必须在白名单
3. `freshness_slo_sec > 0`
4. 未配置 fallback 的源不允许进入生产自动链路

## 5. 迁移建议

1. 第一批纳入：`stooq`、`fred`、`articles` 输入
2. 第二批纳入：扩展信号源
