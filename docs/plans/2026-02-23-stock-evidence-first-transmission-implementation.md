# 美股看板「证据优先 + 宏观传导链」实施计划（Implementation Plan）

- 日期: 2026-02-23
- 对应设计: `docs/plans/2026-02-23-stock-evidence-first-transmission-design.md`
- 实施目标: 在 2 周内上线轻量版，确保“证据优先、AI参考、传导可解释”

## 1. 实施原则

1. 不阻断现有 V2/V3 主链路：旁路新增，逐步切换
2. 证据优先于建议：先落证据与链路，再生成 AI 文案
3. 可回放与可追溯：全链路写 `run_id/as_of/source_refs`
4. 降级不空白：任何新增模块失败不得导致看板关键区域为空

## 2. 里程碑与阶段

### P0（D1-D2）数据层与契约冻结
- [ ] 新增 `stock_evidence_v2` migration
- [ ] 新增 `stock_transmission_paths_v2` migration
- [ ] 扩展 `stock_opportunities_v2` 字段（`evidence_ids/path_ids/uncertainty_flags/counter_view`）
- [ ] 在 `frontend/lib/types.ts` 增加新数据契约类型
- [ ] 增加 feature flags：
  - `ENABLE_STOCK_EVIDENCE_LAYER`
  - `ENABLE_STOCK_TRANSMISSION_LAYER`
  - `ENABLE_STOCK_AI_DEBATE_VIEW`

交付门槛：
- [ ] migration 可幂等执行
- [ ] 前后端类型定义对齐

### P1（D3-D7）后端能力上线
- [ ] 实现证据抽取层（3-5 条关键段落）
- [ ] 实现宏观传导链层（最多 3 条 M→I→S 主链）
- [ ] 改造 AI 解释为四段式（正方/反方/不确定性/操作前确认）
- [ ] 将 `evidence_bonus`、`uncertainty_penalty` 融入机会分
- [ ] 在 workflow 接入旁路执行与 summary 输出

交付门槛：
- [ ] 每条机会平均证据条数 >= 2
- [ ] 传导链生成覆盖率 >= 70%（有宏观触发条件的机会集）

### P2（D8-D14）前端改版与灰度验收
- [ ] Why-Now 抽屉改为 4 分区
- [ ] 新增传导链卡片（方向/强度/时效/依据）
- [ ] 新增证据卡（来源/时间/关键句段/原文链接）
- [ ] 机会卡增加“证据完整度/关联链强度”
- [ ] 增加人工复核反馈埋点
- [ ] 灰度发布并观察 3 天

交付门槛：
- [ ] 证据区点击率 > AI 区点击率
- [ ] 用户“决策有帮助”评分较基线提升

## 3. 代码级任务拆分

## 3.1 SQL / Migration
- [ ] 新增 `sql/2026-02-23_stock_evidence_transmission_tables.sql`
  - [ ] `stock_evidence_v2`
  - [ ] `stock_transmission_paths_v2`
  - [ ] `stock_opportunities_v2` 扩展字段
  - [ ] 索引 + RLS + comments

验收:
- [ ] 幂等执行通过
- [ ] `anon/authenticated` 仅 SELECT

## 3.2 Pipeline（后端主改造）

目标文件：`scripts/stock_pipeline_v2.py`

- [ ] `extract_key_evidence_snippets()`
  - [ ] 主体/时间/数字事实优先
  - [ ] 证据去重（source_url + snippet hash）
- [ ] `build_macro_transmission_paths()`
  - [ ] 宏观因子词典匹配
  - [ ] 行业映射与方向判断
  - [ ] 路径强度评分
- [ ] `build_ai_debate_view()`
  - [ ] 正方观点
  - [ ] 反方观点
  - [ ] 不确定性
  - [ ] 操作前确认项
- [ ] `merge_opportunity_score_with_evidence()`
- [ ] 写入 `stock_evidence_v2` / `stock_transmission_paths_v2`

