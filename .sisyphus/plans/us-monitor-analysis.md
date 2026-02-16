# US-Monitor Hotspot Analysis System

## TL;DR

> **Quick Summary**: Build an intelligent analysis pipeline that clusters crawled RSS news articles (199 sources) using Jaccard similarity, categorizes by domain (political/geopolitical, economic, military), and uses Alibaba Qwen3-Plus LLM to generate hotspot analyses with trend detection and escalation scoring. Runs as a separate GitHub Actions workflow after the crawler completes.
>
> **Deliverables**:
> 
> **核心分析 (Core Analysis)**:
> - Database schema: `analysis_clusters`, `analysis_signals` tables
> - Python analysis pipeline: `scripts/analyzer.py` (中文输出)
> - LLM integration: Alibaba Qwen3-Plus API client (中文提示词)
> - Clustering engine: Jaccard similarity with inverted index
> - Signal detection: velocity_spike, convergence, triangulation, hotspot_escalation
> - GitHub Actions workflow: `.github/workflows/analyzer.yml`
> 
> **免费数据源 (Free Data Sources)**:
> - FRED client: 美国经济数据 (免费, 需API key)
> - GDELT client: 全球事件数据库 (完全免费)
> - USGS client: 地震数据 (完全免费)
> - World Bank client: 经济指标 (完全免费)
> - Enhanced signals: 数据源融合增强信号
> 
> **UI 仪表板 (Web Dashboard)**:
> - Streamlit Web应用: 中文界面
> - 页面: 概览首页、热点详情、信号中心、数据统计
> - 移动端响应式支持
> - 一键部署文档
>
> **Estimated Effort**: Large (10-12 hours)  
> **Parallel Execution**: YES - 6 waves (Foundation → Core → Integration → Validation → Enhancement → Final)  
> **Critical Path**: Database Schema → Clustering → Analyzer → Enhanced Analyzer → Final Testing  
> **新增功能**: 中文输出、Web UI仪表板、4个免费数据源集成

---

## Context

### Original Request
"帮我学习worldmonitor，设计一个基于现在爬取数据的热点分析功能，可以分为政治/地缘 经济 军事三个分类。总结分析使用阿里qwen3-plus的在线大模型。"

(Learn from worldmonitor, design a hotspot analysis feature based on current crawled data, categorized into Political/Geopolitical, Economic, and Military. Use Alibaba Qwen3-Plus LLM for summarization and analysis.)

### Interview Summary

**Key Discussions**:
- Fixed crawler bugs (timestamp format, Twitter/X header overflow)
- Expanded RSS sources from 172 to 199 (added worldmonitor premium sources)
- Current database: 1000+ unique articles, SimHash deduplication working
- Schedule: GitHub Actions runs twice daily at 9AM/9PM ET
- Cloudflare Worker deployed for content extraction

**User Intent**: Build intelligent analysis layer on top of existing crawler infrastructure, inspired by worldmonitor's architecture but adapted for US-focused news monitoring.

### Research Findings

**WorldMonitor Architecture Analyzed**:
- **analysis-core.ts**: Jaccard similarity clustering (SIMILARITY_THRESHOLD=0.5), tokenization with stop words removal, inverted index for efficient matching
- **hotspot-escalation.ts**: Dynamic escalation scoring with weighted components (news 35%, CII 25%, geo 25%, military 15%), signal cooldown (2 hours), historical trend tracking
- **analysis.worker.ts**: Web Worker for O(n²) clustering off main thread, state persistence between analyses, signal deduplication
- **analysis-constants.ts**: Signal types with context explanations (whyItMatters, actionableInsight, confidenceNote), keyword mappings for topics

**Key Patterns to Adopt**:
1. Pure functions for core analysis (no side effects)
2. Clustering: Tokenization → Jaccard similarity → Inverted index optimization
3. Signals: velocity_spike, convergence, triangulation, hotspot_escalation
4. Signal deduplication via generateDedupeKey
5. Weighted scoring for escalation (news velocity, source diversity, geographic convergence)

### Metis Review

**Identified Gaps** (addressed in this plan):
1. Output format defined: Structured JSON with summaries, signals, escalation scores
2. Time window: Last 24 hours of unanalyzed articles
3. Incremental processing: Only analyze articles with `analyzed_at IS NULL`
4. LLM strategy: Per-cluster summarization (not per-article to control costs)
5. Scope locked: No UI/dashboard, no real-time processing, no custom ML
6. Hotspot definition: Topic/theme-based clusters (not geographic like worldmonitor)
7. Language: English output (sources are US-based)
8. Analysis workflow: Separate from crawler, triggered after crawler completes

**Guardrails Applied**:
- Max 500 articles per run (GitHub Actions time limit)
- Max 200 LLM API calls per run (cost control)
- Token estimation before API calls
- Retry logic with exponential backoff (3 attempts)
- Truncate long content to 4000 chars
- Skip articles <100 chars content, <10 chars title
- 90-day retention for analysis results

---

## Work Objectives

### Core Objective
Implement an intelligent news analysis pipeline that transforms raw crawled RSS articles into actionable hotspot intelligence using LLM-powered summarization and worldmonitor-inspired clustering and signal detection algorithms.

### Concrete Deliverables
#### Core Analysis
- `sql/analysis_schema.sql` - Database tables for analysis results
- `scripts/analyzer.py` - Main analysis pipeline
- `scripts/clustering.py` - Jaccard similarity clustering engine
- `scripts/llm_client.py` - Alibaba Qwen3-Plus API client (中文输出)
- `scripts/signal_detector.py` - Signal detection algorithms
- `.github/workflows/analyzer.yml` - GitHub Actions workflow
- `.env.example` - Updated with analysis configuration
- `config/analysis_config.py` - Thresholds, prompts (中文), constants

#### Data Sources (Free/Low-Cost)
- `scripts/datasources/fred_client.py` - FRED 美国经济数据 (免费，需API key)
- `scripts/datasources/gdelt_client.py` - GDELT 全球事件数据库 (免费)
- `scripts/datasources/earthquake_client.py` - USGS 地震数据 (免费)
- `scripts/datasources/worldbank_client.py` - 世界银行指标 (免费)
- `scripts/datasources/enhanced_signals.py` - 增强信号检测（结合多数据源）

#### UI Dashboard
- `web/app.py` - Flask/Streamlit Web 应用主入口
- `web/templates/index.html` - 主仪表板页面（中文界面）
- `web/templates/hotspots.html` - 热点详情页
- `web/templates/signals.html` - 信号列表页
- `web/static/css/style.css` - 样式表
- `web/static/js/dashboard.js` - 前端交互
- `web/data_api.py` - 数据查询API
- `web/README.md` - UI部署说明

### Definition of Done
- [ ] Analysis pipeline completes within 30 minutes for 500 articles
- [ ] Successfully calls Alibaba Qwen3-Plus API and stores structured JSON results
- [ ] Clusters 1000 articles into 50-200 meaningful clusters (verified via DB query)
- [ ] Detects at least 1 signal per run when significant news exists
- [ ] Only processes unanalyzed articles (incremental processing verified)
- [ ] All acceptance criteria pass via agent-executed QA scenarios

### Must Have
- Database schema for clusters and signals
- Jaccard similarity clustering with inverted index
- Alibaba Qwen3-Plus LLM integration
- Per-cluster summarization
- Signal detection: velocity_spike, convergence
- Incremental processing (only new articles)
- Error handling with graceful degradation
- GitHub Actions workflow

### Must NOT Have (Guardrails)
- **No Real-time Processing** - Batch analysis only, scheduled via GitHub Actions
- **No Custom ML Models** - Use Qwen3-Plus only, no model training
- **No Market Data Integration** - Skip prediction_leads_news, news_leads_markets signals (no market data source)
- **No Advanced Signals Initially** - Start with 4 core signals only

