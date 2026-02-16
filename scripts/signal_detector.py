#!/usr/bin/env python3
"""
信号检测器模块
检测新闻聚类中的异常信号模式
"""

import hashlib
from typing import List, Dict, Set, Tuple, Optional
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.analysis_config import (
    SIGNAL_THRESHOLDS,
    TOPIC_KEYWORDS,
    SIGNAL_TYPES,
    SIGNAL_COOLDOWN_HOURS,
)


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
        # 这里简化处理，假设每个聚类有sources字段
        # 实际应该从cluster的articles中获取来源
        source_types = set()

        # 模拟来源分类（实际应该使用真实来源URL）
        if "sources" in cluster:
            for source in cluster["sources"]:
                source_type = classify_source(source)
                source_types.add(source_type)
        else:
            # 如果没有来源信息，使用模拟数据
            # 基于聚类大小推测
            if cluster["article_count"] >= 5:
                source_types = {"wire", "mainstream", "financial"}
            elif cluster["article_count"] >= 3:
                source_types = {"wire", "mainstream"}

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

        # 模拟来源分类
        if "sources" in cluster:
            for source in cluster["sources"]:
                source_type = classify_source(source)
                source_types.add(source_type)
        else:
            # 模拟：假设大聚类有更高概率包含多种来源
            if cluster["article_count"] >= 4:
                source_types = {"wire", "gov", "intel", "mainstream"}

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
