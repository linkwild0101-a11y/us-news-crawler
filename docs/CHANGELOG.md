# Changelog

## v0.3.0 - 2026-02-18

### Added
- 新增 `scripts/entity_classification.py`，用于 LLM 实体分类标准化与规则兜底纠偏。
- 新增信号解释增强参数：
  - `scripts/analyzer.py --enrich-signals-after-run`
  - `scripts/enhanced_analyzer.py --enrich-signals-after-run`

### Changed
- 分析链路切换为全量完整分析，默认并发提升至 10。
- `signal_explainer.py` 改为兼容入口，核心逻辑整合进 `scripts/analyzer.py`。
- `scripts/reset_analysis.py --all` 增强为同步清理实体档案、实体关联与信号数据。
- 前端 `web/app.py` 优化为高对比可读样式，热点/详情/信号关联支持原文链接。

### Fixed
- Streamlit `st.link_button` 兼容性问题（移除不支持的 `key` 参数）。
- 实体误分类（人名/组织/节日/地点混淆）通过规则校验显著降低。