### Key Changes from Original Plan
1. **中文输出** - 所有分析摘要用中文输出，但保留英文原文链接供溯源
2. **UI展示** - 添加 Web 仪表板，展示热点分析结果（Python Flask/Streamlit）
3. **免费数据源增强** - 集成 worldmonitor 中可用的免费/低成本数据源

---

## Verification Strategy

> **UNIVERSAL RULE: ZERO HUMAN INTERVENTION**
>
> ALL tasks must be verifiable by the agent using tools. No human testing required.

### Test Decision
- **Infrastructure exists**: YES - Supabase PostgreSQL already configured
- **Automated tests**: Tests-after (add unit tests after core implementation)
- **Framework**: Python unittest (consistent with existing scripts)

### Agent-Executed QA Scenarios (MANDATORY)

Every task includes concrete scenarios with exact commands, assertions, and evidence paths.

**Verification Tools by Type:**
| Type | Tool | How Agent Verifies |
|------|------|-------------------|
| **Database** | Bash (psql) | Query tables, assert row counts, validate schema |
| **Python** | Bash (python) | Run scripts, check exit codes, validate output |
| **API** | Bash (curl) | Send requests, parse JSON, assert status codes |
| **GitHub Actions** | Web | Check workflow runs, view logs |

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation - Can Start Immediately):
├── Task 1: Database Schema (no dependencies)
├── Task 2: LLM Client Module (no dependencies)
└── Task 3: Configuration & Constants (no dependencies)

Wave 2 (Core Logic - After Wave 1):
├── Task 4: Clustering Engine (depends: Task 3)
└── Task 5: Signal Detection (depends: Task 3)

Wave 3 (Integration - After Wave 2):
├── Task 6: Main Analyzer Pipeline (depends: 1, 2, 4, 5)
└── Task 7: GitHub Actions Workflow (depends: 6)

Wave 4 (Validation - After Wave 3):
└── Task 8: End-to-End Testing (depends: 7)

Critical Path: Task 1 → Task 4 → Task 6 → Task 7 → Task 8
Parallel Speedup: ~30% faster than sequential
```

### Dependency Matrix

| Task | Depends On | Blocks | Can Parallelize With |
|------|------------|--------|---------------------|
| 1 | None | 6 | 2, 3 |
| 2 | None | 6 | 1, 3 |
| 3 | None | 4, 5 | 1, 2 |
| 4 | 3 | 6 | 5 |
| 5 | 3 | 6 | 4 |
| 6 | 1, 2, 4, 5 | 7 | None |
| 7 | 6 | 8 | None |
| 8 | 7 | None | None |

---

## TODOs

### Task 1: Database Schema

**What to do**:
Create SQL schema for analysis results storage:
1. `analysis_clusters` table - stores cluster information
2. `analysis_signals` table - stores detected signals
3. `article_analyses` junction table - links articles to clusters
4. Add `analyzed_at` column to existing `articles` table
5. Create indexes for performance

**Must NOT do**:
- Do not modify existing `articles` table structure beyond adding `analyzed_at`
- Do not drop existing tables
- Do not create foreign key constraints that would block deletions

**Recommended Agent Profile**:
- **Category**: unspecified-low
- **Reason**: SQL schema creation is straightforward, low complexity
- **Skills**: None needed

**Parallelization**:
- **Can Run In Parallel**: YES - Wave 1
- **Blocks**: Task 6 (Main Analyzer)
- **Blocked By**: None

**References**:
- Pattern: Follow existing schema in `sql/schema.sql`
- Similar table: `articles` table structure for column types
- WorldMonitor: `analysis-core.ts:ClusteredEventCore` interface for data structure

**Acceptance Criteria**:

**Agent-Executed QA Scenarios:**

```
Scenario: Schema creates successfully
  Tool: Bash (psql)
  Preconditions: Supabase credentials in environment
  Steps:
    1. Run: psql $SUPABASE_URL -f sql/analysis_schema.sql
    2. Assert: Exit code 0
    3. Query: \dt analysis_*
    4. Assert: Shows analysis_clusters, analysis_signals, article_analyses

Scenario: Tables have correct structure
  Tool: Bash (psql)
  Steps:
    1. Query: SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'analysis_clusters'
    2. Assert: Columns include id, cluster_key, category, primary_title, summary, article_count, created_at, updated_at
    3. Query: SELECT column_name FROM information_schema.columns WHERE table_name = 'articles' AND column_name = 'analyzed_at'
    4. Assert: analyzed_at column exists
    5. Evidence: Screenshot of query results

Scenario: Indexes created for performance
  Tool: Bash (psql)
  Steps:
    1. Query: SELECT indexname FROM pg_indexes WHERE tablename = 'analysis_clusters'
    2. Assert: Index on cluster_key exists
    3. Assert: Index on created_at exists
    4. Evidence: Query output saved
```

**Commit**: YES
- Message: `feat(db): add analysis schema for hotspot detection`
- Files: `sql/analysis_schema.sql`
- Pre-commit: Verify schema applies without errors

---

### Task 2: LLM Client Module

**What to do**:
Create Python module for Alibaba Qwen3-Plus API integration:
1. `scripts/llm_client.py` - API client class
2. Implement authentication with API key
3. Request/response handling with JSON mode
4. Token estimation and cost tracking
5. Retry logic with exponential backoff (3 attempts)
6. Response caching to avoid duplicate calls
7. Error handling for rate limits, timeouts, malformed responses

**Must NOT do**:
- Do not implement streaming responses (not needed)
- Do not support multiple LLM providers initially
- Do not implement fine-tuning or custom models

**Recommended Agent Profile**:
- **Category**: unspecified-high
- **Reason**: API integration requires robust error handling, retry logic, async patterns
- **Skills**: None needed (pure Python)

**Parallelization**:
- **Can Run In Parallel**: YES - Wave 1
- **Blocks**: Task 6 (Main Analyzer)
- **Blocked By**: None

**References**:
- WorldMonitor: `api/groq-summarize.js` for API call pattern and caching strategy
- Existing code: `scripts/crawler.py` for Supabase client pattern
- External: Alibaba DashScope API documentation (https://help.aliyun.com/zh/dashscope/)

**Acceptance Criteria**:

**Agent-Executed QA Scenarios:**

```
Scenario: LLM client initializes with API key
  Tool: Bash (python)
  Preconditions: ALIBABA_API_KEY set in environment
  Steps:
    1. Run: python -c "from scripts.llm_client import LLMClient; c = LLMClient(); print('Initialized')"
    2. Assert: Output contains "Initialized"
    3. Assert: Exit code 0

Scenario: API call returns structured JSON
  Tool: Bash (python)
  Steps:
    1. Create test script: test_llm.py (provided in task)
    2. Run: python test_llm.py
    3. Assert: Response is valid JSON
    4. Assert: Response contains expected fields (summary, keywords, sentiment)
    5. Evidence: Save response to .sisyphus/evidence/task-2-llm-response.json

Scenario: Retry on failure works
  Tool: Bash (python)
  Steps:
    1. Configure invalid API key temporarily
    2. Run: python -c "from scripts.llm_client import LLMClient; c = LLMClient(); c.summarize('test')" 2>&1
    3. Assert: Log shows 3 retry attempts
    4. Assert: Final error is graceful (not crash)
    5. Evidence: Screenshot of retry logs

Scenario: Caching prevents duplicate calls
  Tool: Bash (python)
  Steps:
    1. Call LLM with same input twice
    2. Assert: Second call returns cached result (faster, no API log)
    3. Evidence: Compare timestamps in logs
