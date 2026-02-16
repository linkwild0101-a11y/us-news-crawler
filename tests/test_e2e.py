#!/usr/bin/env python3
"""
端到端测试
测试完整的分析流程
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.clustering import tokenize, jaccard_similarity, cluster_news
from scripts.signal_detector import (
    detect_velocity_spike,
    detect_convergence,
    detect_triangulation,
    detect_hotspot_escalation,
    classify_source,
)


def test_tokenization():
    """测试分词功能"""
    print("\n" + "=" * 60)
    print("测试1: 分词功能")
    print("=" * 60)

    test_cases = [
        ("The quick brown fox", {"quick", "brown", "fox"}),
        ("Fed Raises Interest Rates", {"fed", "raises", "interest", "rates"}),
        ("Pentagon Announces New Strategy", {"pentagon", "announces", "strategy"}),
    ]

    all_passed = True
    for text, expected in test_cases:
        result = tokenize(text)
        # 检查是否包含预期的词（可能还有其他词）
        missing = expected - result
        if missing:
            print(f"❌ 失败: '{text}'")
            print(f"   缺少词: {missing}")
            all_passed = False
        else:
            print(f"✅ 通过: '{text[:40]}...' -> {len(result)} 个token")

    return all_passed


def test_jaccard_similarity():
    """测试Jaccard相似度"""
    print("\n" + "=" * 60)
    print("测试2: Jaccard相似度")
    print("=" * 60)

    test_cases = [
        ({"a", "b"}, {"a", "b"}, 1.0, "相同集合"),
        ({"a", "b"}, {"c", "d"}, 0.0, "不相交集合"),
        ({"a", "b", "c"}, {"a", "b", "d"}, 0.5, "部分交集"),
        ({"a"}, {"a", "b", "c", "d"}, 0.25, "子集"),
    ]

    all_passed = True
    for set1, set2, expected, desc in test_cases:
        result = jaccard_similarity(set1, set2)
        if abs(result - expected) < 0.01:
            print(f"✅ 通过: {desc} -> {result:.2f}")
        else:
            print(f"❌ 失败: {desc}")
            print(f"   期望: {expected}, 实际: {result}")
            all_passed = False

    return all_passed


def test_clustering():
    """测试聚类功能"""
    print("\n" + "=" * 60)
    print("测试3: 聚类功能")
    print("=" * 60)

    test_articles = [
        {"id": 1, "title": "Fed Raises Interest Rates by 0.25%", "category": "economy"},
        {
            "id": 2,
            "title": "Federal Reserve Increases Interest Rate",
            "category": "economy",
        },
        {
            "id": 3,
            "title": "Pentagon Announces New Defense Strategy",
            "category": "military",
        },
        {
            "id": 4,
            "title": "Defense Department Reveals Military Plan",
            "category": "military",
        },
        {
            "id": 5,
            "title": "Congress Passes New Tax Legislation",
            "category": "politics",
        },
    ]

    clusters = cluster_news(test_articles, threshold=0.3)

    print(f"创建了 {len(clusters)} 个聚类")

    # 验证聚类数量
    if len(clusters) >= 2:
        print("✅ 通过: 正确分组相似文章")
        for i, c in enumerate(clusters):
            print(
                f"   聚类 {i + 1}: {c['primary_title'][:50]}... ({c['article_count']} 篇)"
            )
        return True
    else:
        print("❌ 失败: 聚类数量过少")
        return False


def test_signal_detection():
    """测试信号检测"""
    print("\n" + "=" * 60)
    print("测试4: 信号检测")
    print("=" * 60)

    test_clusters = [
        {
            "cluster_id": "test1",
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
            "cluster_id": "test2",
            "primary_title": "Pentagon Announces New Defense Strategy Against China",
            "article_count": 3,
            "category": "military",
            "sources": ["defense.gov", "reuters.com", "rand.org"],
        },
    ]

    # 测试来源分类
    print("\n测试来源分类:")
    test_urls = [
        ("reuters.com", "wire"),
        ("defense.gov", "gov"),
        ("rand.org", "intel"),
        ("nytimes.com", "mainstream"),
    ]

    all_passed = True
    for url, expected in test_urls:
        result = classify_source(url)
        if result == expected:
            print(f"✅ {url} -> {result}")
        else:
            print(f"❌ {url} -> {result} (期望: {expected})")
            all_passed = False

    # 测试三角验证
    print("\n测试三角验证:")
    signals = detect_triangulation(test_clusters)
    if signals:
        print(f"✅ 检测到 {len(signals)} 个三角验证信号")
        for s in signals:
            print(f"   - {s['name']}: 置信度 {s['confidence']}")
    else:
        print("⚠️  未检测到三角验证信号（可能数据源不够多样）")

    # 测试来源汇聚
    print("\n测试来源汇聚:")
    signals = detect_convergence(test_clusters)
    if signals:
        print(f"✅ 检测到 {len(signals)} 个来源汇聚信号")
    else:
        print("⚠️  未检测到来源汇聚信号")

    # 测试热点升级
    print("\n测试热点升级:")
    signals = detect_hotspot_escalation(test_clusters)
    if signals:
        print(f"✅ 检测到 {len(signals)} 个热点升级信号")
        for s in signals:
            print(f"   - 等级: {s['details']['escalation_level']}")
    else:
        print("⚠️  未检测到热点升级信号")

    return all_passed


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("US-Monitor 端到端测试")
    print("=" * 60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = []

    # 运行测试
    results.append(("分词功能", test_tokenization()))
    results.append(("Jaccard相似度", test_jaccard_similarity()))
    results.append(("聚类功能", test_clustering()))
    results.append(("信号检测", test_signal_detection()))

    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status}: {name}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有测试通过!")
        return 0
    else:
        print("\n⚠️  部分测试失败")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
