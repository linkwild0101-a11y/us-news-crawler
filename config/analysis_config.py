#!/usr/bin/env python3
"""
US-Monitor 热点分析配置
包含所有阈值、常量、提示词
"""

# ============================================
# 1. 聚类配置
# ============================================

# Jaccard相似度阈值
SIMILARITY_THRESHOLD = 0.5

# 最大文章处理数量
MAX_ARTICLES_PER_RUN = 500

# 最大LLM API调用次数
MAX_LLM_CALLS = 200

# 信号冷却时间（小时）
SIGNAL_COOLDOWN_HOURS = 2

# 文章时间窗口（小时）
ARTICLE_TIME_WINDOW_HOURS = 24

# ============================================
# 2. 停用词（英文）
# ============================================

STOP_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "up",
    "about",
    "into",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "between",
    "among",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "must",
    "shall",
    "can",
    "need",
    "dare",
    "ought",
    "used",
    "it",
    "its",
    "itself",
    "this",
    "that",
    "these",
    "those",
    "i",
    "me",
    "my",
    "myself",
    "we",
    "our",
    "ours",
    "ourselves",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
    "he",
    "him",
    "his",
    "himself",
    "she",
    "her",
    "hers",
    "herself",
    "they",
    "them",
    "their",
    "theirs",
    "themselves",
    "what",
    "which",
    "who",
    "whom",
    "whose",
    "whatever",
    "whichever",
    "whoever",
    "whomever",
    "as",
    "until",
    "while",
    "so",
    "than",
    "too",
    "very",
    "just",
    "now",
    "then",
    "once",
    "here",
    "there",
    "when",
    "where",
    "why",
    "how",
    "all",
    "each",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "nor",
    "not",
    "only",
    "own",
    "same",
    "s",
    "t",
    "don",
    "doesn",
    "didn",
    "wasn",
    "weren",
    "haven",
    "hasn",
    "hadn",
    "won",
    "wouldn",
    "couldn",
    "shouldn",
    "isn",
    "aren",
    "ain",
    "ma",
    "mightn",
    "mustn",
    "needn",
    "shan",
    "shouldn",
    "wasn",
    "weren",
    "won",
    "wouldn",
    "aren",
    "couldn",
    "didn",
    "doesn",
    "hadn",
    "hasn",
    "haven",
    "isn",
    "let",
    "mayn",
    "mightn",
    "mustn",
    "needn",
    "oughtn",
    "shan",
    "shouldn",
    "wasn",
    "weren",
    "won",
    "wouldn",
    "new",
    "said",
    "say",
    "says",
    "according",
    "also",
    "per",
    "amid",
    "among",
    "off",
    "over",
    "under",
    "again",
    "further",
    "then",
    "once",
}

# ============================================
# 3. 主题关键词
# ============================================

TOPIC_KEYWORDS = {
    "military": [
        "military",
        "defense",
        "pentagon",
        "army",
        "navy",
        "air force",
        "marines",
        "coast guard",
        "war",
        "conflict",
        "combat",
        "troop",
        "soldier",
        "veteran",
        "weapon",
        "missile",
        "drone",
        "nuclear",
        "tank",
        "aircraft",
        "carrier",
        "submarine",
        "intelligence",
        "cia",
        "nsa",
        "dod",
        "defense department",
        "homeland security",
        "border",
        "immigration",
        "terrorism",
        "cyber",
        "cybersecurity",
        "espionage",
        "surveillance",
        "treaty",
        "alliance",
        "nato",
        "un peacekeeping",
        "geopolitics",
        "strategy",
        "tactics",
    ],
    "politics": [
        "politics",
        "government",
        "congress",
        "senate",
        "house",
        "white house",
        "president",
        "vice president",
        "secretary",
        "ambassador",
        "diplomacy",
        "foreign policy",
        "domestic policy",
        "election",
        "vote",
        "campaign",
        "democrat",
        "republican",
        "gop",
        "liberal",
        "conservative",
        "legislation",
        "bill",
        "law",
        "regulation",
        "executive order",
        "judicial",
        "supreme court",
        "federal",
        "state",
        "governor",
        "mayor",
        "sanction",
        "trade war",
        "diplomatic",
        "summit",
        "treaty",
        "negotiation",
        "bilateral",
        "multilateral",
    ],
    "economy": [
        "economy",
        "economic",
        "finance",
        "financial",
        "fed",
        "federal reserve",
        "interest rate",
        "inflation",
        "deflation",
        "recession",
        "gdp",
        "growth",
        "stock",
        "market",
        "trading",
        "wall street",
        "nasdaq",
        "dow jones",
        "s&p 500",
        "investment",
        "investor",
        "fund",
        "etf",
        "bond",
        "treasury",
        "yield",
        "dollar",
        "euro",
        "yuan",
        "currency",
        "exchange rate",
        "trade",
        "tariff",
        "export",
        "import",
        "supply chain",
        "manufacturing",
        "jobs",
        "employment",
        "unemployment",
        "labor",
        "wage",
        "salary",
        "consumer",
        "spending",
        "retail",
        "sales",
        "housing",
        "mortgage",
        "real estate",
        "bank",
        "banking",
        "cryptocurrency",
        "bitcoin",
        "crypto",
        "fintech",
    ],
}

# ============================================
# 4. 信号检测阈值
# ============================================

SIGNAL_THRESHOLDS = {
    # 新闻速度激增：1小时内超过此数量的文章
    "velocity_spike_count": 5,
    # 来源汇聚：需要至少这么多不同类型的来源
    "convergence_min_sources": 3,
    # 三角验证：需要至少3种类型的来源（通讯社+政府+情报）
    "triangulation_min_types": 3,
    # 热点升级：文章数量阈值
    "hotspot_min_articles": 3,
    # 最大置信度
    "max_confidence": 0.95,
    # 最小置信度
    "min_confidence": 0.6,
}