```

**Commit**: YES
- Message: `feat(llm): add Alibaba Qwen3-Plus client with retry and caching`
- Files: `scripts/llm_client.py`, `.env.example` (updated)
- Pre-commit: Verify client imports without errors

---

### Task 3: Configuration & Constants

**What to do**:
Create centralized configuration module:
1. `config/analysis_config.py` - All thresholds and constants
2. Define Jaccard similarity threshold (default: 0.5)
3. Define stop words for tokenization
4. Define topic keywords for each category (military, politics, economy)
5. Define signal detection thresholds
6. Define LLM prompts (cluster summarization, signal rationale)
7. Define batch sizes and limits

**Must NOT do**:
- Do not hardcode values in other modules
- Do not create circular dependencies

**Recommended Agent Profile**:
- **Category**: quick
- **Reason**: Simple constants definition, low complexity
- **Skills**: None needed

**Parallelization**:
- **Can Run In Parallel**: YES - Wave 1
- **Blocks**: Tasks 4, 5 (Clustering, Signal Detection)
- **Blocked By**: None

**References**:
- WorldMonitor: `analysis-constants.ts` for stop words, topic keywords, thresholds
- WorldMonitor: `analysis-core.ts` for signal type definitions
- Existing: `scripts/crawler.py` for batch size patterns

**Acceptance Criteria**:

**Agent-Executed QA Scenarios:**

```
Scenario: Configuration loads correctly
  Tool: Bash (python)
  Steps:
    1. Run: python -c "from config.analysis_config import SIMILARITY_THRESHOLD, STOP_WORDS; print(f'Threshold: {SIMILARITY_THRESHOLD}')"
    2. Assert: Exit code 0
    3. Assert: Output shows threshold value (0.5)

Scenario: Stop words defined
  Tool: Bash (python)
  Steps:
    1. Run: python -c "from config.analysis_config import STOP_WORDS; print(f'Count: {len(STOP_WORDS)}')"
    2. Assert: STOP_WORDS contains common words (the, a, an, and)
    3. Assert: Count > 20
    4. Evidence: Print sample of stop words

Scenario: Topic keywords categorized
  Tool: Bash (python)
  Steps:
    1. Run: python -c "from config.analysis_config import TOPIC_KEYWORDS; print(TOPIC_KEYWORDS)"
    2. Assert: Has keys: 'military', 'politics', 'economy'
    3. Assert: Each category has 10+ keywords
    4. Evidence: Save output

Scenario: LLM prompts defined
  Tool: Bash (python)
  Steps:
    1. Run: python -c "from config.analysis_config import LLM_PROMPTS; print(LLM_PROMPTS.keys())"
    2. Assert: Contains 'cluster_summary' key
    3. Assert: Prompt is non-empty string with instructions
    4. Evidence: Save prompt content
```

**Commit**: YES
- Message: `feat(config): add analysis configuration with thresholds and prompts`
- Files: `config/analysis_config.py`, `config/__init__.py`
- Pre-commit: Verify imports work

---

### Task 4: Clustering Engine

**What to do**:
Implement Jaccard similarity clustering (pure functions):
1. `scripts/clustering.py` - Core clustering logic
2. `tokenize(title)` - Tokenization with stop words removal
3. `jaccard_similarity(set1, set2)` - Similarity calculation
4. `cluster_news(articles)` - Main clustering with inverted index optimization
5. Generate cluster IDs based on content hash
6. Sort clusters by source tier and recency
7. Return cluster objects with metadata

**Must NOT do**:
- Do not use scikit-learn or external ML libraries (keep it pure Python)
- Do not mutate input articles
- Do not access database (pure function)

**Recommended Agent Profile**:
- **Category**: unspecified-high
- **Reason**: Algorithm implementation requires careful optimization, O(n²) complexity management
- **Skills**: None needed (pure Python algorithms)

**Parallelization**:
- **Can Run In Parallel**: YES - Wave 2
- **Blocks**: Task 6 (Main Analyzer)
- **Blocked By**: Task 3 (Configuration)

**References**:
- WorldMonitor: `analysis-core.ts:154-280` - clusterNewsCore implementation
- WorldMonitor: `analysis-constants.ts:59-73` - tokenize and jaccardSimilarity
- Pattern: Inverted index for O(n) candidate selection instead of O(n²) comparisons

**Acceptance Criteria**:

**Agent-Executed QA Scenarios:**

```
Scenario: Tokenization works correctly
  Tool: Bash (python)
  Steps:
    1. Run: python -c "from scripts.clustering import tokenize; print(tokenize('The quick brown fox'))"
    2. Assert: Returns set without stop words (the)
    3. Assert: Contains 'quick', 'brown', 'fox'
    4. Evidence: Output shows correct tokens

Scenario: Jaccard similarity calculates correctly
  Tool: Bash (python)
  Steps:
    1. Run: python -c "from scripts.clustering import jaccard_similarity; print(jaccard_similarity({'a','b'}, {'a','b'}))"
    2. Assert: Returns 1.0 for identical sets
    3. Run with {'a','b'}, {'c','d'}
    4. Assert: Returns 0.0 for disjoint sets
    5. Evidence: Screenshot of test results

Scenario: Clustering groups similar articles
  Tool: Bash (python)
  Steps:
    1. Create test data with 5 articles (3 similar, 2 different)
    2. Run: python -c "from scripts.clustering import cluster_news; import json; clusters = cluster_news(test_data); print(f'Clusters: {len(clusters)}')"
    3. Assert: Creates 2-3 clusters (not 5 individual)
    4. Assert: Similar articles grouped together
    5. Evidence: Print cluster assignments

Scenario: Inverted index optimization works
  Tool: Bash (python)
  Steps:
    1. Test with 100 articles
    2. Measure time with and without inverted index
    3. Assert: With inverted index is significantly faster
    4. Evidence: Timing logs saved
```

**Commit**: YES
- Message: `feat(clustering): implement Jaccard similarity clustering with inverted index`
- Files: `scripts/clustering.py`
- Pre-commit: Unit tests pass

---

### Task 5: Signal Detection

**What to do**:
Implement signal detection algorithms:
1. `scripts/signal_detector.py` - Signal detection module
2. `detect_velocity_spike(clusters)` - News velocity surge detection
3. `detect_convergence(clusters)` - Multi-source type confirmation
4. `detect_triangulation(clusters)` - Wire+Gov+Intel alignment
5. `detect_hotspot_escalation(clusters)` - Composite escalation scoring
6. `generate_signal_id()`, `generate_dedupe_key()` - Utilities
7. Return signal objects with confidence scores

**Must NOT do**:
- Do not implement prediction_leads_news or news_leads_markets (no market data)
- Do not implement flow_drop or flow_price_divergence (no pipeline data)
- Do not access external APIs

**Recommended Agent Profile**:
- **Category**: unspecified-high
- **Reason**: Algorithm logic requires careful threshold tuning and weight calculations
- **Skills**: None needed

**Parallelization**:
- **Can Run In Parallel**: YES - Wave 2
- **Blocks**: Task 6 (Main Analyzer)
- **Blocked By**: Task 3 (Configuration)

**References**:
- WorldMonitor: `analysis-core.ts:302-434` - detectPipelineFlowDrops, detectConvergence, detectTriangulation
- WorldMonitor: `hotspot-escalation.ts` - escalation scoring with weighted components
- WorldMonitor: `analysis-constants.ts` - SIGNAL_CONTEXT for explanations

**Acceptance Criteria**:

**Agent-Executed QA Scenarios:**

```
Scenario: Velocity spike detected
  Tool: Bash (python)
  Steps:
    1. Create test clusters with one cluster having 10+ sources in 1 hour
    2. Run: python -c "from scripts.signal_detector import detect_velocity_spike; signals = detect_velocity_spike(clusters)"
    3. Assert: Returns velocity_spike signal
    4. Assert: Confidence > 0.6
    5. Evidence: Print signal details