验收:
- [ ] 新模块失败时机会照常产出（带 `evidence_incomplete`）
- [ ] snapshot 不空白

## 3.3 配置与词典

目标文件：
- `config/analysis_config.py`
- `config/entity_config.py`
- `config/macro_factor_dictionary.json`（新增）

- [ ] 新增宏观因子白名单（利率/通胀/油价/汇率/政策）
- [ ] 新增行业映射规则（宏观因子 -> 行业）
- [ ] 新增评分权重配置（bonus/penalty）

验收:
- [ ] 配置可热切换（无需改代码）

## 3.4 Workflow / CI

目标文件：`.github/workflows/analysis-after-crawl.yml`

- [ ] 增加证据层/传导层步骤（受 flag 控制）
- [ ] 增加 run summary 指标输出：
  - `evidence_rows_written`
  - `transmission_paths_written`
  - `evidence_coverage_rate`
  - `ai_debate_coverage_rate`
  - `pipeline_duration_sec`

验收:
- [ ] 不开启 flags 时与当前行为一致
- [ ] 开启 flags 后主 workflow 成功率 >= 99%

## 3.5 Frontend

目标文件：
- `frontend/lib/types.ts`
- `frontend/lib/data.ts`
- `frontend/components/mobile-dashboard.tsx`

- [ ] 类型层新增：EvidenceItem / TransmissionPath / AiDebateView
- [ ] 数据层整合：机会详情附带 evidence/path/debate
- [ ] UI 改造：Why-Now 四分区
- [ ] UI 改造：机会卡增加证据完整度、关联链强度
- [ ] 证据卡操作：查看原文、加入复核清单

验收:
- [ ] 无新增数据时有友好占位文案
- [ ] tooltip / drawer 不发生裁剪与遮挡

## 4. 观测与埋点

## 4.1 运行指标（后端）
- [ ] `evidence_extract_success_rate`
- [ ] `transmission_build_success_rate`
- [ ] `avg_evidence_per_opportunity`
- [ ] `uncertainty_flag_rate`

## 4.2 产品指标（前端）
- [ ] `evidence_card_click_rate`
- [ ] `original_article_open_rate`
- [ ] `ai_panel_expand_rate`
- [ ] `manual_review_submit_rate`
- [ ] `decision_helpfulness_score`

## 5. 测试计划

### 5.1 本地静态检查
- [ ] `python3 -m py_compile scripts/*.py web/*.py`
- [ ] `npm --prefix frontend run typecheck`

### 5.2 数据回放测试
- [ ] 使用最近 7 天数据回放 3 次
- [ ] 对账：证据覆盖率、链路覆盖率、空白率

### 5.3 人工抽样测试
- [ ] 抽样 50 条机会验证：
  - [ ] 证据是否可追溯到原文
  - [ ] 传导方向是否合理
  - [ ] AI 正反观点是否存在明显自相矛盾

## 6. 风险与回滚

触发回滚条件（任一满足）：
- [ ] workflow 连续失败 > 3 次
- [ ] 证据区或机会区空白率 > 10%
- [ ] 用户反馈“误导性建议”显著上升

回滚动作：
1. `ENABLE_STOCK_EVIDENCE_LAYER=false`
2. `ENABLE_STOCK_TRANSMISSION_LAYER=false`
3. `ENABLE_STOCK_AI_DEBATE_VIEW=false`
4. 保留新增表数据供排障，不做删除

## 7. 执行顺序（建议）

1. P0: schema + type contract + flags
2. P1: pipeline + config + workflow summary
3. P2: frontend 四分区 + 传导卡 + 埋点灰度
4. 灰度 3 天后复盘并决定是否全量

## 8. 交付物清单

- [x] 设计文档（已完成）
- [x] 实施计划（本文）
- [ ] migration SQL
- [ ] pipeline 改造
- [ ] workflow 改造
- [ ] 前端改造
- [ ] 灰度复盘报告
