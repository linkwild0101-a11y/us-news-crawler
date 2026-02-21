#!/usr/bin/env python3
"""Stock V2 全量回填入口脚本。"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.stock_pipeline_v2 import StockPipelineV2

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def run_backfill(
    batch_size: int,
    max_articles: Optional[int],
    lookback_hours: int,
    enable_llm: bool,
    llm_event_cap: int,
) -> Dict[str, Any]:
    """执行 Stock V2 历史回填。"""
    engine = StockPipelineV2(enable_llm=enable_llm)
    return engine.run_backfill(
        batch_size=batch_size,
        max_articles=max_articles,
        llm_event_cap=llm_event_cap,
        lookback_hours=lookback_hours,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock V2 全量回填")
    parser.add_argument("--batch-size", type=int, default=500, help="每批文章数量")
    parser.add_argument("--max-articles", type=int, default=None, help="最多回填文章数")
    parser.add_argument("--lookback-hours", type=int, default=336, help="聚合回看小时")
    parser.add_argument("--enable-llm", action="store_true", help="启用 LLM 修正")
    parser.add_argument("--llm-event-cap", type=int, default=0, help="本轮最多 LLM 事件数")
    args = parser.parse_args()

    metrics = run_backfill(
        batch_size=args.batch_size,
        max_articles=args.max_articles,
        lookback_hours=args.lookback_hours,
        enable_llm=args.enable_llm,
        llm_event_cap=args.llm_event_cap,
    )
    logger.info("[STOCK_V2_BACKFILL_METRICS] " + ", ".join([f"{k}={v}" for k, v in metrics.items()]))


if __name__ == "__main__":
    main()