Scenario: Convergence detected
  Tool: Bash (python)
  Steps:
    1. Create test cluster with 3+ different source types
    2. Run: python -c "from scripts.signal_detector import detect_convergence; signals = detect_convergence(clusters)"
    3. Assert: Returns convergence signal
    4. Assert: Lists source types in description
    5. Evidence: Save signal output

Scenario: Triangulation detected
  Tool: Bash (python)
  Steps:
    1. Create test cluster with wire + gov + intel sources
    2. Run: python -c "from scripts.signal_detector import detect_triangulation; signals = detect_triangulation(clusters)"
    3. Assert: Returns triangulation signal
    4. Assert: Confidence >= 0.9
    5. Evidence: Screenshot

Scenario: Signal deduplication works
  Tool: Bash (python)
  Steps:
    1. Call detect_velocity_spike twice with same cluster
    2. Assert: generate_dedupe_key returns same key for same input
    3. Assert: Second call would be filtered by dedupe logic
    4. Evidence: Show dedupe keys match
```

**Commit**: YES
- Message: `feat(signals): implement velocity, convergence, triangulation detection`
- Files: `scripts/signal_detector.py`
- Pre-commit: Unit tests pass

---

### Task 6: Main Analyzer Pipeline

**What to do**:
Create main analysis orchestrator:
1. `scripts/analyzer.py` - Main entry point
2. Load unanalyzed articles from Supabase (WHERE analyzed_at IS NULL)
3. Filter by time window (last 24 hours)
4. Run clustering on articles
5. Call LLM for cluster summarization (batch calls)
6. Run signal detection on clusters
7. Store results in database (clusters, signals, mark articles as analyzed)
8. Logging and progress tracking
9. Error handling with partial success

**Must NOT do**:
- Do not process more than 500 articles per run
- Do not make more than 200 LLM API calls per run
- Do not fail entirely if single article/cluster fails

**Recommended Agent Profile**:
- **Category**: ultrabrain
- **Reason**: Complex orchestration, database transactions, API rate limiting, batch processing, error recovery
- **Skills**: None needed

**Parallelization**:
- **Can Run In Parallel**: NO - Wave 3
- **Blocks**: Task 7 (GitHub Actions)
- **Blocked By**: Tasks 1, 2, 4, 5

**References**:
- WorldMonitor: `analysis.worker.ts` - worker message handling and state management
- Existing: `scripts/crawler.py` - batch processing pattern, Supabase interactions
- Existing: `scripts/dedup.py` - SimHash implementation (reference for pure functions)

**Acceptance Criteria**:

**Agent-Executed QA Scenarios:**

```
Scenario: Analyzer runs end-to-end
  Tool: Bash (python)
  Preconditions: Test articles in database, API key configured
  Steps:
    1. Run: python scripts/analyzer.py --limit 10
    2. Assert: Exit code 0
    3. Assert: Log shows: "Loaded 10 unanalyzed articles"
    4. Assert: Log shows: "Created X clusters"
    5. Assert: Log shows: "Detected Y signals"
    6. Evidence: Save full log output

Scenario: Articles marked as analyzed
  Tool: Bash (psql)
  Steps:
    1. Query: SELECT COUNT(*) FROM articles WHERE analyzed_at IS NOT NULL
    2. Assert: Count equals number of processed articles (10)
    3. Query: SELECT analyzed_at FROM articles LIMIT 1
    4. Assert: Timestamp is recent
    5. Evidence: Screenshot of query results

Scenario: Clusters stored in database
  Tool: Bash (psql)
  Steps:
    1. Query: SELECT COUNT(*) FROM analysis_clusters
    2. Assert: Count > 0
    3. Query: SELECT * FROM analysis_clusters LIMIT 1
    4. Assert: Has summary, category, article_count
    5. Evidence: Save query output

Scenario: Signals stored in database
  Tool: Bash (psql)
  Steps:
    1. Query: SELECT COUNT(*) FROM analysis_signals
    2. Assert: Count >= 0 (may be 0 if no signals detected)
    3. Query: SELECT * FROM analysis_signals LIMIT 1
    4. Assert: If exists, has signal_type, confidence, description
    5. Evidence: Save output

Scenario: Respects limit parameter
  Tool: Bash (python)
  Steps:
    1. Run with --limit 5
    2. Assert: Log shows "Processing max 5 articles"
    3. Assert: Only 5 articles marked as analyzed
    4. Evidence: Compare counts before/after

Scenario: Handles errors gracefully
  Tool: Bash (python)
  Steps:
    1. Temporarily break one article (empty content)
    2. Run: python scripts/analyzer.py
    3. Assert: Pipeline completes (exit 0)
    4. Assert: Log shows "Skipped 1 invalid articles"
    5. Assert: Other articles still processed
    6. Evidence: Log showing error handling
```

**Commit**: YES
- Message: `feat(analyzer): add main analysis pipeline with clustering and LLM`
- Files: `scripts/analyzer.py`
- Pre-commit: Full test run with --limit 10

---

### Task 7: GitHub Actions Workflow

**What to do**:
Create GitHub Actions workflow for automated analysis:
1. `.github/workflows/analyzer.yml` - Workflow definition
2. Trigger: schedule (runs 1 hour after crawler) + workflow_dispatch
3. Setup Python environment
4. Install dependencies
5. Run analyzer with proper env vars
6. Error notifications on failure
7. Artifact upload for logs

**Must NOT do**:
- Do not merge with crawler workflow (keep separate)
- Do not trigger on every push (only schedule)

**Recommended Agent Profile**:
- **Category**: quick
- **Reason**: YAML configuration, straightforward workflow setup
- **Skills**: None needed

**Parallelization**:
- **Can Run In Parallel**: NO - Wave 3
- **Blocks**: Task 8 (End-to-End Testing)
- **Blocked By**: Task 6 (Main Analyzer)

**References**:
- Existing: `.github/workflows/crawler.yml` - workflow structure
- WorldMonitor: Not applicable (they use Web Workers, not GitHub Actions)

**Acceptance Criteria**:

**Agent-Executed QA Scenarios:**

```
Scenario: Workflow file is valid YAML
  Tool: Bash
  Steps:
    1. Run: python -c "import yaml; yaml.safe_load(open('.github/workflows/analyzer.yml'))"
    2. Assert: Exit code 0
    3. Assert: No YAML syntax errors

Scenario: Workflow triggers on schedule
  Tool: Read (file)
  Steps:
    1. Read: .github/workflows/analyzer.yml
    2. Assert: Contains 'schedule:' with cron expression
    3. Assert: Cron is 1 hour after crawler schedule (10AM/10PM ET)
    4. Assert: Also has 'workflow_dispatch:' for manual runs
    5. Evidence: Screenshot of schedule section

Scenario: Workflow runs successfully (manual trigger)
  Tool: Web (GitHub Actions page)
  Steps:
    1. Go to GitHub repo → Actions → Analyzer workflow
    2. Click "Run workflow"
    3. Wait for completion
    4. Assert: Workflow shows green checkmark
    5. Assert: Logs show analyzer executed
    6. Evidence: Screenshot of successful run

Scenario: Environment variables configured
  Tool: Bash
  Steps:
    1. Check: GitHub Settings → Secrets
    2. Assert: ALIBABA_API_KEY secret exists
    3. Assert: SUPABASE_URL secret exists
    4. Assert: SUPABASE_KEY secret exists
    5. Evidence: List of secrets (redacted values)
