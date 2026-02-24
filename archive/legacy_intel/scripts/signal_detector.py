#!/usr/bin/env python3
"""
信号检测器模块
检测新闻聚类中的异常信号模式
"""

import hashlib
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import sys
import os
from urllib.parse import urlparse

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.analysis_config import (
    SIGNAL_THRESHOLDS,
    TOPIC_KEYWORDS,
    SIGNAL_TYPES,
    SIGNAL_COOLDOWN_HOURS,
)
from config.watchlist_config import (
    HIGH_TRUST_DOMAIN_HINTS,
    OFFICIAL_DOMAIN_HINTS,
    OFFICIAL_EFFECTIVE_KEYWORDS,
    WATCHLIST_HARD_GATES,
    WATCHLIST_LEVEL_THRESHOLDS,
    WATCHLIST_REVIEW_WINDOW_MINUTES,
    WATCHLIST_RISK_WEIGHTS,
    WATCHLIST_SENTINELS,
    WATCHLIST_SUGGESTED_ACTIONS,
)
from scripts.text_normalizer import contains_any_keyword, normalize_zh_text


def generate_signal_id(signal_type: str, cluster_ids: List[str]) -> str:
    """
    生成信号唯一ID

    Args:
        signal_type: 信号类型
        cluster_ids: 相关聚类ID列表

    Returns:
        信号ID
    """
    content = f"{signal_type}:{':'.join(sorted(cluster_ids))}"
    return hashlib.md5(content.encode()).hexdigest()[:16]


def generate_dedupe_key(signal_type: str, cluster_key: str, hour_bucket: int) -> str:
    """
    生成信号去重键（用于冷却期）

    Args:
        signal_type: 信号类型
        cluster_key: 聚类键
        hour_bucket: 小时桶（用于时间窗口）

    Returns:
        去重键
    """
    return f"{signal_type}:{cluster_key}:{hour_bucket}"


def classify_source(source_url: str) -> str:
    """
    分类来源类型

    Args:
        source_url: 来源URL或名称

    Returns:
        来源类型: wire/gov/intel/mainstream/financial/other
    """
    source_lower = source_url.lower()
    if "://" in source_lower:
        try:
            source_lower = urlparse(source_lower).netloc.lower()
        except Exception:
            pass

    # 通讯社
    wire_agencies = ["reuters", "ap.org", "afp", "bloomberg", "associated press"]
    for agency in wire_agencies:
        if agency in source_lower:
            return "wire"

    # 政府
    if ".gov" in source_lower:
        return "gov"

    # 情报/智库
    intel_orgs = [
        "rand.org",
        "csis.org",
        "brookings.edu",
        "cfr.org",
        "carnegie",
        "heritage.org",
        "aei.org",
        "cato.org",
        "stratfor",
        "janes.com",
    ]
    for org in intel_orgs:
        if org in source_lower:
            return "intel"

    # 主流媒体
    mainstream = [
        "nytimes.com",
        "washingtonpost.com",
        "bbc.com",
        "bbc.co.uk",
        "cnn.com",
        "nbcnews.com",
        "abcnews.go.com",
        "cbsnews.com",
        "foxnews.com",
        "usatoday.com",
        "latimes.com",
        "chicagotribune.com",
    ]
    for media in mainstream:
        if media in source_lower:
            return "mainstream"

    # 财经媒体
    financial = [
        "wsj.com",
        "ft.com",
        "cnbc.com",
        "marketwatch.com",
        "barrons.com",
        "economist.com",
        "forbes.com",
        "fortune.com",
    ]
    for media in financial:
        if media in source_lower:
            return "financial"

    return "other"


