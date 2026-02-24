#!/usr/bin/env python3
"""导出独立信号源清单（JSON + Markdown）。"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.independent_signal_config import INDEPENDENT_SIGNAL_CONFIG
from scripts.datasources.independent_signal_sources import get_independent_signal_catalog

ROOT = Path(__file__).resolve().parents[1]
JSON_OUTPUT = ROOT / "data" / "independent_signal_sources.json"
MD_OUTPUT = ROOT / "docs" / "independent_signal_sources.md"


def _split_by_tier(catalog: List[Dict[str, object]]) -> Dict[str, List[Dict[str, object]]]:
    tiers = {"priority": [], "second": [], "defer": []}
    for row in catalog:
        tier = str(row.get("tier", "defer"))
        tiers.setdefault(tier, []).append(row)
    return tiers


def _build_markdown(catalog: List[Dict[str, object]]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tiers = _split_by_tier(catalog)

    lines: List[str] = []
    lines.append("# 独立信号源清单")
    lines.append("")
    lines.append(f"- 生成时间: {now}")
    lines.append(
        "- 默认启用层级: "
        + ", ".join(INDEPENDENT_SIGNAL_CONFIG.get("enabled_tiers", []))
    )
    lines.append(f"- 总数: {len(catalog)}")
    lines.append("")

    sections = [
        ("priority", "优先接入"),
        ("second", "第二批接入"),
        ("defer", "延后接入"),
    ]

    for tier_key, title in sections:
        rows = tiers.get(tier_key, [])
        lines.append(f"## {title} ({len(rows)})")
        lines.append("")
        lines.append("| key | endpoint | signal_focus | 备注 |")
        lines.append("| --- | --- | --- | --- |")
        for row in rows:
            note = str(row.get("independent_note", "")).replace("|", "\\|")
            lines.append(
                "| "
                + f"{row.get('key', '')} | {row.get('endpoint', '')} | "
                + f"{row.get('signal_focus', '')} | {note} |"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    catalog = get_independent_signal_catalog()
    payload = {
        "generated_at": datetime.now().isoformat(),
        "default_enabled_tiers": list(
            INDEPENDENT_SIGNAL_CONFIG.get("enabled_tiers", ["priority", "second"])
        ),
        "sources": catalog,
    }

    JSON_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    MD_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    JSON_OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    MD_OUTPUT.write_text(_build_markdown(catalog), encoding="utf-8")

    print(f"导出完成: {JSON_OUTPUT}")
    print(f"导出完成: {MD_OUTPUT}")


if __name__ == "__main__":
    main()