```

**Commit**: YES
- Message: `ci(actions): add analyzer workflow for automated hotspot detection`
- Files: `.github/workflows/analyzer.yml`
- Pre-commit: Validate YAML syntax

---

### Task 8: End-to-End Testing

**What to do**:
Comprehensive end-to-end validation:
1. Run full pipeline on test dataset
2. Verify database state before/after
3. Validate cluster quality (not too many, not too few)
4. Check signal detection accuracy
5. Verify LLM output quality
6. Performance check (completes in <30 min)
7. Create test report

**Must NOT do**:
- Do not modify production data
- Do not skip error scenarios

**Recommended Agent Profile**:
- **Category**: unspecified-high
- **Reason**: Complex validation across multiple components, database state verification, quality metrics
- **Skills**: None needed

**Parallelization**:
- **Can Run In Parallel**: NO - Wave 4
- **Blocks**: None (final task)
- **Blocked By**: Task 7 (GitHub Actions)

**References**:
- All previous tasks
- WorldMonitor: `analysis-core.ts` acceptance patterns

**Acceptance Criteria**:

**Agent-Executed QA Scenarios:**

```
Scenario: End-to-end pipeline succeeds
  Tool: Bash (GitHub Actions or local)
  Steps:
    1. Trigger analyzer workflow
    2. Wait for completion
    3. Assert: Status is "success"
    4. Assert: Duration < 30 minutes
    5. Evidence: Screenshot of completed run

Scenario: Database shows analysis results
  Tool: Bash (psql)
  Steps:
    1. Query: SELECT COUNT(*) FROM analysis_clusters WHERE created_at > NOW() - INTERVAL '1 hour'
    2. Assert: Count > 0
    3. Query: SELECT AVG(article_count) FROM analysis_clusters
    4. Assert: Average is between 3-10 (reasonable cluster sizes)
    5. Evidence: Query results

Scenario: Cluster quality is good
  Tool: Bash (psql)
  Steps:
    1. Query: SELECT COUNT(DISTINCT cluster_id) FROM article_analyses
    2. Assert: Number of clusters is reasonable (50-200 for 1000 articles)
    3. Query: Find largest cluster
    4. Assert: No cluster has >50 articles (indicates over-clustering)
    5. Evidence: Distribution statistics

Scenario: LLM summaries are valid
  Tool: Bash (psql)
  Steps:
    1. Query: SELECT summary FROM analysis_clusters LIMIT 3
    2. Assert: Summaries are non-empty
    3. Assert: Summaries are coherent English text
    4. Assert: Length is 100-500 chars (reasonable)
    5. Evidence: Save sample summaries

Scenario: Incremental processing works
  Tool: Bash (python + psql)
  Steps:
    1. Count unanalyzed articles before: SELECT COUNT(*) FROM articles WHERE analyzed_at IS NULL
    2. Run analyzer
    3. Count after: Should be 0 (or close to it)
    4. Run analyzer again immediately
    5. Assert: Second run processes 0 articles (all already analyzed)
    6. Evidence: Before/after counts

Scenario: Error scenarios handled
  Tool: Bash (python)
  Steps:
    1. Inject bad data: Insert article with empty content
    2. Run analyzer
    3. Assert: Completes without crash
    4. Assert: Log shows error but continues
    5. Assert: Valid articles still processed
    6. Evidence: Error log screenshot
```

**Commit**: YES
- Message: `test(e2e): add end-to-end validation and test report`
- Files: `tests/test_analyzer_e2e.py`, `tests/report.md`
- Pre-commit: All tests pass

---

### Task 9: 免费数据源集成（Free Data Sources）

**What to do**:
集成 worldmonitor 中可用的免费/低成本数据源，增强分析维度：

1. **FRED 美国经济数据** (`scripts/datasources/fred_client.py`)
   - 免费 API，需申请 API key (https://fred.stlouisfed.org/docs/api/api_key.html)
   - 获取指标：联邦基金利率、CPI、失业率、GDP 等
   - 用途：经济数据信号增强

2. **GDELT 全球事件数据库** (`scripts/datasources/gdelt_client.py`)
   - 完全免费，无需 API key
   - 获取全球事件地理分布数据
   - 用途：地缘政治事件强度评估

3. **USGS 地震数据** (`scripts/datasources/earthquake_client.py`)
   - 完全免费，无需 API key
   - 获取 4.5 级以上地震数据
   - 用途：自然灾害信号检测

4. **World Bank 指标** (`scripts/datasources/worldbank_client.py`)
   - 完全免费，无需 API key
   - 获取各国经济指标：GDP、教育、研发支出等
   - 用途：国家稳定性评估

5. **增强信号检测器** (`scripts/datasources/enhanced_signals.py`)
   - 结合多数据源生成增强信号
   - 新增信号类型：
     - `economic_indicator_alert` - 关键经济指标异常
     - `natural_disaster_signal` - 自然灾害相关新闻
     - `geopolitical_intensity` - 地缘政治事件强度

**Must NOT do**:
- 不要调用付费 API（如 ACLED 需要付费 token）
- 不要存储大量历史数据（只保留最近 30 天）
- 不要实时轮询（在分析时批量获取）

**Recommended Agent Profile**:
- **Category**: unspecified-high
- **Reason**: Multiple API integrations, data transformation, caching
- **Skills**: None needed

**Parallelization**:
- **Can Run In Parallel**: YES - Wave 5 (与 Task 10 并行)
- **Blocks**: Task 11 (Enhanced Analyzer)
- **Blocked By**: Task 3 (Configuration)

**References**:
- WorldMonitor: `/api/fred-data.js`, `/api/gdelt-geo.js`, `/api/earthquakes.js`, `/api/worldbank.js`
- FRED API Docs: https://fred.stlouisfed.org/docs/api/fred/series_observations.html
- GDELT API: https://blog.gdeltproject.org/gdelt-2-0-our-global-world-in-realtime/

**Cost Analysis**:
| 数据源 | 费用 | 限额 | 说明 |
|--------|------|------|------|
| FRED | 免费 | 120 requests/min | 需 API key，申请即得 |
| GDELT | 免费 | 无限制 | 无需 key |
| USGS | 免费 | 无限制 | 无需 key |
| World Bank | 免费 | 100 req/sec | 无需 key |
| **总计** | **$0** | - | 完全免费 |

**Acceptance Criteria**:

**Agent-Executed QA Scenarios:**

```
Scenario: FRED client fetches data
  Tool: Bash (python)
  Preconditions: FRED_API_KEY configured
  Steps:
    1. Run: python -c "from scripts.datasources.fred_client import FREDClient; c = FREDClient(); data = c.get_series('FEDFUNDS'); print(f'Got {len(data)} records')"
    2. Assert: Returns list of observations
    3. Assert: Data includes date and value fields
    4. Evidence: Save sample data

Scenario: GDELT client fetches events
  Tool: Bash (python)
  Steps:
    1. Run: python -c "from scripts.datasources.gdelt_client import GDELTClient; c = GDELTClient(); events = c.query('protest', days=7); print(f'Got {len(events)} events')"
    2. Assert: Returns list of events
    3. Assert: Events have lat/lon coordinates
    4. Evidence: Save sample events

Scenario: USGS earthquake data
  Tool: Bash (python)
  Steps:
    1. Run: python -c "from scripts.datasources.earthquake_client import USGSClient; c = USGSClient(); quakes = c.get_recent(); print(f'Got {len(quakes)} earthquakes')"
    2. Assert: Returns list of earthquakes
    3. Assert: Each has magnitude >= 4.5
    4. Evidence: Save sample data

Scenario: World Bank indicators
  Tool: Bash (python)
  Steps:
    1. Run: python -c "from scripts.datasources.worldbank_client import WorldBankClient; c = WorldBankClient(); data = c.get_indicator('NY.GDP.MKTP.CD', 'USA'); print(f'Got {len(data)} years')"
    2. Assert: Returns historical GDP data
    3. Assert: Data includes year and value
    4. Evidence: Save sample data

Scenario: Enhanced signals combine data sources
  Tool: Bash (python)
  Steps:
    1. Create test news cluster about "earthquake"
    2. Run: python -c "from scripts.datasources.enhanced_signals import EnhancedSignalDetector; d = EnhancedSignalDetector(); signals = d.detect(cluster)"
    3. Assert: If USGS has recent quake, signal includes disaster alert
    4. Assert: Signal has combined confidence score
    5. Evidence: Save signal output