def detect_velocity_spike(
    clusters: List[Dict], time_window_hours: int = 1
) -> List[Dict]:
    """
    检测新闻速度激增信号

    Args:
        clusters: 聚类列表
        time_window_hours: 时间窗口（小时）

    Returns:
        信号列表
    """
    signals = []
    threshold = SIGNAL_THRESHOLDS["velocity_spike_count"]

    # 按小时分组统计
    hour_buckets = defaultdict(list)
    now = datetime.now()

    for cluster in clusters:
        # 假设聚类有created_at字段，这里简化处理
        # 实际应该使用cluster的created_at
        hour_buckets["current"].append(cluster)

    # 检查当前窗口
    current_count = len(hour_buckets["current"])

    if current_count >= threshold:
        # 计算置信度
        confidence = min(0.95, 0.6 + (current_count - threshold) * 0.05)

        signal = {
            "signal_id": generate_signal_id(
                "velocity_spike", [c["cluster_id"] for c in clusters]
            ),
            "signal_type": "velocity_spike",
            "name": SIGNAL_TYPES["velocity_spike"]["name"],
            "icon": SIGNAL_TYPES["velocity_spike"]["icon"],
            "confidence": confidence,
            "description": f"过去{time_window_hours}小时内出现{current_count}个新闻聚类，超过阈值{threshold}",
            "affected_clusters": [c["cluster_id"] for c in clusters],
            "details": {
                "cluster_count": current_count,
                "threshold": threshold,
                "time_window_hours": time_window_hours,
            },
            "expires_at": (now + timedelta(hours=SIGNAL_COOLDOWN_HOURS)).isoformat(),
            "created_at": now.isoformat(),
        }
        signals.append(signal)

    return signals


def detect_convergence(clusters: List[Dict], min_sources: int = None) -> List[Dict]:
    """
    检测来源汇聚信号

    Args:
        clusters: 聚类列表
        min_sources: 最小来源数量

    Returns:
        信号列表
    """
    if min_sources is None:
        min_sources = SIGNAL_THRESHOLDS["convergence_min_sources"]

    signals = []
    now = datetime.now()

    for cluster in clusters:
        source_types = set()

        source_candidates = []
        if isinstance(cluster.get("source_domains"), list):
            source_candidates.extend(cluster.get("source_domains", []))
        if isinstance(cluster.get("sources"), list):
            source_candidates.extend(cluster.get("sources", []))

        if source_candidates:
            for source in source_candidates:
                source_type = classify_source(source)
                source_types.add(source_type)
        else:
            # 没有来源信息时只给弱兜底，避免虚高分。
            if cluster["article_count"] >= 5:
                source_types = {"wire", "mainstream"}
            elif cluster["article_count"] >= 3:
                source_types = {"mainstream"}

        if len(source_types) >= min_sources:
            confidence = min(0.95, 0.6 + (len(source_types) - 2) * 0.1)

            signal = {
                "signal_id": generate_signal_id("convergence", [cluster["cluster_id"]]),
                "signal_type": "convergence",
                "name": SIGNAL_TYPES["convergence"]["name"],
                "icon": SIGNAL_TYPES["convergence"]["icon"],
                "confidence": confidence,
                "description": f'聚类"{cluster["primary_title"][:50]}..."包含{len(source_types)}种不同类型的来源',
                "affected_clusters": [cluster["cluster_id"]],
                "details": {
                    "source_types": list(source_types),
                    "source_count": len(source_types),
                    "article_count": cluster["article_count"],
                },
                "expires_at": (
                    now + timedelta(hours=SIGNAL_COOLDOWN_HOURS)
                ).isoformat(),
                "created_at": now.isoformat(),
            }
            signals.append(signal)

    return signals


def detect_triangulation(clusters: List[Dict]) -> List[Dict]:
    """
    检测情报三角验证信号
    需要同时包含 wire + gov + intel 三种来源

    Args:
        clusters: 聚类列表

    Returns:
        信号列表
    """
    signals = []
    now = datetime.now()

    required_types = {"wire", "gov", "intel"}

    for cluster in clusters:
        source_types = set()

        source_candidates = []
        if isinstance(cluster.get("source_domains"), list):
            source_candidates.extend(cluster.get("source_domains", []))
        if isinstance(cluster.get("sources"), list):
            source_candidates.extend(cluster.get("sources", []))

        if source_candidates:
            for source in source_candidates:
                source_type = classify_source(source)
                source_types.add(source_type)

        # 检查是否包含所有三种必需类型
        if required_types.issubset(source_types):
            signal = {
                "signal_id": generate_signal_id(
                    "triangulation", [cluster["cluster_id"]]
                ),
                "signal_type": "triangulation",
                "name": SIGNAL_TYPES["triangulation"]["name"],
                "icon": SIGNAL_TYPES["triangulation"]["icon"],
                "confidence": 0.9,  # 三角验证是高置信度信号
                "description": f'聚类"{cluster["primary_title"][:50]}..."获得通讯社、政府和情报机构三方交叉验证',
                "affected_clusters": [cluster["cluster_id"]],
                "details": {
                    "source_types": list(source_types),
                    "verification_types": list(required_types),
                    "article_count": cluster["article_count"],
                },
                "expires_at": (
                    now + timedelta(hours=SIGNAL_COOLDOWN_HOURS)
                ).isoformat(),
                "created_at": now.isoformat(),
            }
            signals.append(signal)

    return signals


