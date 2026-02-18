#!/usr/bin/env python3
"""
实体标准化与分类兜底逻辑
"""

import re
from typing import Any, Dict, List, Optional, Tuple

ENTITY_TYPE_OPTIONS = [
    "person",
    "organization",
    "location",
    "event",
    "holiday",
    "metric",
    "media",
    "product",
    "law_policy",
    "other",
]

ENTITY_TYPE_FILTER_OPTIONS = ENTITY_TYPE_OPTIONS + ["concept"]

ENTITY_TYPE_ALIASES = {
    "org": "organization",
    "company": "organization",
    "institution": "organization",
    "place": "location",
    "geo": "location",
    "geography": "location",
    "people": "person",
    "human": "person",
    "policy": "law_policy",
    "law": "law_policy",
    "regulation": "law_policy",
    "holiday_event": "holiday",
    "concept": "other",
}

LOW_CONFIDENCE_THRESHOLD = 0.75
MIN_ENTITY_LENGTH = 2
MAX_ENTITY_LENGTH = 100

_CJK_PERSON_RE = re.compile(r"^[\u4e00-\u9fff]{2,4}$")
_CJK_PERSON_DOT_RE = re.compile(r"^[\u4e00-\u9fff]{1,8}·[\u4e00-\u9fff]{1,8}$")
_EN_PERSON_RE = re.compile(r"^[A-Z][a-z]+(?:[ .-][A-Z][a-z]+){1,3}$")

_METRIC_KEYWORDS = {
    "zh": ["指数", "利率", "收益率", "通胀", "失业率", "增长率", "开工率", "数据", "指标"],
    "en": [
        "index",
        "rate",
        "yield",
        "inflation",
        "unemployment",
        "housing starts",
        "cpi",
        "ppi",
        "gdp",
    ],
}
_HOLIDAY_KEYWORDS = {
    "zh": ["节", "节日", "纪念日", "假日"],
    "en": [" day", "holiday", "festival", "christmas", "thanksgiving", "halloween"],
}
_LOCATION_KEYWORDS = {
    "zh": ["州", "市", "省", "县", "郡", "地区", "半岛", "海峡"],
    "en": [" state", "city", "county", "province", "district", "island"],
}
_ORG_KEYWORDS = {
    "zh": ["公司", "集团", "委员会", "议会", "大学", "法院", "部", "局", "署", "银行"],
    "en": [
        " inc",
        " corp",
        " llc",
        " company",
        " committee",
        " council",
        " agency",
        " department",
        " university",
        " bank",
    ],
}
_MEDIA_KEYWORDS = {
    "zh": ["新闻网", "通讯社", "报", "电视台", "媒体"],
    "en": [" news", " times", " post", " journal", " media", " press"],
}
_LAW_KEYWORDS = {
    "zh": ["法案", "法律", "政策", "条例", "禁令"],
    "en": [" act", " bill", " law", " policy", "regulation", "executive order"],
}
_PRODUCT_KEYWORDS = {
    "zh": ["手机", "芯片", "系统", "平台", "软件"],
    "en": ["iphone", "android", "chatgpt", "model", "platform", "software"],
}
_EVENT_KEYWORDS = {
    "zh": ["选举", "战争", "峰会", "抗议", "袭击", "会谈", "比赛"],
    "en": ["election", "war", "summit", "protest", "attack", "meeting", "tournament"],
}


