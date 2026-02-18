#!/usr/bin/env python3
"""
信号解释增强器
独立补充 analysis_signals 的 LLM 解释，避免阻塞主分析流程
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.analyzer import HotspotAnalyzer

logger = logging.getLogger(__name__)


def main():
    """主函数"""
    logger.warning(
        "signal_explainer.py 已整合进 analyzer.py，建议改用: "
        "python3 scripts/analyzer.py --enrich-signals-only"
    )
    parser = argparse.ArgumentParser(description="US-Monitor 信号解释增强器")
    parser.add_argument("--hours", type=int, default=24, help="回看时间窗口（小时）")
    parser.add_argument("--limit", type=int, default=30, help="本次最多增强的信号数量")
    parser.add_argument("--workers", type=int, default=3, help="并发解释 worker 数")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("开始异步信号解释增强")
    logger.info(
        f"参数: hours={args.hours}, limit={args.limit}, workers={args.workers}"
    )
    logger.info("=" * 60)

    analyzer = HotspotAnalyzer()
    updated = analyzer.enrich_pending_signal_rationales(
        hours=args.hours,
        limit=args.limit,
        max_workers=args.workers,
    )

    logger.info("=" * 60)
    logger.info(f"信号解释增强完成: 更新 {updated} 条")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
