# US-Monitor Agent Guidelines

Python news analysis system with tiered LLM processing and entity tracking.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run syntax check
python3 -m py_compile scripts/*.py web/*.py

# Run tests
python3 tests/test_e2e.py

# Run single test function
python3 -c "from tests.test_e2e import test_tokenization; test_tokenization()"

# Run analyzer
python3 scripts/analyzer.py --limit 500
python3 scripts/enhanced_analyzer.py --limit 1000

# Start web UI
streamlit run web/app.py

# Reset analysis status
python3 scripts/reset_analysis.py --hours 24
```

## Code Style

### Python Standards
- **Python 3.11+** with type hints (`typing` module)
- **Docstrings**: Chinese for business logic, English for technical utilities
- **Imports**: stdlib → third-party → local (with sys.path.insert for local)
- **Line length**: 100 characters max
- **Quotes**: Double quotes for strings, single quotes for dict keys

### Naming Conventions
```python
# Functions: snake_case with Chinese docstrings
def load_unanalyzed_articles(limit: int = None) -> List[Dict]:
    """加载未分析的文章"""
    pass

# Classes: PascalCase
class HotspotAnalyzer:
    """热点分析器"""
    pass

# Constants: UPPER_SNAKE_CASE
MAX_ARTICLES_PER_RUN = 500
HOT_THRESHOLD = 3

# Private methods: _leading_underscore
def _quick_translate(self, cluster: Dict) -> Dict:
    pass
```

### Type Hints
```python
from typing import List, Dict, Optional, Any

def process_clusters(
    clusters: List[Dict], 
    depth: str = "full"
) -> Optional[List[Dict]]:
    pass
```

### Logging Pattern
```python
import logging

logger = logging.getLogger(__name__)
logger.info(f"[CLUSTER_START] cluster_id: {cluster_id[:8]}...")
logger.warning(f"[CACHE_MISS] key: {cache_key}")
logger.error(f"[API_ERROR] error: {str(e)[:100]}")
```

### Error Handling
```python
try:
    result = api_call()
except Exception as e:
    logger.error(f"[OPERATION_FAILED] error: {str(e)}")
    # Return safe default or re-raise
    return {"error": str(e), "parsed": False}
```

## Project Structure

```
scripts/
  analyzer.py           # Main analyzer with tiered processing
  enhanced_analyzer.py  # Extended with external data sources
  llm_client.py         # LLM client with caching
  clustering.py         # News clustering algorithms
  signal_detector.py    # Signal detection logic

web/
  app.py                # Streamlit web interface

config/
  analysis_config.py    # Analysis configuration
  entity_config.py      # Entity classification rules

tests/
  test_e2e.py           # End-to-end tests

sql/
  analysis_schema.sql   # Database schema
```

## Key Principles

1. **Tiered Processing**: Hot clusters (≥3 articles) get full LLM analysis; cold clusters get quick translation only
2. **Configuration-Driven**: Entity types and keywords live in `config/entity_config.py`
3. **Bilingual**: Chinese for user-facing content, English for technical internals
4. **Always Log**: Use structured logging with [CATEGORY] prefixes for traceability
5. **Never Suppress**: Don't use `as any` or `@ts-ignore` equivalents; fix type errors properly

## Database

- **Supabase** PostgreSQL backend
- Key tables: `articles`, `analysis_clusters`, `analysis_signals`, `entities`
- Entity tracking: automatic extraction and popularity scoring