def detect_hotspot_escalation(
    clusters: List[Dict], historical_data: List[Dict] = None
) -> List[Dict]:
    """
    检测热点升级信号

    Args:
        clusters: 聚类列表
        historical_data: 历史数据（可选）

    Returns:
        信号列表
    """
    signals = []
    now = datetime.now()
    threshold = SIGNAL_THRESHOLDS["hotspot_min_articles"]

    for cluster in clusters:
        # 计算各项评分
        scores = {}

        # 1. 新闻速度评分 (0-100)
        article_count = cluster.get("article_count", 0)
        scores["news_velocity"] = min(100, article_count * 20)

        # 2. 来源多样性评分 (0-100)
        # 基于来源类型数量
        scores["source_diversity"] = min(100, article_count * 15)

        # 3. 关键词强度评分 (0-100)
        # 检查是否包含军事/政治关键词
        title_lower = cluster.get("primary_title", "").lower()
        keyword_count = 0

        for category, keywords in TOPIC_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in title_lower:
                    keyword_count += 1

        scores["keyword_intensity"] = min(100, keyword_count * 25)

        # 4. 地理汇聚评分 (0-100)
        # 基于涉及的国家/地区数量（简化）
        scores["geographic"] = min(100, article_count * 10)

        # 计算加权总分
        # news: 35%, geo: 25%, cii: 25%, military: 15%
        total_score = (
            scores["news_velocity"] * 0.35
            + scores["geographic"] * 0.25
            + scores["source_diversity"] * 0.25
            + scores["keyword_intensity"] * 0.15
        )

        # 归一化到 0-1
        normalized_score = total_score / 100

        # 确定升级等级
        if total_score >= 80:
            escalation_level = "critical"
        elif total_score >= 60:
            escalation_level = "high"
        elif total_score >= 40:
            escalation_level = "medium"
        else:
            escalation_level = "low"

        # 只报告中等级别以上的信号
        if (
            escalation_level in ["medium", "high", "critical"]
            and article_count >= threshold
        ):
            confidence = min(0.95, normalized_score)

            signal = {
                "signal_id": generate_signal_id(
                    "hotspot_escalation", [cluster["cluster_id"]]
                ),
                "signal_type": "hotspot_escalation",
                "name": SIGNAL_TYPES["hotspot_escalation"]["name"],
                "icon": SIGNAL_TYPES["hotspot_escalation"]["icon"],
                "confidence": confidence,
                "description": f'聚类"{cluster["primary_title"][:50]}..."升级等级为{escalation_level}',
                "affected_clusters": [cluster["cluster_id"]],
                "details": {
                    "escalation_level": escalation_level,
                    "total_score": round(total_score, 2),
                    "component_scores": scores,
                    "article_count": article_count,
                    "category": cluster.get("category", "unknown"),
                },
                "expires_at": (
                    now + timedelta(hours=SIGNAL_COOLDOWN_HOURS)
                ).isoformat(),
                "created_at": now.isoformat(),
            }
            signals.append(signal)

    return signals


def _collect_source_domains(cluster: Dict[str, Any]) -> List[str]:
    """收集聚类来源域名。"""
    domains: List[str] = []
    for key in ("source_domains", "sources"):
        value = cluster.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if not item:
                continue
            text = str(item).strip().lower()
            if "://" in text:
                text = urlparse(text).netloc.lower()
            if text.startswith("www."):
                text = text[4:]
            if text and text not in domains:
                domains.append(text)
    return domains


def _domain_matches(domain: str, hints: List[str]) -> bool:
    """判断域名是否命中提示列表。"""
    for hint in hints:
        hint_lower = hint.lower()
        if domain.endswith(hint_lower) or hint_lower in domain:
            return True
    return False


def _determine_alert_level(risk_score: float) -> str:
    """按阈值映射告警等级。"""
    if risk_score >= WATCHLIST_LEVEL_THRESHOLDS["L4"]:
        return "L4"
    if risk_score >= WATCHLIST_LEVEL_THRESHOLDS["L3"]:
        return "L3"
    if risk_score >= WATCHLIST_LEVEL_THRESHOLDS["L2"]:
        return "L2"
    if risk_score >= WATCHLIST_LEVEL_THRESHOLDS["L1"]:
        return "L1"
    return "L0"


