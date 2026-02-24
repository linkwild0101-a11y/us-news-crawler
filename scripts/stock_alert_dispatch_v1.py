#!/usr/bin/env python3
"""StockOps P0: 告警投递与去重冷却执行器。"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from supabase import Client, create_client

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


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


class StockAlertDispatchV1:
    """将 pending alert 写入 delivery，并标记状态。"""

    def __init__(self) -> None:
        self.supabase = self._init_supabase()

    def _init_supabase(self) -> Client:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("缺少 SUPABASE_URL / SUPABASE_KEY")
        return create_client(url, key)

    def _load_pending_alerts(self, limit: int) -> List[Dict[str, Any]]:
        try:
            return (
                self.supabase.table("stock_alert_events_v1")
                .select("id,user_id,ticker,signal_type,dedupe_window,title,why_now,payload")
                .eq("is_active", True)
                .eq("status", "pending")
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
                .data
                or []
            )
        except Exception as e:
            logger.warning(f"[ALERT_DISPATCH_LOAD_FALLBACK] error={str(e)[:120]}")
            return []

    def _exists_delivery(self, dedupe_key: str) -> bool:
        try:
            row = (
                self.supabase.table("stock_alert_delivery_v1")
                .select("id")
                .eq("dedupe_key", dedupe_key)
                .limit(1)
                .maybe_single()
                .execute()
                .data
            )
            return isinstance(row, dict) and _safe_int(row.get("id"), 0) > 0
        except Exception:
            return False

    def _insert_delivery(
        self,
        alert_id: int,
        user_id: str,
        channel: str,
        dedupe_key: str,
        run_id: str,
        payload: Dict[str, Any],
        provider_message: str,
        status: str,
    ) -> bool:
        row = {
            "alert_id": alert_id,
            "user_id": user_id,
            "channel": channel,
            "dedupe_key": dedupe_key,
            "status": status,
            "provider_message": provider_message[:500],
            "payload": payload,
            "sent_at": _now_utc().isoformat(),
            "run_id": run_id,
            "as_of": _now_utc().isoformat(),
        }
        try:
            self.supabase.table("stock_alert_delivery_v1").insert(row).execute()
            return True
        except Exception as e:
            logger.warning(
                f"[ALERT_DISPATCH_INSERT_FALLBACK] alert_id={alert_id} error={str(e)[:120]}"
            )
            return False

    def _update_alert_status(self, alert_id: int, status: str) -> None:
        try:
            (
                self.supabase.table("stock_alert_events_v1")
                .update({"status": status, "as_of": _now_utc().isoformat()})
                .eq("id", alert_id)
                .execute()
            )
        except Exception as e:
            logger.warning(
                f"[ALERT_DISPATCH_STATUS_FALLBACK] alert_id={alert_id} error={str(e)[:120]}"
            )

    def run(self, run_id: str, limit: int, channel: str, dry_run: bool) -> Dict[str, Any]:
        logger.info(
            f"[STOCK_ALERT_DISPATCH_START] run_id={run_id} limit={limit} "
            f"channel={channel} dry_run={dry_run}"
        )
        rows = self._load_pending_alerts(limit=limit)
        sent = 0
        deduped = 0

        for row in rows:
            alert_id = _safe_int(row.get("id"), 0)
            if alert_id <= 0:
                continue
            user_id = str(row.get("user_id") or "system")[:64]
            ticker = str(row.get("ticker") or "")[:16]
            signal_type = str(row.get("signal_type") or "opportunity")[:32]
            dedupe_window = str(row.get("dedupe_window") or "")[:40]
            dedupe_key = f"{channel}:{user_id}:{ticker}:{signal_type}:{dedupe_window}"[:180]

            if self._exists_delivery(dedupe_key):
                deduped += 1
                if not dry_run:
                    self._update_alert_status(alert_id, "deduped")
                continue

            message = f"[{ticker}] {str(row.get('title') or '')}"
            payload = {
                "title": str(row.get("title") or "")[:220],
                "why_now": str(row.get("why_now") or "")[:500],
                "raw_payload": row.get("payload") or {},
            }

            if dry_run:
                sent += 1
                continue

            inserted = self._insert_delivery(
                alert_id=alert_id,
                user_id=user_id,
                channel=channel,
                dedupe_key=dedupe_key,
                run_id=run_id,
                payload=payload,
                provider_message=message,
                status="sent",
            )
            if inserted:
                sent += 1
                self._update_alert_status(alert_id, "sent")

        logger.info(
            f"[STOCK_ALERT_DISPATCH_DONE] run_id={run_id} pending={len(rows)} "
            f"sent={sent} deduped={deduped}"
        )
        return {
            "run_id": run_id,
            "pending": len(rows),
            "sent": sent,
            "deduped": deduped,
            "channel": channel,
            "dry_run": dry_run,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="StockOps P0 告警投递与去重")
    parser.add_argument("--run-id", type=str, default="", help="外部 run id")
    parser.add_argument("--limit", type=int, default=300, help="本轮最多处理多少条 pending")
    parser.add_argument("--channel", type=str, default="inbox", help="投递通道标识")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    args = parser.parse_args()

    run_id = args.run_id.strip() or f"alert-dispatch-{_now_utc().strftime('%Y%m%d%H%M%S')}"
    engine = StockAlertDispatchV1()
    metrics = engine.run(
        run_id=run_id,
        limit=max(1, args.limit),
        channel=args.channel.strip() or "inbox",
        dry_run=args.dry_run,
    )
    logger.info(
        "[STOCK_ALERT_DISPATCH_METRICS] "
        + ", ".join(f"{key}={value}" for key, value in metrics.items())
    )


if __name__ == "__main__":
    main()