def _safe_float(value: Any) -> Optional[float]:
    """Parse numeric values safely."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0 or number > 1:
        return None
    return round(number, 4)


def normalize_entity_type(raw_entity_type: Any) -> str:
    """规范化实体类型值"""
    if not isinstance(raw_entity_type, str):
        return "other"
    normalized = raw_entity_type.strip().lower().replace("-", "_").replace("/", "_")
    normalized = ENTITY_TYPE_ALIASES.get(normalized, normalized)
    if normalized not in ENTITY_TYPE_OPTIONS:
        return "other"
    return normalized


def _contains_keywords(text: str, keyword_group: Dict[str, List[str]]) -> bool:
    """Check if text contains any keyword in predefined groups."""
    lowered = text.lower()
    for keyword in keyword_group.get("zh", []):
        if keyword in text:
            return True
    for keyword in keyword_group.get("en", []):
        if keyword.lower() in lowered:
            return True
    return False


def _looks_like_person(name: str) -> bool:
    """Heuristic person-name detection."""
    stripped = name.strip()
    if _CJK_PERSON_RE.match(stripped) or _CJK_PERSON_DOT_RE.match(stripped):
        return True
    return bool(_EN_PERSON_RE.match(stripped))


def _rule_based_entity_type(name: str) -> str:
    """规则兜底分类"""
    if _contains_keywords(name, _METRIC_KEYWORDS):
        return "metric"
    if name.endswith("日") and not any(char.isdigit() for char in name):
        return "holiday"
    if _contains_keywords(name, _HOLIDAY_KEYWORDS):
        return "holiday"
    if _contains_keywords(name, _LAW_KEYWORDS):
        return "law_policy"
    if _contains_keywords(name, _MEDIA_KEYWORDS):
        return "media"
    if _contains_keywords(name, _ORG_KEYWORDS):
        return "organization"
    if _contains_keywords(name, _LOCATION_KEYWORDS):
        return "location"
    if _contains_keywords(name, _PRODUCT_KEYWORDS):
        return "product"
    if _contains_keywords(name, _EVENT_KEYWORDS):
        return "event"
    if _looks_like_person(name):
        return "person"
    return "other"


def _apply_guardrails(
    name: str, llm_type: str, confidence: Optional[float]
) -> Tuple[str, str]:
    """对LLM分类结果执行强规则校验"""
    rule_type = _rule_based_entity_type(name)

    if llm_type == "other":
        if rule_type != "other":
            return rule_type, "rule_fallback"
        return "other", "llm"

    if confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD:
        if rule_type != "other":
            return rule_type, "rule_low_confidence"

    invalid_person_types = {
        "metric",
        "holiday",
        "location",
        "organization",
        "media",
        "law_policy",
    }
    if llm_type == "person" and rule_type in invalid_person_types:
        return rule_type, "rule_override"

    if llm_type == "organization" and rule_type == "person":
        return "person", "rule_override"

    return llm_type, "llm"


def normalize_entity_mentions(raw_entities: Any) -> List[Dict[str, Any]]:
    """标准化LLM实体输出并应用分类兜底"""
    if not isinstance(raw_entities, list):
        return []

    normalized_entities: List[Dict[str, Any]] = []
    entity_index: Dict[Tuple[str, str], int] = {}

    for item in raw_entities:
        if isinstance(item, str):
            mention = item.strip()
            canonical_name = mention
            llm_type = "other"
            confidence = None
            evidence_span = ""
        elif isinstance(item, dict):
            mention = str(
                item.get("mention")
                or item.get("entity_name")
                or item.get("name")
                or item.get("canonical_name")
                or ""
            ).strip()
            canonical_name = str(item.get("canonical_name") or mention).strip()
            llm_type = normalize_entity_type(item.get("entity_type") or item.get("type"))
            confidence = _safe_float(item.get("confidence"))
            evidence_span = str(
                item.get("evidence_span") or item.get("evidence") or item.get("context") or ""
            ).strip()
        else:
            continue

        if not mention:
            continue
        if len(canonical_name) < MIN_ENTITY_LENGTH or len(canonical_name) > MAX_ENTITY_LENGTH:
            continue

        final_type, source = _apply_guardrails(canonical_name, llm_type, confidence)
        normalized_item = {
            "mention": mention[:MAX_ENTITY_LENGTH],
            "canonical_name": canonical_name[:MAX_ENTITY_LENGTH],
            "entity_type": final_type,
            "confidence": confidence,
            "evidence_span": evidence_span[:200],
            "classification_source": source,
        }

        dedupe_key = (
            normalized_item["canonical_name"].lower(),
            normalized_item["entity_type"],
        )
        if dedupe_key in entity_index:
            existing_idx = entity_index[dedupe_key]
            existing_conf = normalized_entities[existing_idx].get("confidence") or 0
            current_conf = normalized_item.get("confidence") or 0
            if current_conf > existing_conf:
                normalized_entities[existing_idx] = normalized_item
            continue

        entity_index[dedupe_key] = len(normalized_entities)
        normalized_entities.append(normalized_item)

    return normalized_entities


def extract_entity_names(entity_mentions: List[Dict[str, Any]]) -> List[str]:
    """从标准化实体中提取名称列表"""
    names: List[str] = []
    seen = set()
    for entity in entity_mentions:
        name = str(entity.get("canonical_name") or entity.get("mention") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def merge_entity_metadata(
    existing_metadata: Any,
    entity: Dict[str, Any],
    model_name: str = "",
    prompt_version: str = "",
) -> Dict[str, Any]:
    """构建实体入库元数据"""
    metadata = existing_metadata if isinstance(existing_metadata, dict) else {}
    aliases = metadata.get("aliases", [])
    if not isinstance(aliases, list):
        aliases = []

    for alias in [entity.get("mention"), entity.get("canonical_name")]:
        if alias and alias not in aliases:
            aliases.append(alias)

    metadata["aliases"] = aliases[:20]
    metadata["classification_source"] = entity.get("classification_source", "llm")
    metadata["llm_confidence"] = entity.get("confidence")
    metadata["evidence_span"] = entity.get("evidence_span", "")
    metadata["canonical_name"] = entity.get("canonical_name", "")
    if model_name:
        metadata["model_name"] = model_name
    if prompt_version:
        metadata["prompt_version"] = prompt_version
    return metadata