def _extract_cluster_text(cluster: Dict[str, Any]) -> str:
    """拼接用于关键词检测的文本。"""
    summary = cluster.get("summary", {}) if isinstance(cluster.get("summary"), dict) else {}
    pieces = [
        str(cluster.get("primary_title", "")),
        str(summary.get("summary", "")),
        str(summary.get("impact", "")),
        str(summary.get("trend", "")),
    ]
    return normalize_zh_text(" ".join([p for p in pieces if p]))


def _extract_cluster_entities(cluster: Dict[str, Any]) -> List[str]:
    """提取聚类实体列表。"""
    summary = cluster.get("summary", {}) if isinstance(cluster.get("summary"), dict) else {}
    entities = summary.get("key_entities", [])
    if isinstance(entities, list):
        return [str(item) for item in entities if item]
    return []


def _extract_evidence_links(cluster: Dict[str, Any], max_links: int = 5) -> List[str]:
    """提取证据链接。"""
    links: List[str] = []
    primary_link = str(cluster.get("primary_link") or "").strip()
    if primary_link:
        links.append(primary_link)

    article_refs = cluster.get("article_refs")
    if isinstance(article_refs, list):
        for row in article_refs:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "").strip()
            if url and url not in links:
                links.append(url)
            if len(links) >= max_links:
                break
    return links[:max_links]


