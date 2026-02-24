#!/usr/bin/env python3
"""
RSS验证报告对比工具
对比本地和GitHub Actions的验证结果
"""

import json
import sys
from collections import Counter
from datetime import datetime


def load_report(filepath):
    """加载验证报告"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ 无法加载报告 {filepath}: {e}")
        return None


def compare_reports(local_report, github_report):
    """对比两份报告"""
    print("=" * 80)
    print("📊 RSS验证报告对比分析")
    print("=" * 80)
    print()

    # 基本信息
    print("📋 基本信息:")
    print(f"  本地报告时间: {local_report.get('timestamp', 'N/A')}")
    print(f"  GitHub报告时间: {github_report.get('timestamp', 'N/A')}")
    print()

    # 总体统计对比
    print("📈 总体统计对比:")
    print("-" * 80)
    print(f"{'指标':<20} {'本地':<15} {'GitHub':<15} {'差异':<15}")
    print("-" * 80)

    local_stats = local_report["stats"]
    github_stats = github_report["stats"]

    metrics = [
        ("总源数", "total"),
        ("可用源", "working"),
        ("不可用源", "failed"),
    ]

    for label, key in metrics:
        local_val = local_stats.get(key, 0)
        github_val = github_stats.get(key, 0)
        diff = local_val - github_val
        diff_str = f"{diff:+,}"
        print(f"{label:<20} {local_val:<15} {github_val:<15} {diff_str:<15}")

    # 可用率对比
    local_rate = (
        local_stats["working"] / local_stats["total"] * 100
        if local_stats["total"] > 0
        else 0
    )
    github_rate = (
        github_stats["working"] / github_stats["total"] * 100
        if github_stats["total"] > 0
        else 0
    )
    rate_diff = local_rate - github_rate
    print(
        f"{'可用率':<20} {local_rate:>14.1f}% {github_rate:>14.1f}% {rate_diff:>+14.1f}%"
    )
    print()

    # 按分类对比
    print("📊 按分类对比:")
    print("-" * 80)
    print(f"{'分类':<15} {'本地可用':<12} {'GitHub可用':<12} {'差异':<12}")
    print("-" * 80)

    local_cats = local_stats.get("by_category", {})
    github_cats = github_stats.get("by_category", {})
    all_cats = set(local_cats.keys()) | set(github_cats.keys())

    for cat in sorted(all_cats):
        local_working = local_cats.get(cat, {}).get("working", 0)
        local_total = local_cats.get(cat, {}).get("total", 0)
        github_working = github_cats.get(cat, {}).get("working", 0)
        github_total = github_cats.get(cat, {}).get("total", 0)

        diff = local_working - github_working
        diff_str = f"{diff:+,}"

        print(
            f"{cat:<15} {local_working:>5}/{local_total:<6} {github_working:>5}/{github_total:<6} {diff_str:<12}"
        )
    print()

    # 差异源分析
    print("🔍 差异源分析:")
    print("-" * 80)

    # 只在本地可用的源
    local_working = {
        r["rss_url"] for r in local_report["results"] if r["status"] == "working"
    }
    github_working = {
        r["rss_url"] for r in github_report["results"] if r["status"] == "working"
    }

    only_local = local_working - github_working
    only_github = github_working - local_working

    if only_local:
        print(f"✅ 只在本地可用的源 ({len(only_local)}个):")
        for result in local_report["results"]:
            if result["rss_url"] in only_local:
                print(f"   - {result['name'][:50]}")
        print()

    if only_github:
        print(f"✅ 只在GitHub可用的源 ({len(only_github)}个):")
        for result in github_report["results"]:
            if result["rss_url"] in only_github:
                print(f"   - {result['name'][:50]}")
        print()

    # 错误类型对比
    print("⚠️  错误类型对比:")
    print("-" * 80)

    local_errors = Counter(
        r["status"] for r in local_report["results"] if r["status"] != "working"
    )
    github_errors = Counter(
        r["status"] for r in github_report["results"] if r["status"] != "working"
    )
    all_errors = set(local_errors.keys()) | set(github_errors.keys())

    print(f"{'错误类型':<20} {'本地':<12} {'GitHub':<12} {'差异':<12}")
    print("-" * 80)
    for error_type in sorted(all_errors):
        local_count = local_errors.get(error_type, 0)
        github_count = github_errors.get(error_type, 0)
        diff = local_count - github_count
        diff_str = f"{diff:+,}"
        print(f"{error_type:<20} {local_count:<12} {github_count:<12} {diff_str:<12}")
    print()

    # 总结建议
    print("=" * 80)
    print("💡 总结与建议")
    print("=" * 80)
    print()

    if abs(rate_diff) < 5:
        print("✅ 本地和GitHub可用率接近，网络环境差异不大")
    elif rate_diff > 0:
        print("✅ 本地可用率更高，可能是代理效果更好")
    else:
        print("✅ GitHub可用率更高，美国IP对某些源更友好")

    print()
    print("📋 建议:")
    if only_github:
        print(f"  1. 有 {len(only_github)} 个源只在GitHub可用，建议优先在云端运行")
    if only_local:
        print(f"  2. 有 {len(only_local)} 个源只在本地可用，可能是代理优势")

    print("  3. 关注 timeout 错误的源，可能是临时网络问题")
    print("  4. HTTP 403 错误的源可能需要 Worker 代理")
    print("  5. 考虑维护一个稳定的源白名单（可用率 > 80% 的源）")
    print()


def main():
    if len(sys.argv) < 3:
        print("用法: python compare_reports.py <本地报告.json> <github报告.json>")
        print()
        print("示例:")
        print(
            "  python compare_reports.py rss_validation_report_local.json rss_validation_report_github.json"
        )
        sys.exit(1)

    local_file = sys.argv[1]
    github_file = sys.argv[2]

    local_report = load_report(local_file)
    github_report = load_report(github_file)

    if not local_report or not github_report:
        sys.exit(1)

    compare_reports(local_report, github_report)


if __name__ == "__main__":
    main()