# ============================================
# 5. LLM 提示词（中文）
# ============================================

LLM_PROMPTS = {
    "cluster_summary": """请将以下英文新闻聚类总结为中文摘要。

聚类包含 {article_count} 篇文章，来源：{sources}
主要标题：{primary_title}
内容片段：
{content_samples}

要求：
1. 用中文撰写，200-300字
2. 概括核心事件和要点
3. 指出涉及的关键实体，并对每个实体进行类型分类
4. 分析可能的影响和趋势
5. 保持客观中立的语气
6. 实体类型只能从以下枚举中选择：
   person / organization / location / event / holiday
   / metric / media / product / law_policy / other
7. confidence 为 0-1 之间的小数，evidence_span 给出原文中触发判断的短证据

必须按以下JSON格式输出，不要添加其他内容：
{{
  "summary": "中文摘要（200-300字）",
  "key_entities": ["实体1", "实体2", "实体3"],
  "entity_mentions": [
    {{
      "mention": "原文提及",
      "canonical_name": "标准实体名",
      "entity_type": "person",
      "confidence": 0.92,
      "evidence_span": "用于判断实体类型的短文本"
    }}
  ],
  "impact": "影响分析（50-100字）",
  "trend": "趋势判断（50-100字）"
}}""",
    "signal_rationale": """请为检测到的信号提供中文解释。

信号类型：{signal_type}
置信度：{confidence}
相关文章数：{article_count}
聚类摘要：{cluster_summary}

要求：
1. 解释为什么这个信号重要
2. 提供可执行的建议
3. 说明置信度依据
4. 说明该信号在业务上代表什么
5. 保持中文输出

输出格式：
{{
  "importance": "重要性说明",
  "meaning": "业务含义说明",
  "actionable": "可执行建议",
  "confidence_reason": "置信度理由"
}}""",
    "hotspot_escalation": """请分析以下热点事件的升级程度。

聚类信息：
- 主题：{topic}
- 文章数：{article_count}
- 时间跨度：{time_span}
- 来源多样性：{source_diversity}

请按以下维度评分（0-100）：
- 新闻热度：基于文章数量和速度
- 地缘政治影响：涉及的国家和地区
- 军事活动强度：是否涉及军事行动
- 经济影响：对市场/贸易的影响

输出JSON格式：
{{
  "news_velocity_score": 数值,
  "geopolitical_score": 数值,
  "military_score": 数值,
  "economic_score": 数值,
  "escalation_level": "low/medium/high/critical",
  "rationale": "评分理由（中文）"
}}""",
}

# ============================================
# 6. 信号类型说明
# ============================================

SIGNAL_TYPES = {
    "velocity_spike": {
        "name": "新闻速度激增",
        "description": "短时间内大量相关新闻涌现",
        "icon": "📈",
    },
    "convergence": {
        "name": "来源汇聚",
        "description": "多种类型来源同时报道，增加可信度",
        "icon": "🎯",
    },
    "triangulation": {
        "name": "情报三角验证",
        "description": "通讯社、政府、情报机构三方信息交叉验证",
        "icon": "🔺",
    },
    "hotspot_escalation": {
        "name": "热点升级",
        "description": "事件热度持续上升，可能升级",
        "icon": "🔥",
    },
    "economic_indicator_alert": {
        "name": "经济指标异常",
        "description": "关键经济指标出现异常波动",
        "icon": "💹",
    },
    "natural_disaster_signal": {
        "name": "自然灾害信号",
        "description": "检测到自然灾害相关新闻",
        "icon": "🌊",
    },
    "geopolitical_intensity": {
        "name": "地缘政治紧张",
        "description": "地缘政治事件强度增加",
        "icon": "🌍",
    },
}

# ============================================
# 7. 数据源配置
# ============================================

DATA_SOURCES = {
    "FRED": {
        "enabled": True,
        "api_key_required": True,
        "base_url": "https://api.stlouisfed.org/fred",
        "rate_limit": "120 requests/min",
    },
    "GDELT": {
        "enabled": True,
        "api_key_required": False,
        "base_url": "https://api.gdeltproject.org/api/v2",
        "rate_limit": "unlimited",
    },
    "USGS": {
        "enabled": True,
        "api_key_required": False,
        "base_url": "https://earthquake.usgs.gov/earthquakes/feed/v1.0",
        "rate_limit": "unlimited",
    },
    "WorldBank": {
        "enabled": True,
        "api_key_required": False,
        "base_url": "https://api.worldbank.org/v2",
        "rate_limit": "100 req/sec",
    },
}

# worldmonitor 无鉴权信号端点默认配置（可被环境变量覆盖）
WORLDMONITOR_SIGNAL_CONFIG = {
    "enabled": True,
    "base_url": "https://worldmonitor.app",
    "max_priority": 2,
    "enabled_endpoints": [
        "/api/earthquakes",
        "/api/ucdp-events",
        "/api/ucdp",
        "/api/unhcr-population",
        "/api/hapi",
        "/api/macro-signals",
        "/api/yahoo-finance",
        "/api/etf-flows",
        "/api/worldbank",
        "/api/faa-status",
        "/api/service-status",
        "/api/climate-anomalies",
        "/api/nga-warnings",
    ],
}

# 关键 FRED 指标系列
FRED_SERIES = {
    "FEDFUNDS": "联邦基金利率",
    "CPIAUCSL": "消费者价格指数",
    "UNRATE": "失业率",
    "GDP": "国内生产总值",
    "PAYEMS": "非农就业人数",
    "INDPRO": "工业生产指数",
    "RSXFS": "零售销售",
    "HOUST": "新屋开工数",
}
