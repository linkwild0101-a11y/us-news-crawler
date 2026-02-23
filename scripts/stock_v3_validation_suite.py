#!/usr/bin/env python3
"""Stock V3 验证套件（迁移幂等检查 + 压测 + 回放一致性）。"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.stock_champion_challenger_v3 import _build_scorecards
from scripts.stock_portfolio_constraints_v3 import ConstraintConfig, apply_constraints_to_opportunities

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


def _synthetic_rows(size: int, seed: int = 7) -> List[Dict[str, Any]]:
    random.seed(seed + size)
    rows: List[Dict[str, Any]] = []
    sides = ["LONG", "SHORT"]
    horizons = ["A", "B"]
    risk_levels = ["L1", "L2", "L3", "L4"]
    for idx in range(size):
        side = random.choice(sides)
        ticker = f"T{idx % 120:03d}"
        rows.append(
            {
                "id": idx + 1,
                "ticker": ticker,
                "side": side,
                "horizon": random.choice(horizons),
                "risk_level": random.choice(risk_levels),
                "opportunity_score": round(random.uniform(45, 95), 4),
                "confidence": round(random.uniform(0.4, 0.95), 6),
                "catalysts": ["earnings x1", "macro x1"] if idx % 3 == 0 else ["flow x1"],
                "source_signal_ids": [idx, idx + 1, idx + 2] if idx % 5 == 0 else [idx],
                "as_of": "2026-02-23T00:00:00+00:00",
            }
        )
    return rows


def _check_migration_idempotence(sql_dir: Path) -> Dict[str, Any]:
    files = sorted(sql_dir.glob("2026-02-2*_stock_v3*.sql"))
    invalid: List[str] = []
    for file in files:
        text = file.read_text(encoding="utf-8")
        required_tokens = ["CREATE TABLE IF NOT EXISTS", "ENABLE ROW LEVEL SECURITY"]
        if not all(token in text for token in required_tokens):
            invalid.append(str(file))
    return {
        "files_checked": len(files),
        "invalid_files": invalid,
        "ok": len(invalid) == 0,
    }


def _run_stress_benchmark() -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for size in (1000, 5000, 10000):
        rows = _synthetic_rows(size=size)
        open_positions = [
            {"ticker": "T000", "side": "LONG", "size": 1},
            {"ticker": "T001", "side": "SHORT", "size": 1},
        ]
        started = time.perf_counter()
        _build_scorecards(
            rows=rows,
            run_id=f"bench-{size}",
            promote_margin=0.03,
            champion_model="v2_rule",
            challenger_model="v3_alt",
        )
        cc_cost_ms = round((time.perf_counter() - started) * 1000, 2)

        started = time.perf_counter()
        apply_constraints_to_opportunities(
            opportunities=rows,
            open_positions=open_positions,
            config=ConstraintConfig(
                max_positions=20,
                max_new_positions=12,
                max_single_ticker=1,
                max_gross_exposure=20,
                max_long_ratio=0.75,
                max_short_ratio=0.75,
                min_opportunity_score=65,
                min_confidence=0.5,
            ),
        )
        constraint_cost_ms = round((time.perf_counter() - started) * 1000, 2)
        result[f"size_{size}"] = {
            "cc_cost_ms": cc_cost_ms,
            "constraint_cost_ms": constraint_cost_ms,
        }
    return result


def _run_replay_consistency() -> Dict[str, Any]:
    rows = _synthetic_rows(size=1200, seed=42)
    first_rows, first_metrics = _build_scorecards(
        rows=rows,
        run_id="replay-1",
        promote_margin=0.03,
        champion_model="v2_rule",
        challenger_model="v3_alt",
    )
    second_rows, second_metrics = _build_scorecards(
        rows=rows,
        run_id="replay-2",
        promote_margin=0.03,
        champion_model="v2_rule",
        challenger_model="v3_alt",
    )

    def normalize(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized = []
        for row in items:
            normalized.append(
                {
                    "opportunity_id": row.get("opportunity_id"),
                    "winner": row.get("winner"),
                    "score_delta": row.get("score_delta"),
                    "promote_candidate": row.get("promote_candidate"),
                }
            )
        return normalized

    stable = normalize(first_rows) == normalize(second_rows) and first_metrics == second_metrics
    return {
        "stable": stable,
        "rows": len(first_rows),
    }


def _write_report(output: Path, payload: Dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Stock V3 Validation Suite Report",
        "",
        f"- generated_at: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        "",
        "```json",
        json.dumps(payload, ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    output.write_text("\n".join(lines), encoding="utf-8")


def run_suite(output: str) -> Dict[str, Any]:
    migration = _check_migration_idempotence(sql_dir=Path("sql"))
    stress = _run_stress_benchmark()
    replay = _run_replay_consistency()
    summary = {
        "migration": migration,
        "stress": stress,
        "replay": replay,
    }
    _write_report(output=Path(output), payload=summary)
    logger.info("[VALIDATION_V3_DONE] " + json.dumps(summary, ensure_ascii=False))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock V3 validation suite")
    parser.add_argument(
        "--output",
        type=str,
        default="docs/reports/stock_v3_validation_report.md",
        help="验证报告输出路径",
    )
    args = parser.parse_args()
    run_suite(output=args.output.strip() or "docs/reports/stock_v3_validation_report.md")


if __name__ == "__main__":
    main()