def detect_watchlist_signals(
    clusters: List[Dict[str, Any]],
    external_data: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    检测哨兵告警信号（L1-L4）。

    输出字段对齐哨兵计划：level/risk_score/trigger_reasons/evidence_links。
    """

    now = datetime.now()
    hour_bucket = int(now.timestamp() // 3600)
    results: List[Dict[str, Any]] = []
    watchlist_external: Dict[str, Any] = {}
    if isinstance(external_data, dict):
        gdelt_payload = external_data.get("watchlist_gdelt", {})
        if isinstance(gdelt_payload, dict):
            watchlist_external = gdelt_payload

    for sentinel in WATCHLIST_SENTINELS:
        sentinel_id = str(sentinel.get("id"))
        sentinel_name = str(sentinel.get("name"))
        min_groups_hit = int(sentinel.get("min_groups_hit", 1))
        required_groups = [str(item) for item in sentinel.get("required_groups", [])]
        keyword_groups = sentinel.get("keyword_groups", {})
        if not isinstance(keyword_groups, dict):
            continue

        best_candidate: Optional[Dict[str, Any]] = None
        matched_cluster_ids: List[str] = []

        for cluster in clusters:
            text = _extract_cluster_text(cluster)
            if not text:
                continue

            hit_groups: List[str] = []
            for group_name, keywords in keyword_groups.items():
                if not isinstance(keywords, list):
                    continue
                if contains_any_keyword(text, [str(item) for item in keywords]):
                    hit_groups.append(str(group_name))

            if len(hit_groups) < min_groups_hit:
                continue
            if required_groups and not set(required_groups).issubset(set(hit_groups)):
                continue

            domains = _collect_source_domains(cluster)
            unique_domains = len(set(domains))
            official_sources = len(
                [domain for domain in domains if _domain_matches(domain, OFFICIAL_DOMAIN_HINTS)]
            )
            independent_high_trust = len(
                [domain for domain in domains if _domain_matches(domain, HIGH_TRUST_DOMAIN_HINTS)]
            )
            article_count = int(cluster.get("article_count", 0) or 0)
            entities = _extract_cluster_entities(cluster)
            entity_count = len(entities)

            scenario_score = min(1.0, len(hit_groups) / max(len(keyword_groups), 1))
            velocity_score = min(1.0, article_count / 8.0)
            convergence_score = min(1.0, unique_domains / 5.0)
            source_score = min(
                1.0,
                min(1.0, official_sources / 2.0) * 0.6
                + min(1.0, independent_high_trust / 3.0) * 0.4,
            )
            entity_score = min(1.0, entity_count / 6.0)
            external_row = watchlist_external.get(sentinel_id, {})
            external_event_count = int(
                external_row.get("event_count", 0)
            ) if isinstance(external_row, dict) else 0
            external_score = min(1.0, external_event_count / 40.0)

            risk_score = (
                WATCHLIST_RISK_WEIGHTS["scenario_match"] * scenario_score
                + WATCHLIST_RISK_WEIGHTS["velocity"] * velocity_score
                + WATCHLIST_RISK_WEIGHTS["convergence"] * convergence_score
                + WATCHLIST_RISK_WEIGHTS["source_credibility"] * source_score
                + WATCHLIST_RISK_WEIGHTS["entity_spike"] * entity_score
            )
            # 外部模板查询作为轻量加权，避免喧宾夺主
            risk_score = min(1.0, risk_score + 0.08 * external_score)

            alert_level = _determine_alert_level(risk_score)
            official_text_effective = contains_any_keyword(text, OFFICIAL_EFFECTIVE_KEYWORDS)

            l3_gate = WATCHLIST_HARD_GATES["L3"]
            l4_gate = WATCHLIST_HARD_GATES["L4"]
            pass_l3 = (
                official_sources >= int(l3_gate["official_sources_min"])
                and unique_domains >= int(l3_gate["unique_domains_min"])
            )
            pass_l4 = official_text_effective and independent_high_trust >= int(
                l4_gate["independent_high_trust_min"]
            )

            if alert_level == "L4" and not pass_l4:
                alert_level = "L3"
            if alert_level in ("L3", "L4") and not pass_l3:
                alert_level = "L2"
            if alert_level == "L0":
                continue

            trigger_reasons = [
                f"命中分组: {', '.join(hit_groups)}",
                f"来源域名: {unique_domains} 个（官方 {official_sources}）",
                f"高可信独立来源: {independent_high_trust} 个",
                f"实体数: {entity_count}，文章数: {article_count}",
            ]
            if official_text_effective:
                trigger_reasons.append("命中官方落地/生效关键词")
            if external_event_count > 0:
                trigger_reasons.append(f"外部模板查询命中 {external_event_count} 条事件")

            suggested_action = WATCHLIST_SUGGESTED_ACTIONS.get(
                alert_level, "建议人工复核并持续观察。"
            )
            review_minutes = int(WATCHLIST_REVIEW_WINDOW_MINUTES.get(alert_level, 120))
            next_review_time = (now + timedelta(minutes=review_minutes)).isoformat()
            evidence_links = _extract_evidence_links(cluster)
            confidence = min(0.95, max(0.55, risk_score))

            candidate = {
                "cluster_id": cluster.get("cluster_id"),
                "cluster_title": cluster.get("primary_title", ""),
                "risk_score": round(risk_score, 4),
                "alert_level": alert_level,
                "confidence": round(confidence, 4),
                "trigger_reasons": trigger_reasons,
                "evidence_links": evidence_links,
                "suggested_action": suggested_action,
                "next_review_time": next_review_time,
                "entities": entities[:8],
                "affected_clusters": [cluster.get("cluster_id")],
                "category": cluster.get("category", sentinel.get("category", "unknown")),
                "source_stats": {
                    "unique_domains": unique_domains,
                    "official_sources": official_sources,
                    "independent_high_trust": independent_high_trust,
                    "official_text_effective": official_text_effective,
                    "external_event_count": external_event_count,
                },
            }

            matched_cluster_ids.append(str(cluster.get("cluster_id", "")))
            if not best_candidate:
                best_candidate = candidate
                continue

            current_score = float(best_candidate.get("risk_score", 0))
            if candidate["risk_score"] > current_score:
                best_candidate = candidate

        if not best_candidate:
            continue

        details = {
            "sentinel_id": sentinel_id,
            "sentinel_name": sentinel_name,
            "alert_level": best_candidate["alert_level"],
            "risk_score": best_candidate["risk_score"],
            "trigger_reasons": best_candidate["trigger_reasons"],
            "evidence_links": best_candidate["evidence_links"],
            "suggested_action": best_candidate["suggested_action"],
            "next_review_time": best_candidate["next_review_time"],
            "related_entities": best_candidate["entities"],
            "matched_cluster_count": len([cid for cid in matched_cluster_ids if cid]),
            "source_stats": best_candidate["source_stats"],
            "external_query": watchlist_external.get(sentinel_id, {}),
        }
        signal_key = f"{sentinel_id}:{best_candidate.get('cluster_id')}"
        signal = {
            "signal_id": generate_dedupe_key("watchlist_alert", signal_key, hour_bucket),
            "signal_type": "watchlist_alert",
            "name": f"{sentinel_name} {best_candidate['alert_level']}",
            "confidence": best_candidate["confidence"],
            "description": (
                f"{sentinel_name} 告警等级 {best_candidate['alert_level']}，"
                f"风险分 {best_candidate['risk_score']:.2f}"
            ),
            "cluster_id": best_candidate["cluster_id"],
            "affected_clusters": best_candidate["affected_clusters"],
            "category": best_candidate["category"],
            "details": details,
            "data_source": "watchlist_rule_engine",
            "sentinel_id": sentinel_id,
            "alert_level": best_candidate["alert_level"],
            "risk_score": best_candidate["risk_score"],
            "trigger_reasons": best_candidate["trigger_reasons"],
            "evidence_links": best_candidate["evidence_links"],
            "suggested_action": best_candidate["suggested_action"],
            "next_review_time": best_candidate["next_review_time"],
            "related_entities": best_candidate["entities"],
            "expires_at": (now + timedelta(hours=SIGNAL_COOLDOWN_HOURS)).isoformat(),
            "created_at": now.isoformat(),
        }
        results.append(signal)

    results.sort(key=lambda item: float(item.get("risk_score", 0) or 0), reverse=True)
    return results


def detect_all_signals(clusters: List[Dict]) -> List[Dict]:
    """
    检测所有类型的信号

    Args:
        clusters: 聚类列表

    Returns:
        合并后的信号列表
    """
    all_signals = []

    # 检测各类信号
    all_signals.extend(detect_velocity_spike(clusters))
    all_signals.extend(detect_convergence(clusters))
    all_signals.extend(detect_triangulation(clusters))
    all_signals.extend(detect_hotspot_escalation(clusters))

    # 按置信度排序
    all_signals.sort(key=lambda x: x["confidence"], reverse=True)

    return all_signals


# 测试代码
if __name__ == "__main__":
    print("=" * 60)
    print("测试信号检测器")
    print("=" * 60)

    # 测试数据
    test_clusters = [
        {
            "cluster_id": "abc123",
            "primary_title": "Fed Raises Interest Rates by 0.25% to Combat Inflation",
            "article_count": 5,
            "category": "economy",
            "sources": [
                "reuters.com",
                "bloomberg.com",
                "ft.com",
                "wsj.com",
                "nytimes.com",
            ],
        },
        {
            "cluster_id": "def456",
            "primary_title": "Pentagon Announces New Defense Strategy Against China",
            "article_count": 3,
            "category": "military",
            "sources": ["defense.gov", "reuters.com", "rand.org"],
        },
        {
            "cluster_id": "ghi789",
            "primary_title": "Congress Passes New Tax Legislation",
            "article_count": 2,
            "category": "politics",
            "sources": ["nytimes.com", "washingtonpost.com"],
        },
    ]

    print("\n1. 测试来源分类:")
    test_urls = [
        "https://www.reuters.com/news/article",
        "https://www.defense.gov/news/",
        "https://www.rand.org/pubs/",
        "https://www.nytimes.com/article",
    ]
    for url in test_urls:
        source_type = classify_source(url)
        print(f"  {url[:40]:40} -> {source_type}")

    print("\n2. 检测速度激增:")
    signals = detect_velocity_spike(test_clusters)
    print(f"  检测到 {len(signals)} 个速度激增信号")

    print("\n3. 检测来源汇聚:")
    signals = detect_convergence(test_clusters)
    print(f"  检测到 {len(signals)} 个来源汇聚信号")
    for s in signals:
        print(
            f"    - {s['name']}: {s['description'][:60]}... (置信度: {s['confidence']:.2f})"
        )

    print("\n4. 检测三角验证:")
    signals = detect_triangulation(test_clusters)
    print(f"  检测到 {len(signals)} 个三角验证信号")
    for s in signals:
        print(
            f"    - {s['name']}: {s['description'][:60]}... (置信度: {s['confidence']:.2f})"
        )

    print("\n5. 检测热点升级:")
    signals = detect_hotspot_escalation(test_clusters)
    print(f"  检测到 {len(signals)} 个热点升级信号")
    for s in signals:
        print(
            f"    - {s['name']}: {s['details']['escalation_level']} (置信度: {s['confidence']:.2f})"
        )

    print("\n6. 检测所有信号:")
    all_signals = detect_all_signals(test_clusters)
    print(f"  总共检测到 {len(all_signals)} 个信号")

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)