```

**Commit**: YES
- Message: `feat(data): add free data sources (FRED, GDELT, USGS, World Bank)`
- Files: `scripts/datasources/` (4 client modules + enhanced signals)
- Pre-commit: All clients tested individually

---

### Task 10: UI 仪表板开发（Web Dashboard）

**What to do**:
开发中文 Web 仪表板，展示热点分析结果：

1. **技术选型**: Python Streamlit (推荐) 或 Flask
   - Streamlit 优点：快速开发、内置组件、自动响应式
   - Flask 优点：更灵活、可扩展性强
   - **推荐 Streamlit** 用于 MVP

2. **页面结构**:
   - `🏠 概览首页` (web/app.py:home_page)
     - 今日热点卡片（TOP 5）
     - 信号统计图表
     - 最新分析摘要
   
   - `🔥 热点详情` (web/app.py:hotspots_page)
     - 热点列表（按分类筛选：政治/经济/军事）
     - 热点详情弹窗：中文摘要 + 英文原文链接
     - 相关文章列表
   
   - `📊 信号中心` (web/app.py:signals_page)
     - 信号类型筛选（速度激增、来源汇聚等）
     - 信号置信度可视化
     - 历史趋势图表
   
   - `📈 数据统计` (web/app.py:stats_page)
     - 文章数量趋势
     - 分类占比饼图
     - 数据源统计

3. **数据库查询层**: `web/data_api.py`
   - 封装 Supabase 查询
   - 缓存热点数据（减少数据库查询）
   - API 函数：get_hotspots(), get_signals(), get_stats()

4. **部署配置**:
   - `web/requirements.txt` - Streamlit/flask 依赖
   - `web/README.md` - 本地运行和部署说明
   - 支持本地运行：`streamlit run web/app.py`
   - 可选部署：Streamlit Cloud (免费) 或 Railway/Heroku

**Must NOT do**:
- 不要实现用户认证（当前版本无需登录）
- 不要实现实时更新（手动刷新即可）
- 不要添加编辑功能（只读展示）

**Recommended Agent Profile**:
- **Category**: visual-engineering
- **Reason**: Frontend development, data visualization, UI/UX design
- **Skills**: ["frontend-ui-ux"]

**Parallelization**:
- **Can Run In Parallel**: YES - Wave 5 (与 Task 9 并行)
- **Blocks**: None (optional for analysis core)
- **Blocked By**: Task 1 (Database Schema)

**References**:
- Streamlit Docs: https://docs.streamlit.io/
- WorldMonitor UI pattern: Simple cards + filters + detail modals
- Visualization: Plotly or Altair for charts

**Acceptance Criteria**:

**Agent-Executed QA Scenarios:**

```
Scenario: Streamlit app starts
  Tool: Bash
  Steps:
    1. Run: pip install -r web/requirements.txt
    2. Run: timeout 5 streamlit run web/app.py || true
    3. Assert: No import errors
    4. Assert: Shows "US-Monitor 热点分析" in output
    5. Evidence: Screenshot of startup logs

Scenario: 首页显示热点卡片
  Tool: Playwright (playwright skill)
  Preconditions: Streamlit running on localhost:8501
  Steps:
    1. Navigate to: http://localhost:8501
    2. Wait for: "US-Monitor 热点分析" visible (timeout: 10s)
    3. Assert: Page contains "今日热点" section
    4. Assert: At least 1 hotspot card displayed (if data exists)
    5. Screenshot: .sisyphus/evidence/task-10-homepage.png

Scenario: 热点详情页显示中文摘要
  Tool: Playwright (playwright skill)
  Steps:
    1. Navigate to: http://localhost:8501
    2. Click: "热点详情" tab
    3. Wait for: Table or list visible
    4. Assert: Shows "中文摘要" column
    5. Assert: Shows "英文原文" links
    6. Screenshot: .sisyphus/evidence/task-10-hotspots.png

Scenario: 信号中心显示图表
  Tool: Playwright (playwright skill)
  Steps:
    1. Navigate to: http://localhost:8501
    2. Click: "信号中心" tab
    3. Wait for: Charts visible
    4. Assert: Shows signal type filters
    5. Assert: Shows confidence visualization
    6. Screenshot: .sisyphus/evidence/task-10-signals.png

Scenario: 数据统计页显示图表
  Tool: Playwright (playwright skill)
  Steps:
    1. Navigate to: http://localhost:8501
    2. Click: "数据统计" tab
    3. Wait for: Charts visible
    4. Assert: Shows article count trend chart
    5. Assert: Shows category pie chart
    6. Screenshot: .sisyphus/evidence/task-10-stats.png

Scenario: 移动端响应式
  Tool: Playwright (playwright skill)
  Steps:
    1. Set viewport: 375x812 (iPhone X)
    2. Navigate to: http://localhost:8501
    3. Assert: Layout adapts to mobile
    4. Assert: All content visible without horizontal scroll
    5. Screenshot: .sisyphus/evidence/task-10-mobile.png
```

**Commit**: YES
- Message: `feat(ui): add Streamlit dashboard with Chinese interface`
- Files: `web/app.py`, `web/data_api.py`, `web/requirements.txt`, `web/README.md`
- Pre-commit: App starts without errors

---

### Task 11: 增强分析器（Enhanced Analyzer）

**What to do**:
整合免费数据源到主分析器，生成增强型信号：

1. **修改 `scripts/analyzer.py`**:
   - 在聚类后调用免费数据源客户端
   - 根据数据源结果增强信号检测
   - 示例增强逻辑：
     - 如果新闻聚类包含 "Fed", "interest rate" + FRED 显示利率变化 → economic_indicator_alert
     - 如果新闻聚类包含 "earthquake" + USGS 显示近期地震 → natural_disaster_signal

2. **中文 LLM 提示词** (config/analysis_config.py):
```python
LLM_PROMPTS = {
    "cluster_summary": """
    请将以下英文新闻聚类总结为中文摘要。
    
    聚类包含 {article_count} 篇文章，来源：{sources}
    主要标题：{primary_title}
    
    要求：
    1. 用中文撰写，200-300 字
    2. 概括核心事件和要点
    3. 指出涉及的关键实体（人物、组织、地点）
    4. 分析可能的影响和趋势
    5. 保持客观中立的语气
    
    输出格式：
    {{
      "summary": "中文摘要",
      "key_entities": ["实体1", "实体2"],
      "impact": "影响分析",
      "trend": "趋势判断"
    }}
    """,
    
    "signal_rationale": """
    请为检测到的信号提供中文解释。
    
    信号类型：{signal_type}
    置信度：{confidence}
    相关文章数：{article_count}
    
    要求：
    1. 解释为什么这个信号重要
    2. 提供可执行的建议
    3. 说明置信度依据
    4. 保持中文输出
    """
}
```

3. **数据源关联**:
   - 为每个聚类添加 `data_sources` 字段（JSONB）
   - 存储关联的 FRED 指标、GDELT 事件、地震数据等
   - 在 UI 中展示数据源关联

4. **增强信号存储**:
   - 新增信号类型到 `analysis_signals` 表
   - 添加 `data_source` 字段标识信号来源

**Must NOT do**:
- 不要阻塞分析流程等待 API（使用 asyncio 并发）
- 不要存储原始 API 响应（只存储处理后的关键数据）
- 不要在没有新闻关联时生成信号

**Recommended Agent Profile**:
- **Category**: ultrabrain
- **Reason**: Complex integration, async orchestration, data correlation
- **Skills**: None needed

**Parallelization**:
- **Can Run In Parallel**: NO - Wave 6 (Final Integration)
- **Blocks**: Task 12 (Final Testing)
- **Blocked By**: Tasks 6, 9, 10

**References**:
- Task 6: Original analyzer structure
- Task 9: Data source clients
- WorldMonitor: Enhanced signal patterns

**Acceptance Criteria**:

**Agent-Executed QA Scenarios:**

```
Scenario: Analyzer uses Chinese prompts
  Tool: Bash (python)
  Steps:
    1. Check config: python -c "from config.analysis_config import LLM_PROMPTS; print('cluster_summary' in LLM_PROMPTS)"
    2. Assert: LLM_PROMPTS contains Chinese prompts
    3. Verify: Prompts are in Chinese with JSON format instructions
    4. Evidence: Save prompt content

