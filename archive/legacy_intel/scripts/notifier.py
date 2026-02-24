#!/usr/bin/env python3
"""哨兵告警通知器（飞书机器人）。"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import request

from supabase import create_client

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

ALERT_LEVEL_ORDER = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}
DEFAULT_STATE_FILE = Path("data/notifier_state.json")


def _load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return parsed if isinstance(parsed, dict) else default


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            return parsed.astimezone().replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _extract_signal_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    details = row.get("details", {})
    if not isinstance(details, dict):
        details = {}

    trigger_reasons = row.get("trigger_reasons", details.get("trigger_reasons", []))
    evidence_links = row.get("evidence_links", details.get("evidence_links", []))

    if not isinstance(trigger_reasons, list):
        trigger_reasons = []
    if not isinstance(evidence_links, list):
        evidence_links = []

    return {
        "signal_key": str(row.get("signal_key", "")),
        "sentinel_id": str(row.get("sentinel_id") or details.get("sentinel_id") or ""),
        "sentinel_name": str(details.get("sentinel_name") or row.get("description") or "场景哨兵"),
        "alert_level": str(row.get("alert_level") or details.get("alert_level") or "L1"),
        "risk_score": float(row.get("risk_score") or details.get("risk_score") or 0.0),
        "trigger_reasons": [str(item) for item in trigger_reasons if item],
        "evidence_links": [str(item) for item in evidence_links if item],
        "suggested_action": str(details.get("suggested_action") or "建议人工复核。"),
        "next_review_time": str(details.get("next_review_time") or ""),
        "created_at": str(row.get("created_at") or ""),
    }


def _build_event_key(payload: Dict[str, Any]) -> str:
    sentinel_id = payload.get("sentinel_id") or "unknown_sentinel"
    cluster_key = payload.get("signal_key") or "unknown_signal"
    return f"{sentinel_id}:{cluster_key}"


def _should_send(
    payload: Dict[str, Any],
    state: Dict[str, Any],
    cooldown_minutes: int,
) -> Tuple[bool, str]:
    event_key = _build_event_key(payload)
    level = str(payload.get("alert_level", "L1"))
    created_at = _parse_iso(str(payload.get("created_at", ""))) or datetime.now()

    events = state.setdefault("events", {})
    prev = events.get(event_key, {}) if isinstance(events.get(event_key), dict) else {}
    prev_level = str(prev.get("level", "L0"))
    prev_sent_at = _parse_iso(str(prev.get("sent_at", "")))

    if prev_sent_at is None:
        return True, "首次发送"

    level_up = ALERT_LEVEL_ORDER.get(level, 0) > ALERT_LEVEL_ORDER.get(prev_level, 0)
    if level_up:
        return True, f"等级提升 {prev_level}->{level}"

    if created_at - prev_sent_at >= timedelta(minutes=cooldown_minutes):
        return True, f"超过冷却窗口 {cooldown_minutes} 分钟"

    return False, "冷却中且无等级提升"


def _build_feishu_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    sentinel_name = payload.get("sentinel_name", "场景哨兵")
    level = payload.get("alert_level", "L1")
    risk_score = float(payload.get("risk_score", 0.0))
    trigger_reasons = payload.get("trigger_reasons", [])[:3]
    evidence_links = payload.get("evidence_links", [])[:3]
    suggested_action = payload.get("suggested_action", "建议人工复核。")
    next_review_time = payload.get("next_review_time", "")

    body_lines = [
        f"【{sentinel_name}】等级: {level}",
        f"风险分: {risk_score:.2f}",
    ]
    if trigger_reasons:
        body_lines.append("触发原因:")
        body_lines.extend([f"- {item}" for item in trigger_reasons])
    if evidence_links:
        body_lines.append("证据链接:")
        body_lines.extend([f"- {item}" for item in evidence_links])
    body_lines.append(f"建议动作: {suggested_action}")
    if next_review_time:
        body_lines.append(f"复核时间: {next_review_time}")

    return {
        "msg_type": "text",
        "content": {
            "text": "\n".join(body_lines),
        },
    }


def _post_feishu(webhook_url: str, payload: Dict[str, Any]) -> Tuple[bool, str]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode("utf-8")
        if resp.status >= 400:
            return False, f"HTTP {resp.status}: {content[:120]}"
        return True, content[:120]
    except Exception as e:
        return False, str(e)[:160]


def dispatch_watchlist_notifications(
    supabase,
    webhook_url: str,
    hours: int = 24,
    limit: int = 40,
    cooldown_minutes: int = 30,
    state_file: Path = DEFAULT_STATE_FILE,
    dry_run: bool = False,
) -> Dict[str, int]:
    """发送 L3/L4 告警通知。"""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

    try:
        rows = (
            supabase.table("analysis_signals")
            .select(
                "signal_key,sentinel_id,alert_level,risk_score,description,"
                "trigger_reasons,evidence_links,details,created_at"
            )
            .eq("signal_type", "watchlist_alert")
            .in_("alert_level", ["L3", "L4"])
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(limit * 3)
            .execute()
        )
    except Exception as e:
        logger.info(
            "[NOTIFY_SCHEMA_FALLBACK] analysis_signals 缺少 details 字段，"
            f"切换兼容查询: {str(e)[:120]}"
        )
        rows = (
            supabase.table("analysis_signals")
            .select(
                "signal_key,sentinel_id,alert_level,risk_score,description,"
                "trigger_reasons,evidence_links,created_at"
            )
            .eq("signal_type", "watchlist_alert")
            .in_("alert_level", ["L3", "L4"])
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(limit * 3)
            .execute()
        )

    state = _load_json(state_file, {"events": {}})
    metrics = {"candidate": 0, "sent": 0, "skipped": 0, "failed": 0}

    for row in rows.data or []:
        payload = _extract_signal_payload(row)
        if not payload.get("sentinel_id"):
            continue

        metrics["candidate"] += 1
        should_send, reason = _should_send(payload, state, cooldown_minutes)
        if not should_send:
            logger.info(f"[NOTIFY_SKIP] {payload['sentinel_id']} | {reason}")
            metrics["skipped"] += 1
            continue

        event_key = _build_event_key(payload)
        if dry_run:
            logger.info(f"[NOTIFY_DRY_RUN] {event_key} | {payload['alert_level']}")
            ok = True
            resp_text = "dry_run"
        else:
            feishu_payload = _build_feishu_payload(payload)
            ok, resp_text = _post_feishu(webhook_url, feishu_payload)

        if ok:
            state.setdefault("events", {})[event_key] = {
                "sent_at": datetime.now().isoformat(),
                "level": payload["alert_level"],
            }
            metrics["sent"] += 1
            logger.info(f"[NOTIFY_SENT] {event_key} | {payload['alert_level']}")
        else:
            metrics["failed"] += 1
            logger.warning(f"[NOTIFY_FAIL] {event_key} | {resp_text}")

    _save_json(state_file, state)
    return metrics


def _init_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("缺少 SUPABASE_URL / SUPABASE_KEY")
    return create_client(url, key)


def main() -> None:
    parser = argparse.ArgumentParser(description="发送哨兵 L3/L4 飞书通知")
    parser.add_argument("--hours", type=int, default=24, help="回看窗口（小时）")
    parser.add_argument("--limit", type=int, default=40, help="最多检查信号数量")
    parser.add_argument("--cooldown-minutes", type=int, default=30, help="去重冷却分钟")
    parser.add_argument("--dry-run", action="store_true", help="试运行，不发送请求")
    parser.add_argument(
        "--state-file",
        type=str,
        default=str(DEFAULT_STATE_FILE),
        help="通知状态文件路径",
    )

    args = parser.parse_args()

    webhook_url = os.getenv("FEISHU_WEBHOOK_URL", "").strip()
    if not webhook_url and not args.dry_run:
        raise ValueError("缺少 FEISHU_WEBHOOK_URL，无法发送通知")

    supabase = _init_supabase()
    metrics = dispatch_watchlist_notifications(
        supabase=supabase,
        webhook_url=webhook_url,
        hours=args.hours,
        limit=args.limit,
        cooldown_minutes=args.cooldown_minutes,
        state_file=Path(args.state_file),
        dry_run=args.dry_run,
    )
    logger.info(f"通知执行完成: {metrics}")


if __name__ == "__main__":
    main()
