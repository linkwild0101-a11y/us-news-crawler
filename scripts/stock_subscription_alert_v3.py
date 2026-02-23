#!/usr/bin/env python3
"""Stock V3 订阅告警投递脚本（ticker/方向/等级）。"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timedelta, timezone
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

RISK_ORDER = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}


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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _load_active_subscriptions(supabase, limit: int) -> List[Dict[str, Any]]:
    rows = (
        supabase.table("stock_alert_subscriptions")
        .select(
            "id,subscription_key,subscriber,channel,feishu_webhook_url,tickers,side_filter,"
            "min_risk_level,min_opportunity_score,min_confidence,cooldown_minutes,"
            "max_items_per_run,quiet_hours_start,quiet_hours_end,is_active"
        )
        .eq("is_active", True)
        .order("updated_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    return rows


def _load_active_opportunities(supabase, limit: int) -> List[Dict[str, Any]]:
    rows = (
        supabase.table("stock_opportunities_v2")
        .select(
            "id,ticker,side,horizon,risk_level,opportunity_score,confidence,why_now,invalid_if,as_of"
        )
        .eq("is_active", True)
        .order("opportunity_score", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    return rows


def _in_quiet_hours(now: datetime, start_hour: int, end_hour: int) -> bool:
    start = int(start_hour)
    end = int(end_hour)
    if start == end:
        return False
    hour = now.hour
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def _to_tickers(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).upper().strip() for item in value if str(item).strip()]


def _filter_candidates(
    rows: List[Dict[str, Any]],
    ticker_filter: List[str],
    side_filter: str,
    min_risk_level: str,
    min_score: float,
    min_confidence: float,
) -> List[Dict[str, Any]]:
    ticker_set = set(ticker_filter)
    min_risk_rank = RISK_ORDER.get(min_risk_level.upper(), 0)
    normalized_side = side_filter.upper()
    result: List[Dict[str, Any]] = []

    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        side = str(row.get("side") or "").upper()
        risk_level = str(row.get("risk_level") or "L0").upper()
        score = _safe_float(row.get("opportunity_score"), 0.0)
        confidence = _safe_float(row.get("confidence"), 0.0)
        if not ticker:
            continue
        if ticker_set and ticker not in ticker_set:
            continue
        if normalized_side in ("LONG", "SHORT") and side != normalized_side:
            continue
        if RISK_ORDER.get(risk_level, 0) < min_risk_rank:
            continue
        if score < min_score or confidence < min_confidence:
            continue
        result.append(row)
    return result


def _was_recently_sent(supabase, subscription_id: int, opportunity_id: int, cooldown_minutes: int) -> bool:
    cutoff = (_now_utc() - timedelta(minutes=max(1, cooldown_minutes))).isoformat()
    rows = (
        supabase.table("stock_alert_delivery_logs")
        .select("id")
        .eq("subscription_id", subscription_id)
        .eq("opportunity_id", opportunity_id)
        .eq("status", "sent")
        .gte("sent_at", cutoff)
        .order("sent_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    return bool(rows)


def _build_text_payload(subscriber: str, row: Dict[str, Any]) -> Dict[str, Any]:
    lines = [
        f"【Stock V3订阅告警】{subscriber}",
        f"{row.get('ticker')} {row.get('side')} {row.get('risk_level')}"
        f" · score={round(_safe_float(row.get('opportunity_score'), 0.0), 1)}"
        f" · conf={round(_safe_float(row.get('confidence'), 0.0) * 100)}%",
        f"why_now: {str(row.get('why_now') or '')[:120]}",
        f"invalid_if: {str(row.get('invalid_if') or '')[:120]}",
        f"as_of: {row.get('as_of')}",
    ]
    return {
        "msg_type": "text",
        "content": {"text": "\n".join(lines)},
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
        with request.urlopen(req, timeout=12) as resp:
            content = resp.read().decode("utf-8")
        if resp.status >= 400:
            return False, f"HTTP {resp.status}: {content[:120]}"
        return True, content[:120]
    except Exception as e:
        return False, str(e)[:160]


def _insert_delivery_log(
    supabase,
    payload: Dict[str, Any],
) -> None:
    supabase.table("stock_alert_delivery_logs").insert(payload).execute()


def _dispatch_subscription(
    supabase,
    run_id: str,
    sub: Dict[str, Any],
    opportunities: List[Dict[str, Any]],
    default_webhook: str,
    dry_run: bool,
) -> Dict[str, int]:
    sub_id = int(sub.get("id") or 0)
    sub_key = str(sub.get("subscription_key") or f"sub-{sub_id}")
    subscriber = str(sub.get("subscriber") or sub_key)
    webhook = str(sub.get("feishu_webhook_url") or "").strip() or default_webhook
    cooldown_minutes = int(sub.get("cooldown_minutes") or 30)
    max_items = max(1, int(sub.get("max_items_per_run") or 3))
    min_risk_level = str(sub.get("min_risk_level") or "L3").upper()
    side_filter = str(sub.get("side_filter") or "ALL").upper()
    min_score = _safe_float(sub.get("min_opportunity_score"), 70.0)
    min_confidence = _safe_float(sub.get("min_confidence"), 0.55)
    start_hour = int(sub.get("quiet_hours_start") or 0)
    end_hour = int(sub.get("quiet_hours_end") or 0)
    ticker_filter = _to_tickers(sub.get("tickers"))

    metrics = {"candidate": 0, "sent": 0, "skipped": 0, "failed": 0}
    if sub_id <= 0:
        return metrics

    if _in_quiet_hours(_now_utc(), start_hour, end_hour):
        logger.info(f"[SUB_ALERT_SKIP_QUIET] subscription={sub_key}")
        return metrics

    filtered = _filter_candidates(
        rows=opportunities,
        ticker_filter=ticker_filter,
        side_filter=side_filter,
        min_risk_level=min_risk_level,
        min_score=min_score,
        min_confidence=min_confidence,
    )
    metrics["candidate"] = len(filtered)

    if not webhook and not dry_run:
        logger.warning(f"[SUB_ALERT_SKIP_WEBHOOK] subscription={sub_key}")
        metrics["skipped"] += len(filtered[:max_items])
        return metrics

    sent_any = False
    for row in filtered[:max_items]:
        opportunity_id = int(row.get("id") or 0)
        if opportunity_id <= 0:
            continue
        if _was_recently_sent(
            supabase=supabase,
            subscription_id=sub_id,
            opportunity_id=opportunity_id,
            cooldown_minutes=cooldown_minutes,
        ):
            metrics["skipped"] += 1
            continue

        delivery_key = f"{sub_id}:{opportunity_id}:{_now_utc().strftime('%Y%m%d%H%M')}"
        payload = _build_text_payload(subscriber=subscriber, row=row)
        if dry_run:
            ok = True
            response_text = "dry_run"
        else:
            ok, response_text = _post_feishu(webhook_url=webhook, payload=payload)

        log_payload = {
            "delivery_key": delivery_key,
            "subscription_id": sub_id,
            "run_id": run_id,
            "channel": "feishu",
            "ticker": str(row.get("ticker") or ""),
            "side": str(row.get("side") or "LONG"),
            "risk_level": str(row.get("risk_level") or "L1"),
            "opportunity_id": opportunity_id,
            "payload": payload,
            "status": "sent" if ok else "failed",
            "response_text": response_text,
            "sent_at": _now_utc().isoformat(),
        }
        try:
            _insert_delivery_log(supabase=supabase, payload=log_payload)
        except Exception as e:
            logger.warning(f"[SUB_ALERT_LOG_FAIL] subscription={sub_key} error={str(e)[:120]}")

        if ok:
            sent_any = True
            metrics["sent"] += 1
        else:
            metrics["failed"] += 1

    if sent_any:
        (
            supabase.table("stock_alert_subscriptions")
            .update({"last_sent_at": _now_utc().isoformat(), "as_of": _now_utc().isoformat()})
            .eq("id", sub_id)
            .execute()
        )
    return metrics


def _upsert_run_metrics(supabase, run_id: str, metrics: Dict[str, float]) -> None:
    rows = [
        {
            "run_id": run_id,
            "metric_name": key,
            "metric_value": float(value),
            "metric_unit": "count",
        }
        for key, value in metrics.items()
    ]
    if not rows:
        return
    try:
        supabase.table("research_run_metrics").upsert(rows, on_conflict="run_id,metric_name").execute()
    except Exception as e:
        logger.warning(f"[SUB_ALERT_METRICS_UPSERT_FAILED] error={str(e)[:120]}")


def _log_run_start(supabase, run_id: str, sub_limit: int, opp_limit: int) -> None:
    payload = {
        "run_id": run_id,
        "pipeline_name": "stock_v3_subscription_alert",
        "pipeline_version": os.getenv("GITHUB_SHA", "")[:12] or "local",
        "trigger_type": os.getenv("GITHUB_EVENT_NAME", "manual"),
        "status": "running",
        "started_at": _now_utc().isoformat(),
        "input_window": {"sub_limit": sub_limit, "opp_limit": opp_limit},
        "params_json": {"sub_limit": sub_limit, "opp_limit": opp_limit},
        "commit_sha": os.getenv("GITHUB_SHA", "")[:40],
        "as_of": _now_utc().isoformat(),
    }
    try:
        supabase.table("research_runs").upsert(payload, on_conflict="run_id").execute()
    except Exception as e:
        logger.warning(f"[SUB_ALERT_RUN_START_FAILED] error={str(e)[:120]}")


def _log_run_finish(supabase, run_id: str, status: str, notes: str) -> None:
    try:
        (
            supabase.table("research_runs")
            .update(
                {
                    "status": status,
                    "ended_at": _now_utc().isoformat(),
                    "notes": notes[:1000],
                    "as_of": _now_utc().isoformat(),
                }
            )
            .eq("run_id", run_id)
            .execute()
        )
    except Exception as e:
        logger.warning(f"[SUB_ALERT_RUN_FINISH_FAILED] error={str(e)[:120]}")


def run_subscription_alerts(
    run_id: Optional[str],
    sub_limit: int,
    opp_limit: int,
    dry_run: bool,
) -> Dict[str, Any]:
    supabase = _init_supabase()
    final_run_id = run_id or f"sub-alert-{_now_utc().strftime('%Y%m%d%H%M%S')}"
    default_webhook = os.getenv("FEISHU_WEBHOOK_URL", "").strip()
    _log_run_start(
        supabase=supabase,
        run_id=final_run_id,
        sub_limit=sub_limit,
        opp_limit=opp_limit,
    )

    try:
        subscriptions = _load_active_subscriptions(supabase=supabase, limit=sub_limit)
        opportunities = _load_active_opportunities(supabase=supabase, limit=opp_limit)
        aggregate = {
            "run_id": final_run_id,
            "subscriptions": len(subscriptions),
            "opportunities": len(opportunities),
            "candidate": 0,
            "sent": 0,
            "skipped": 0,
            "failed": 0,
        }

        for sub in subscriptions:
            sub_metrics = _dispatch_subscription(
                supabase=supabase,
                run_id=final_run_id,
                sub=sub,
                opportunities=opportunities,
                default_webhook=default_webhook,
                dry_run=dry_run,
            )
            aggregate["candidate"] += sub_metrics["candidate"]
            aggregate["sent"] += sub_metrics["sent"]
            aggregate["skipped"] += sub_metrics["skipped"]
            aggregate["failed"] += sub_metrics["failed"]

        _upsert_run_metrics(
            supabase=supabase,
            run_id=final_run_id,
            metrics={
                "subscription_sub_total": float(aggregate["subscriptions"]),
                "subscription_candidate_total": float(aggregate["candidate"]),
                "subscription_sent_total": float(aggregate["sent"]),
                "subscription_skipped_total": float(aggregate["skipped"]),
                "subscription_failed_total": float(aggregate["failed"]),
            },
        )
        _log_run_finish(
            supabase=supabase,
            run_id=final_run_id,
            status="success",
            notes=f"sent={aggregate['sent']}, failed={aggregate['failed']}",
        )
        logger.info("[SUB_ALERT_V3_DONE] " + ", ".join([f"{k}={v}" for k, v in aggregate.items()]))
        return aggregate
    except Exception as e:
        _log_run_finish(
            supabase=supabase,
            run_id=final_run_id,
            status="failed",
            notes=f"error={str(e)[:300]}",
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock V3 subscription alert runner")
    parser.add_argument("--run-id", type=str, default=None, help="运行 run_id")
    parser.add_argument("--sub-limit", type=int, default=60, help="最多订阅数")
    parser.add_argument("--opp-limit", type=int, default=200, help="最多机会样本")
    parser.add_argument("--dry-run", action="store_true", help="仅演练，不发送")
    args = parser.parse_args()

    summary = run_subscription_alerts(
        run_id=args.run_id,
        sub_limit=max(1, args.sub_limit),
        opp_limit=max(50, args.opp_limit),
        dry_run=bool(args.dry_run),
    )
    logger.info("[SUB_ALERT_V3_METRICS] " + ", ".join([f"{k}={v}" for k, v in summary.items()]))


if __name__ == "__main__":
    main()
