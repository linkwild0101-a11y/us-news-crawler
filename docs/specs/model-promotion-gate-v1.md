# Model Promotion Gate v1（规格草案）

- 日期: 2026-02-23
- 版本: v1
- 目标: 用统一门禁判断 Challenger 是否可晋级 Champion

## 1. 输入

- 最近 7 天 `eval_*` 代理指标
- source health 稳定性
- 主链路时延与成功率

## 2. Go / No-Go 门槛（v1）

1. `eval_hit_rate_proxy` 不低于基线 -2%
2. LONG 与 SHORT 子集均不显著退化
3. workflow 成功率 >= 99%
4. source health `critical` 源数量不连续 2 天恶化

## 3. 结论类型

- `GO`: 可继续扩大灰度
- `HOLD`: 指标不足，继续影子运行
- `NO_GO`: 关闭相关 flag 并回滚

## 4. 审批建议

- 每周固定 Gate 评审
- 评审材料包含:
  - 指标对比表
  - 异常样本复盘
  - 风险与回滚建议