Scenario: Enhanced analyzer runs with data sources
  Tool: Bash (python)
  Preconditions: All data source clients working
  Steps:
    1. Run: python scripts/analyzer.py --limit 10 --enhanced
    2. Assert: Log shows "Fetching FRED data..."
    3. Assert: Log shows "Fetching GDELT events..."
    4. Assert: Completes without errors
    5. Evidence: Full log output

Scenario: Chinese summaries stored
  Tool: Bash (psql)
  Steps:
    1. Query: SELECT summary FROM analysis_clusters ORDER BY created_at DESC LIMIT 3
    2. Assert: Summaries contain Chinese characters
    3. Assert: Length is 200-500 Chinese characters
    4. Evidence: Save sample summaries

Scenario: English source links preserved
  Tool: Bash (psql)
  Steps:
    1. Query: SELECT primary_title, primary_link FROM analysis_clusters LIMIT 1
    2. Assert: primary_title is in English
    3. Assert: primary_link is valid URL
    4. Evidence: Screenshot of query results

Scenario: Enhanced signals detected
  Tool: Bash (psql)
  Steps:
    1. Query: SELECT signal_type, data_source FROM analysis_signals WHERE data_source IS NOT NULL
    2. Assert: Shows enhanced signals (if conditions met)
    3. Assert: data_source field populated
    4. Evidence: Save query results

Scenario: Data sources linked to clusters
  Tool: Bash (psql)
  Steps:
    1. Query: SELECT data_sources FROM analysis_clusters WHERE data_sources IS NOT NULL LIMIT 1
    2. Assert: data_sources JSON contains FRED/GDELT/USGS/WorldBank keys
    3. Assert: Structure matches expected format
    4. Evidence: Save sample JSON
```

**Commit**: YES
- Message: `feat(analyzer): integrate data sources and Chinese LLM prompts`
- Files: `scripts/analyzer.py` (enhanced), `config/analysis_config.py` (Chinese prompts)
- Pre-commit: Full test run with --enhanced flag

---

### Task 12: 最终端到端测试（Final E2E Testing）

**What to do**:
完整系统端到端测试，包括：
1. 爬虫 → 分析器 → UI 完整流程
2. 中文输出质量验证
3. 数据源集成验证
4. UI 功能验证
5. 性能测试（500 文章 <30 分钟）

**Additional Test Scenarios**:

```
Scenario: 完整流程中文输出
  Tool: Playwright + Bash
  Steps:
    1. 运行爬虫获取新文章
    2. 运行分析器（带数据源增强）
    3. 打开 UI 仪表板
    4. Assert: 所有摘要在 UI 中显示为中文
    5. Assert: 点击"英文原文"链接可跳转
    6. Evidence: 录屏或截图序列

Scenario: 数据源信号验证
  Tool: Bash (python)
  Steps:
    1. 等待真实经济数据发布（或模拟）
    2. 运行分析器
    3. 检查：analysis_signals 表包含 economic_indicator_alert
    4. Assert: 信号置信度 > 0.6
    5. Evidence: 数据库查询结果

Scenario: 系统性能
  Tool: Bash (python)
  Steps:
    1. 插入 500 篇测试文章
    2. 计时：time python scripts/analyzer.py
    3. Assert: 总时间 < 30 分钟
    4. Assert: LLM 调用次数 < 200
    5. Evidence: 时间报告
```

**Commit**: YES
- Message: `test(e2e): complete system validation with Chinese output and data sources`
- Files: `tests/test_complete_system.py`, `tests/final_report.md`
- Pre-commit: All tests pass

---

## Updated Execution Strategy

### New Parallel Execution Waves

```
Wave 1 (Foundation):
├── Task 1: Database Schema
├── Task 2: LLM Client Module
└── Task 3: Configuration & Constants

Wave 2 (Core Logic):
├── Task 4: Clustering Engine
└── Task 5: Signal Detection

Wave 3 (Integration):
├── Task 6: Main Analyzer Pipeline
└── Task 7: GitHub Actions Workflow

Wave 4 (Validation):
└── Task 8: End-to-End Testing

Wave 5 (Enhancement - Can Start After Wave 1):
├── Task 9: Free Data Sources
└── Task 10: UI Dashboard

Wave 6 (Final Integration):
├── Task 11: Enhanced Analyzer
└── Task 12: Final E2E Testing

Critical Path: Task 1 → Task 4 → Task 6 → Task 11 → Task 12
UI Path: Task 1 → Task 10 (independent, can be used separately)
```

---

## Commit Strategy

| After Task | Message | Files | Verification |
|------------|---------|-------|--------------|
| 1 | `feat(db): add analysis schema for hotspot detection` | `sql/analysis_schema.sql` | Schema applies without errors |
| 2 | `feat(llm): add Alibaba Qwen3-Plus client with retry and caching` | `scripts/llm_client.py`, `.env.example` | Client imports successfully |
| 3 | `feat(config): add analysis configuration with thresholds and prompts` | `config/analysis_config.py` | Config loads correctly |
| 4 | `feat(clustering): implement Jaccard similarity clustering with inverted index` | `scripts/clustering.py` | Clustering tests pass |
| 5 | `feat(signals): implement velocity, convergence, triangulation detection` | `scripts/signal_detector.py` | Signal tests pass |
| 6 | `feat(analyzer): add main analysis pipeline with clustering and LLM` | `scripts/analyzer.py` | E2E test with --limit 10 |
| 7 | `ci(actions): add analyzer workflow for automated hotspot detection` | `.github/workflows/analyzer.yml` | YAML valid, workflow runs |
| 8 | `test(e2e): add end-to-end validation and test report` | `tests/test_analyzer_e2e.py`, `tests/report.md` | All tests pass |
| 9 | `feat(data): add free data sources (FRED, GDELT, USGS, World Bank)` | `scripts/datasources/` | All APIs tested |
| 10 | `feat(ui): add Streamlit dashboard with Chinese interface` | `web/` | UI loads and displays data |
| 11 | `feat(analyzer): integrate data sources and Chinese LLM prompts` | `scripts/analyzer.py`, `config/` | Enhanced analysis works |
| 12 | `test(e2e): complete system validation with Chinese output and data sources` | `tests/test_complete_system.py` | All tests pass |

---

## Success Criteria

### Verification Commands

```bash
# Test database schema
psql $SUPABASE_URL -f sql/analysis_schema.sql && echo "Schema OK"

# Test imports
python -c "from scripts.analyzer import main; print('Imports OK')"

# Run with limit
python scripts/analyzer.py --limit 10 && echo "Analyzer OK"

