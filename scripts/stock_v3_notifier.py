#!/usr/bin/env python3
"""Stock V3 飞书通知脚本（运行摘要 + 异常告警）。"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import request

from supabase import create_client

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

DEFAULT_STATE_FILE = Path("data/stock_v3_notifier_state.json")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _init_supabase():
    # 本地存在 SOCKS 代理配置时会导致 supabase/httpx 初始化失败，这里显式清理。
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        os.environ.pop(key, None)
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("缺少 SUPABASE_URL / SUPABASE_KEY")
    return create_client(url, key)


def _load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return payload if isinstance(payload, dict) else default


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _post_feishu(webhook_url: str, payload: Dict[str, Any]) -> Tuple[bool, str]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=12) as resp:
            content = resp.read().decode("utf-8")
        if resp.status >= 400:
            return False, f"HTTP {resp.status}: {content[:120]}"
        return True, content[:120]
    except Exception as e:
        return False, str(e)[:160]


def _build_text_payload(lines: List[str]) -> Dict[str, Any]:
    return {
        "msg_type": "text",
        "content": {"text": "\n".join(lines)},
    }


def _count_rows(supabase, table: str, **filters: Any) -> int:
    query = supabase.table(table).select("id", count="exact")
    for key, value in filters.items():
        query = query.eq(key, value)
    result = query.limit(1).execute()
    return int(result.count or 0)


def _load_snapshot(supabase) -> Dict[str, Any]:
    result = (
        supabase.table("stock_dashboard_snapshot_v2")
        .select("snapshot_time,run_id,risk_badge")
        .eq("is_active", True)
        .order("snapshot_time", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    return result.data or {}


def _load_source_health_summary(supabase) -> Dict[str, Any]:
    today = _now_utc().date().isoformat()
    rows = (
        supabase.table("source_health_daily")
        .select("source_id,status")
        .eq("health_date", today)
        .order("as_of", desc=True)
        .limit(30)
        .execute()
        .data
        or []
    )
    latest_by_source: Dict[str, str] = {}
    for row in rows:
        source_id = str(row.get("source_id") or "")
        status = str(row.get("status") or "healthy")
        if source_id and source_id not in latest_by_source:
            latest_by_source[source_id] = status

    healthy = sum(1 for status in latest_by_source.values() if status == "healthy")
    degraded = sum(1 for status in latest_by_source.values() if status == "degraded")
    critical = sum(1 for status in latest_by_source.values() if status == "critical")

    critical_sources = [sid for sid, status in latest_by_source.items() if status == "critical"]
    return {
        "date": today,
        "healthy": healthy,
        "degraded": degraded,
        "critical": critical,
        "critical_sources": critical_sources,
    }


def _load_latest_paper_metrics(supabase) -> Dict[str, Any]:
    try:
        row = (
            supabase.table("portfolio_paper_metrics")
            .select(
                "run_id,as_of,open_count,closed_count,realized_pnl,unrealized_pnl,"
                "win_rate,gross_exposure"
            )
            .order("as_of", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
            .data
            or {}
        )
        return row
    except Exception:
        return {}


def _load_latest_eval_metrics(supabase) -> Dict[str, Any]:
    try:
        rows = (
            supabase.table("signal_eval_snapshots")
            .select("hit_flag,realized_return")
            .order("as_of", desc=True)
            .limit(300)
            .execute()
            .data
            or []
        )
    except Exception:
        return {}

    if not rows:
        return {}
    total = len(rows)
    hit = sum(1 for row in rows if bool(row.get("hit_flag")))
    avg_return = sum(float(row.get("realized_return") or 0.0) for row in rows) / max(1, total)
    return {
        "eval_total": total,
        "eval_hit_rate_proxy": round(hit / total, 4),
        "eval_avg_return_proxy": round(avg_return, 6),
    }


def _load_latest_drift_metrics(supabase) -> Dict[str, Any]:
    try:
        rows = (
            supabase.table("signal_drift_snapshots")
            .select("run_id,metric_name,status,drift_value,as_of")
            .order("as_of", desc=True)
            .limit(24)
            .execute()
            .data
            or []
        )
    except Exception:
        return {}
    if not rows:
        return {}

    newest_run_id = str(rows[0].get("run_id") or "")
    scoped = [row for row in rows if str(row.get("run_id") or "") == newest_run_id]
    warn_count = sum(1 for row in scoped if str(row.get("status") or "") == "warn")
    critical_count = sum(1 for row in scoped if str(row.get("status") or "") == "critical")
    max_drift = 0.0
    for row in scoped:
        try:
            max_drift = max(max_drift, float(row.get("drift_value") or 0.0))
        except Exception:
            pass

    overall = "normal"
    if critical_count > 0:
        overall = "critical"
    elif warn_count > 0:
        overall = "warn"
    return {
        "drift_run_id": newest_run_id,
        "drift_overall_status": overall,
        "drift_warn_count": warn_count,
        "drift_critical_count": critical_count,
        "drift_max_abs": round(max_drift, 6),
    }


def _load_latest_champion_summary(supabase) -> Dict[str, Any]:
    try:
        rows = (
            supabase.table("signal_model_scorecards")
            .select("run_id,winner,promote_candidate,score_delta,as_of")
            .order("as_of", desc=True)
            .limit(400)
            .execute()
            .data
            or []
        )
    except Exception:
        return {}
    if not rows:
        return {}

    newest_run_id = str(rows[0].get("run_id") or "")
    scoped = [row for row in rows if str(row.get("run_id") or "") == newest_run_id]
    total = len(scoped)
    challenger_win = sum(1 for row in scoped if str(row.get("winner") or "") == "challenger")
    promote_count = sum(1 for row in scoped if bool(row.get("promote_candidate")))
    avg_delta = 0.0
    if total > 0:
        avg_delta = sum(float(row.get("score_delta") or 0.0) for row in scoped) / total
    return {
        "cc_run_id": newest_run_id,
        "cc_total": total,
        "cc_challenger_win": challenger_win,
        "cc_promote_candidate": promote_count,
        "cc_avg_delta": round(avg_delta, 4),
    }


def _load_latest_lifecycle_summary(supabase) -> Dict[str, Any]:
    try:
        row = (
            supabase.table("opportunity_lifecycle_snapshots")
            .select(
                "run_id,snapshot_date,generated_count,active_count,long_count,short_count,"
                "expiring_24h_count,expired_24h_count,paper_closed_24h_count,paper_win_rate_24h"
            )
            .order("as_of", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
            .data
            or {}
        )
        return row
    except Exception:
        return {}


def _load_subscription_summary(supabase) -> Dict[str, Any]:
    cutoff = (_now_utc() - timedelta(hours=24)).isoformat()
    try:
        rows = (
            supabase.table("stock_alert_delivery_logs")
            .select("status,sent_at")
            .gte("sent_at", cutoff)
            .order("sent_at", desc=True)
            .limit(500)
            .execute()
            .data
            or []
        )
    except Exception:
        return {}
    if not rows:
        return {}
    sent = sum(1 for row in rows if str(row.get("status") or "") == "sent")
    failed = sum(1 for row in rows if str(row.get("status") or "") == "failed")
    skipped = sum(1 for row in rows if str(row.get("status") or "") == "skipped")
    return {
        "sub_sent_24h": sent,
        "sub_failed_24h": failed,
        "sub_skipped_24h": skipped,
    }


def _should_send(state: Dict[str, Any], key: str) -> bool:
    sent = state.setdefault("events", {})
    if key in sent:
        return False
    sent[key] = {"sent_at": _now_utc().isoformat()}
    return True


def send_run_notification(
    run_id: str,
    job_status: str,
    dry_run: bool,
    state_file: Path,
) -> Dict[str, Any]:
    supabase = _init_supabase()
    webhook_url = os.getenv("FEISHU_WEBHOOK_URL", "").strip()
    if not webhook_url and not dry_run:
        logger.info("[V3_NOTIFY_SKIP] 缺少 FEISHU_WEBHOOK_URL")
        return {"sent": 0, "skipped": 1, "reason": "missing_webhook"}

    state = _load_json(state_file, {"events": {}})
    event_key = f"run:{run_id}:{job_status}"
    if not _should_send(state, event_key):
        logger.info(f"[V3_NOTIFY_SKIP] duplicated event={event_key}")
        return {"sent": 0, "skipped": 1, "reason": "duplicate"}

    snapshot = _load_snapshot(supabase)
    signals_total = _count_rows(supabase, "stock_signals_v2", is_active=True)
    opp_total = _count_rows(supabase, "stock_opportunities_v2", is_active=True)
    long_total = _count_rows(supabase, "stock_opportunities_v2", is_active=True, side="LONG")
    short_total = _count_rows(supabase, "stock_opportunities_v2", is_active=True, side="SHORT")
    health = _load_source_health_summary(supabase)
    paper = _load_latest_paper_metrics(supabase)
    eval_metrics = _load_latest_eval_metrics(supabase)
    drift_metrics = _load_latest_drift_metrics(supabase)
    cc_metrics = _load_latest_champion_summary(supabase)
    lifecycle = _load_latest_lifecycle_summary(supabase)
    sub_metrics = _load_subscription_summary(supabase)

    lines = [f"【Stock V3运行通知】run_id={run_id}"]
    if job_status.lower() != "success":
        lines.append(f"状态: {job_status.upper()}（请检查 Actions 日志）")
    else:
        lines.append("状态: SUCCESS")
    lines.append(
        f"看板: signals={signals_total}, opps={opp_total}, LONG/SHORT={long_total}/{short_total}, "
        f"risk={snapshot.get('risk_badge') or '-'}"
    )
    lines.append(
        f"source_health[{health['date']}]: H/D/C="
        f"{health['healthy']}/{health['degraded']}/{health['critical']}"
    )
    if health.get("critical_sources"):
        lines.append("critical源: " + ", ".join(health.get("critical_sources")[:5]))

    if eval_metrics:
        lines.append(
            f"eval_proxy: hit_rate={eval_metrics.get('eval_hit_rate_proxy')}, "
            f"avg_return={eval_metrics.get('eval_avg_return_proxy')}, "
            f"samples={eval_metrics.get('eval_total')}"
        )

    if paper:
        lines.append(
            f"paper: open={paper.get('open_count', 0)}, closed={paper.get('closed_count', 0)}, "
            f"realized={paper.get('realized_pnl', 0)}, "
            f"unrealized={paper.get('unrealized_pnl', 0)}, "
            f"win_rate={paper.get('win_rate', 0)}"
        )

    if drift_metrics:
        lines.append(
            f"drift: status={drift_metrics.get('drift_overall_status')}, "
            f"warn/critical={drift_metrics.get('drift_warn_count')}/"
            f"{drift_metrics.get('drift_critical_count')}, "
            f"max_abs={drift_metrics.get('drift_max_abs')}"
        )

    if cc_metrics:
        lines.append(
            f"champion_vs_challenger: winner={cc_metrics.get('cc_challenger_win')}/"
            f"{cc_metrics.get('cc_total')} challenger, "
            f"promote={cc_metrics.get('cc_promote_candidate')}, "
            f"avg_delta={cc_metrics.get('cc_avg_delta')}"
        )

    if lifecycle:
        lines.append(
            f"lifecycle: active={lifecycle.get('active_count', 0)}, "
            f"generated={lifecycle.get('generated_count', 0)}, "
            f"expiring24h={lifecycle.get('expiring_24h_count', 0)}, "
            f"expired24h={lifecycle.get('expired_24h_count', 0)}"
        )

    if sub_metrics:
        lines.append(
            f"subscription_24h: sent/failed/skipped={sub_metrics.get('sub_sent_24h', 0)}/"
            f"{sub_metrics.get('sub_failed_24h', 0)}/{sub_metrics.get('sub_skipped_24h', 0)}"
        )

    payload = _build_text_payload(lines)
    if dry_run:
        logger.info("[V3_NOTIFY_DRY_RUN] " + " | ".join(lines))
        _save_json(state_file, state)
        return {"sent": 0, "skipped": 0, "dry_run": 1}

    ok, resp = _post_feishu(webhook_url=webhook_url, payload=payload)
    if ok:
        _save_json(state_file, state)
        logger.info(f"[V3_NOTIFY_SENT] event={event_key}")
        return {"sent": 1, "skipped": 0, "failed": 0}

    logger.warning(f"[V3_NOTIFY_FAIL] event={event_key} error={resp}")
    return {"sent": 0, "skipped": 0, "failed": 1}


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock V3 Feishu notifier")
    parser.add_argument("--run-id", type=str, required=True, help="当前 workflow run_id")
    parser.add_argument("--job-status", type=str, default="unknown", help="job 状态")
    parser.add_argument("--dry-run", action="store_true", help="试运行，不发请求")
    parser.add_argument(
        "--state-file",
        type=str,
        default=str(DEFAULT_STATE_FILE),
        help="通知状态文件路径",
    )
    args = parser.parse_args()

    metrics = send_run_notification(
        run_id=args.run_id,
        job_status=args.job_status,
        dry_run=bool(args.dry_run),
        state_file=Path(args.state_file),
    )
    logger.info("[V3_NOTIFY_METRICS] " + ", ".join([f"{k}={v}" for k, v in metrics.items()]))


if __name__ == "__main__":
    main()
