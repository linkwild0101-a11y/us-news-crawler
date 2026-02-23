#!/usr/bin/env python3
"""Stock X 账号质量治理与动态评分脚本。"""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Sequence

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


@dataclass
class AccountQuality:
    """账号质量快照。"""

    handle: str
    quality_score: float
    reliability_score: float
    precision_score: float
    activity_score: float
    freshness_score: float
    latency_score: float
    neutral_ratio: float
    low_conf_ratio: float
    posts_7d: int
    signals_7d: int
    status: str
    notes: str


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp(value: float, left: float, right: float) -> float:
    return max(left, min(right, value))


class StockXQualityGovernor:
    """X 源质量治理执行器。"""

    def __init__(self, lookback_days: int, run_id: str, dry_run: bool, topn: int):
        self.lookback_days = max(1, lookback_days)
        self.run_id = run_id
        self.dry_run = dry_run
        self.topn = max(1, topn)
        self.supabase = self._init_supabase()

    def _init_supabase(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("缺少 SUPABASE_URL / SUPABASE_KEY")
        return create_client(url, key)

    def _load_active_accounts(self) -> List[str]:
        rows = (
            self.supabase.table("stock_x_accounts")
            .select("handle")
            .eq("is_active", True)
            .order("priority_rank", desc=False)
            .limit(self.topn)
            .execute()
            .data
            or []
        )
        return [str(row.get("handle") or "").strip() for row in rows if str(row.get("handle") or "").strip()]

    def _load_health_rows(self, handles: Sequence[str], cutoff_date: str) -> List[Dict[str, Any]]:
        if not handles:
            return []
        rows = (
            self.supabase.table("stock_x_account_health_daily")
            .select("handle,success_count,failure_count,post_count,signal_count,avg_latency_ms,health_date")
            .in_("handle", list(handles))
            .gte("health_date", cutoff_date)
            .limit(5000)
            .execute()
            .data
            or []
        )
        return rows

    def _load_signal_rows(self, handles: Sequence[str], cutoff_iso: str) -> List[Dict[str, Any]]:
        if not handles:
            return []
        rows = (
            self.supabase.table("stock_x_post_signals")
            .select("handle,confidence,side,as_of")
            .in_("handle", list(handles))
            .gte("as_of", cutoff_iso)
            .limit(20000)
            .execute()
            .data
            or []
        )
        return rows

    def _load_post_rows(self, handles: Sequence[str], cutoff_iso: str) -> List[Dict[str, Any]]:
        if not handles:
            return []
        rows = (
            self.supabase.table("stock_x_posts_raw")
            .select("handle,posted_at,as_of")
            .in_("handle", list(handles))
            .gte("as_of", cutoff_iso)
            .limit(20000)
            .execute()
            .data
            or []
        )
        return rows

    def _build_quality(
        self,
        handles: Sequence[str],
        health_rows: List[Dict[str, Any]],
        signal_rows: List[Dict[str, Any]],
        post_rows: List[Dict[str, Any]],
    ) -> List[AccountQuality]:
        health_map: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for row in health_rows:
            handle = str(row.get("handle") or "").strip()
            if not handle:
                continue
            item = health_map[handle]
            item["success"] += _safe_float(row.get("success_count"), 0.0)
            item["failure"] += _safe_float(row.get("failure_count"), 0.0)
            item["posts"] += _safe_float(row.get("post_count"), 0.0)
            item["signals"] += _safe_float(row.get("signal_count"), 0.0)
            item["latency_total"] += _safe_float(row.get("avg_latency_ms"), 0.0)
            item["latency_days"] += 1

        signal_map: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for row in signal_rows:
            handle = str(row.get("handle") or "").strip()
            if not handle:
                continue
            item = signal_map[handle]
            item["total"] += 1
            confidence = _safe_float(row.get("confidence"), 0.0)
            if confidence < 0.45:
                item["low_conf"] += 1
            side = str(row.get("side") or "").upper()
            if side == "NEUTRAL":
                item["neutral"] += 1

        latest_post_age: Dict[str, float] = {}
        now = _now_utc()
        for row in post_rows:
            handle = str(row.get("handle") or "").strip()
            if not handle:
                continue
            text = str(row.get("posted_at") or row.get("as_of") or "").replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(text)
            except Exception:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_h = max(0.0, (now - dt.astimezone(timezone.utc)).total_seconds() / 3600)
            prev = latest_post_age.get(handle)
            if prev is None or age_h < prev:
                latest_post_age[handle] = age_h

        result: List[AccountQuality] = []
        for handle in handles:
            health = health_map.get(handle, {})
            signal = signal_map.get(handle, {})

            success = _safe_float(health.get("success"), 0.0)
            failure = _safe_float(health.get("failure"), 0.0)
            total_runs = max(1.0, success + failure)
            reliability = _clamp(success / total_runs, 0.0, 1.0)

            posts_7d = int(_safe_float(health.get("posts"), 0.0))
            signals_7d = int(_safe_float(health.get("signals"), 0.0))
            activity = _clamp(posts_7d / float(self.lookback_days * 3), 0.0, 1.0)

            total_signal = max(1.0, _safe_float(signal.get("total"), 0.0))
            neutral_ratio = _clamp(_safe_float(signal.get("neutral"), 0.0) / total_signal, 0.0, 1.0)
            low_conf_ratio = _clamp(_safe_float(signal.get("low_conf"), 0.0) / total_signal, 0.0, 1.0)
            precision = _clamp(1.0 - neutral_ratio * 0.6 - low_conf_ratio * 0.4, 0.0, 1.0)

            latest_age_h = latest_post_age.get(handle, 9999.0)
            if latest_age_h <= 6:
                freshness = 1.0
            elif latest_age_h <= 24:
                freshness = 0.75
            elif latest_age_h <= 48:
                freshness = 0.45
            else:
                freshness = 0.1

            latency_days = max(1.0, _safe_float(health.get("latency_days"), 0.0))
            avg_latency = _safe_float(health.get("latency_total"), 0.0) / latency_days
            if avg_latency <= 6000:
                latency_score = 1.0
            elif avg_latency <= 12000:
                latency_score = 0.7
            elif avg_latency <= 20000:
                latency_score = 0.4
            else:
                latency_score = 0.2

            quality = (
                reliability * 0.35
                + activity * 0.2
                + precision * 0.25
                + freshness * 0.15
                + latency_score * 0.05
            )
            quality_score = round(_clamp(quality, 0.0, 1.0) * 100, 2)

            if quality_score >= 72 and reliability >= 0.8:
                status = "healthy"
            elif quality_score >= 48:
                status = "degraded"
            else:
                status = "critical"

            notes = (
                f"posts={posts_7d},signals={signals_7d},neutral={neutral_ratio:.2f},"
                f"low_conf={low_conf_ratio:.2f},freshness_h={latest_age_h:.1f}"
            )
            result.append(
                AccountQuality(
                    handle=handle,
                    quality_score=quality_score,
                    reliability_score=round(reliability, 4),
                    precision_score=round(precision, 4),
                    activity_score=round(activity, 4),
                    freshness_score=round(freshness, 4),
                    latency_score=round(latency_score, 4),
                    neutral_ratio=round(neutral_ratio, 4),
                    low_conf_ratio=round(low_conf_ratio, 4),
                    posts_7d=posts_7d,
                    signals_7d=signals_7d,
                    status=status,
                    notes=notes,
                )
            )
        return result

    def _upsert_quality(self, rows: List[AccountQuality], score_date: str) -> None:
        if self.dry_run or not rows:
            return

        upsert_rows = [
            {
                "score_date": score_date,
                "handle": row.handle,
                "quality_score": row.quality_score,
                "reliability_score": row.reliability_score,
                "precision_score": row.precision_score,
                "activity_score": row.activity_score,
                "freshness_score": row.freshness_score,
                "latency_score": row.latency_score,
                "neutral_ratio": row.neutral_ratio,
                "low_conf_ratio": row.low_conf_ratio,
                "posts_7d": row.posts_7d,
                "signals_7d": row.signals_7d,
                "status": row.status,
                "notes": row.notes,
                "run_id": self.run_id,
                "as_of": _now_utc().isoformat(),
            }
            for row in rows
        ]
        self.supabase.table("stock_x_account_score_daily").upsert(
            upsert_rows,
            on_conflict="score_date,handle",
        ).execute()

    def _sync_account_score(self, rows: List[AccountQuality]) -> None:
        if self.dry_run or not rows:
            return

        handle_map = {row.handle: row for row in rows}
        handles = list(handle_map.keys())
        account_rows = (
            self.supabase.table("stock_x_accounts")
            .select("id,handle,score,source_payload")
            .in_("handle", handles)
            .execute()
            .data
            or []
        )

        now_iso = _now_utc().isoformat()
        for row in account_rows:
            handle = str(row.get("handle") or "").strip()
            quality = handle_map.get(handle)
            if not quality:
                continue
            base_score = _safe_float(row.get("score"), 0.0)
            merged_score = round(_clamp(base_score * 0.6 + quality.quality_score * 0.4, 0.0, 100.0), 4)
            payload = row.get("source_payload")
            payload_map = payload if isinstance(payload, dict) else {}
            payload_map["quality_score"] = quality.quality_score
            payload_map["quality_status"] = quality.status
            payload_map["quality_run_id"] = self.run_id
            (
                self.supabase.table("stock_x_accounts")
                .update(
                    {
                        "score": merged_score,
                        "source_payload": payload_map,
                        "run_id": self.run_id,
                        "as_of": now_iso,
                    }
                )
                .eq("id", int(row.get("id") or 0))
                .execute()
            )

    def _upsert_quality_source_health(self, rows: List[AccountQuality], score_date: str) -> None:
        if self.dry_run:
            return
        total = max(1, len(rows))
        healthy = sum(1 for row in rows if row.status == "healthy")
        degraded = sum(1 for row in rows if row.status == "degraded")
        critical = sum(1 for row in rows if row.status == "critical")
        success_rate = healthy / total
        error_rate = critical / total
        null_rate = 0.0
        status = "healthy"
        if critical > 0:
            status = "critical"
        elif degraded > 0:
            status = "degraded"

        avg_score = round(sum(row.quality_score for row in rows) / total, 2) if rows else 0.0
        payload = {
            "source_id": "x_grok_quality",
            "health_date": score_date,
            "success_rate": round(success_rate, 4),
            "p95_latency_ms": 0,
            "freshness_sec": 0,
            "null_rate": null_rate,
            "error_rate": round(error_rate, 4),
            "status": status,
            "notes": f"healthy={healthy},degraded={degraded},critical={critical},avg={avg_score}",
            "source_payload": {
                "accounts_total": total,
                "avg_quality_score": avg_score,
            },
            "run_id": self.run_id,
            "as_of": _now_utc().isoformat(),
        }
        self.supabase.table("source_health_daily").upsert(
            payload,
            on_conflict="source_id,health_date",
        ).execute()

    def run(self) -> Dict[str, Any]:
        now = _now_utc()
        cutoff_iso = (now - timedelta(days=self.lookback_days)).isoformat()
        cutoff_date = (now - timedelta(days=self.lookback_days)).date().isoformat()
        score_date = now.date().isoformat()

        handles = self._load_active_accounts()
        if not handles:
            return {"run_id": self.run_id, "accounts": 0, "message": "no active handles"}

        logger.info(
            f"[STOCK_X_QUALITY_START] run_id={self.run_id} handles={len(handles)} lookback={self.lookback_days}d"
        )

        health_rows = self._load_health_rows(handles, cutoff_date=cutoff_date)
        signal_rows = self._load_signal_rows(handles, cutoff_iso=cutoff_iso)
        post_rows = self._load_post_rows(handles, cutoff_iso=cutoff_iso)
        qualities = self._build_quality(handles, health_rows, signal_rows, post_rows)

        self._upsert_quality(qualities, score_date=score_date)
        self._sync_account_score(qualities)
        self._upsert_quality_source_health(qualities, score_date=score_date)

        healthy = sum(1 for row in qualities if row.status == "healthy")
        degraded = sum(1 for row in qualities if row.status == "degraded")
        critical = sum(1 for row in qualities if row.status == "critical")

        result = {
            "run_id": self.run_id,
            "accounts": len(qualities),
            "healthy": healthy,
            "degraded": degraded,
            "critical": critical,
            "avg_quality_score": round(sum(row.quality_score for row in qualities) / max(1, len(qualities)), 2),
        }
        logger.info(f"[STOCK_X_QUALITY_DONE] {json.dumps(result, ensure_ascii=False)}")
        return result


def _default_run_id() -> str:
    return f"x-quality-{_now_utc().strftime('%Y%m%d%H%M%S')}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stock X quality governor")
    parser.add_argument("--lookback-days", type=int, default=7, help="质量评估回看天数")
    parser.add_argument("--topn", type=int, default=30, help="评估活跃账号数量")
    parser.add_argument("--run-id", default="", help="自定义 run_id")
    parser.add_argument("--dry-run", action="store_true", help="仅计算，不写入")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    governor = StockXQualityGovernor(
        lookback_days=args.lookback_days,
        run_id=args.run_id or _default_run_id(),
        dry_run=bool(args.dry_run),
        topn=args.topn,
    )
    governor.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