# Check results
psql $SUPABASE_URL -c "SELECT COUNT(*) FROM analysis_clusters" && echo "Data OK"
```

### Final Checklist
- [ ] All 12 tasks complete
- [ ] Database schema created and applied
- [ ] LLM client working with retry/caching
- [ ] Clustering produces 50-200 clusters for typical dataset
- [ ] Signal detection finds meaningful patterns
- [ ] GitHub Actions workflow runs automatically
- [ ] Analysis completes in <30 minutes
- [ ] Only unanalyzed articles processed (incremental)
- [ ] Error handling graceful (no crashes on bad data)
- [ ] **中文摘要正常输出** (Chinese summaries displayed)
- [ ] **英文原文链接可点击** (English source links work)
- [ ] **免费数据源集成** (FRED, GDELT, USGS, World Bank connected)
- [ ] **UI仪表板可访问** (Web dashboard accessible)
- [ ] **移动端响应式正常** (Mobile responsive)
- [ ] All QA scenarios pass with evidence

---

## Appendix: Free Data Sources Integration

### Available Free/Low-Cost Data Sources (from WorldMonitor)

#### 1. FRED (Federal Reserve Economic Data)
- **URL**: https://fred.stlouisfed.org/
- **Cost**: 免费（需 API key）
- **API Key**: https://fred.stlouisfed.org/docs/api/api_key.html
- **Rate Limit**: 120 requests/minute
- **Use Cases**:
  - 联邦基金利率变化 → 货币政策信号
  - CPI/PPI 数据 → 通胀信号
  - 失业率 → 经济健康度
  - GDP 增长 → 宏观趋势
- **Key Series IDs**:
  - `FEDFUNDS` - 联邦基金利率
  - `CPIAUCSL` - CPI
  - `UNRATE` - 失业率
  - `GDP` - GDP

#### 2. GDELT (Global Database of Events, Language, and Tone)
- **URL**: https://www.gdeltproject.org/
- **Cost**: 完全免费
- **API Key**: 不需要
- **Rate Limit**: 无限制（合理频率）
- **Use Cases**:
  - 全球抗议活动地理分布
  - 冲突事件强度和位置
  - 新闻情绪分析
- **Endpoints**:
  - Geo API: `https://api.gdeltproject.org/api/v2/geo/geo`
  - Document API: `https://api.gdeltproject.org/api/v2/doc/doc`

#### 3. USGS Earthquakes
- **URL**: https://earthquake.usgs.gov/
- **Cost**: 完全免费
- **API Key**: 不需要
- **Rate Limit**: 无限制
- **Use Cases**:
  - 4.5 级以上地震实时监测
  - 自然灾害新闻验证
  - 人道主义危机预警
- **Endpoint**: `https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson`

#### 4. World Bank Open Data
- **URL**: https://data.worldbank.org/
- **Cost**: 完全免费
- **API Key**: 不需要
- **Rate Limit**: 100 requests/second
- **Use Cases**:
  - 国家 GDP 数据
  - 研发投入指标
  - 互联网普及率
  - 教育支出
- **Key Indicators**:
  - `NY.GDP.MKTP.CD` - GDP (current US$)
  - `NY.GDP.MKTP.KD.ZG` - GDP growth
  - `GB.XPD.RSDV.GD.ZS` - R&D expenditure
  - `IT.NET.USER.ZS` - Internet users

#### 5. Hacker News (Bonus)
- **URL**: https://news.ycombinator.com/
- **Cost**: 完全免费
- **API**: https://github.com/HackerNews/API
- **Use Cases**:
  - 科技趋势监测
  - 创业生态信号
  - 技术话题热度

### Signal Enhancement Strategy

```python
# Example: Enhanced Signal Detection
class EnhancedSignalDetector:
    def detect_economic_signals(self, cluster, fred_data):
        """Detect economic indicator alerts"""
        economic_keywords = ['Fed', 'interest rate', 'inflation', 'CPI', 'GDP']
        
        if any(kw in cluster['primary_title'] for kw in economic_keywords):
            # Check FRED for recent changes
            recent_changes = self.check_fred_changes(fred_data)
            if recent_changes:
                return {
                    'type': 'economic_indicator_alert',
                    'confidence': 0.8,
                    'data_source': 'FRED',
                    'related_indicators': recent_changes
                }
    
    def detect_disaster_signals(self, cluster, usgs_data):
        """Detect natural disaster signals"""
        disaster_keywords = ['earthquake', 'tsunami', 'volcano', 'disaster']
        
        if any(kw in cluster['primary_title'].lower() for kw in disaster_keywords):
            # Check USGS for recent earthquakes
            recent_quakes = self.check_usgs_recent(usgs_data)
            if recent_quakes:
                return {
                    'type': 'natural_disaster_signal',
                    'confidence': 0.85,
                    'data_source': 'USGS',
                    'magnitude': recent_quakes[0]['magnitude'],
                    'location': recent_quakes[0]['place']
                }
    
    def detect_geopolitical_intensity(self, cluster, gdelt_data):
        """Detect geopolitical event intensity"""
        # Extract location from cluster
        location = self.extract_location(cluster)
        
        # Query GDELT for events near that location
        nearby_events = self.query_gdelt_nearby(gdelt_data, location)
        
        if len(nearby_events) > 5:
            return {
                'type': 'geopolitical_intensity',
                'confidence': min(0.9, 0.5 + len(nearby_events) * 0.05),
                'data_source': 'GDELT',
                'event_count': len(nearby_events),
                'avg_tone': self.calculate_avg_tone(nearby_events)
            }
```

### Cost Summary

| Data Source | Monthly Cost | Monthly Quota | Setup Effort |
|-------------|--------------|---------------|--------------|
| FRED | $0 | 120 req/min | Low (API key) |
| GDELT | $0 | Unlimited | None |
| USGS | $0 | Unlimited | None |
| World Bank | $0 | 100 req/sec | None |
| **Total** | **$0** | - | **Low** |

### Implementation Notes

1. **Caching Strategy**: Cache API responses for 1-6 hours to reduce calls
2. **Async Fetching**: Use `asyncio.gather()` to fetch all data sources concurrently
3. **Graceful Degradation**: If one API fails, continue with others
4. **Rate Limiting**: Implement client-side rate limiting for FRED (120/min)
5. **Data Retention**: Store only processed/aggregated data, not raw API responses

---

## Appendix: Key WorldMonitor Patterns

### Jaccard Clustering Algorithm
```python
# From analysis-core.ts:154-280
def cluster_news(items):
    # 1. Tokenize all titles
    # 2. Build inverted index (token -> article indices)
    # 3. For each article, find candidates sharing tokens
    # 4. Calculate Jaccard similarity with candidates
    # 5. Group if similarity >= 0.5
    # 6. Sort clusters by tier and recency
    # 7. Aggregate threats and geo locations
```

### Signal Detection Pattern
```python
# From analysis-core.ts:302-434
def detect_convergence(clusters):
    # 1. Filter clusters with 3+ sources
    # 2. Check source types (wire, gov, intel, mainstream)
    # 3. If 3+ different types in 1 hour window
    # 4. Generate signal with confidence 0.6-0.95
    # 5. Deduplicate via generateDedupeKey
```

### Escalation Scoring
```python
# From hotspot-escalation.ts:174-217
COMPONENT_WEIGHTS = {
    'news': 0.35,
    'cii': 0.25,
    'geo': 0.25,
    'military': 0.15
}
# Calculate component scores (0-100)
# Weighted sum → raw score → 1-5 scale
# Blend with static baseline (30% static, 70% dynamic)
```

---

## Notes for Implementer

1. **Database Performance**: With 1000+ articles, clustering is O(n²). Use inverted index optimization from worldmonitor.

2. **LLM Costs**: At ~$0.002 per 1K tokens, 200 calls × 4K tokens = $1.60 per run. Well within reasonable budget.

3. **Signal Cooldown**: Implement 2-hour cooldown to prevent signal spam (same as worldmonitor).

4. **Testing Strategy**: Start with `--limit 10`, then 50, then full dataset. Monitor performance.

5. **Debugging**: Add verbose logging option. Store intermediate cluster data for inspection.

6. **Schema Evolution**: Add `version` column to analysis tables for future migrations.

7. **Fallback Strategy**: If LLM API fails, fall back to keyword-based summarization (title + snippet extraction).

---

*Plan generated by Prometheus (Plan Builder)*  
*Based on worldmonitor architecture analysis and Metis gap review*
