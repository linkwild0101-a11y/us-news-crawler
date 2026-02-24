#!/usr/bin/env python3
"""StockOps P0: 告警规则引擎（基于现有 V2 信号与机会）。"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

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

LEVEL_SCORE: Dict[str, int] = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}
NY_TZ = ZoneInfo("America/New_York")


@dataclass
class AlertRule:
    """告警规则定义。"""

    rule_key: str
    user_id: str
    signal_type: str
    min_level: str
    min_score: float
    cooldown_sec: int
    session_scope: str
    daily_limit: int
    priority: int


@dataclass
class UserPref:
    """用户告警偏好。"""

    user_id: str
    enable_premarket: bool
    enable_postmarket: bool
    daily_alert_cap: int
    watch_tickers: List[str]
    muted_signal_types: List[str]
    quiet_hours_start: int
    quiet_hours_end: int


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(value: Any, fallback: Optional[str] = None) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return fallback or _now_utc().isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _clamp(value: float, left: float, right: float) -> float:
    return max(left, min(right, value))


def _level_value(level: str) -> int:
    return LEVEL_SCORE.get(str(level or "").upper(), 0)


def _session_tag(now_utc: datetime) -> str:
    ny = now_utc.astimezone(NY_TZ)
    minute = ny.hour * 60 + ny.minute
    if 4 * 60 <= minute < 9 * 60 + 30:
        return "premarket"
    if 9 * 60 + 30 <= minute < 16 * 60:
        return "regular"
    if 16 * 60 <= minute < 20 * 60:
        return "postmarket"
    return "closed"


def _window_floor(now_utc: datetime, cooldown_sec: int) -> datetime:
    ts = int(now_utc.timestamp())
    bucket = max(60, cooldown_sec)
    floored = (ts // bucket) * bucket
    return datetime.fromtimestamp(floored, tz=timezone.utc)


def _in_quiet_hours(now_utc: datetime, start_hour: int, end_hour: int) -> bool:
    start = max(0, min(23, int(start_hour)))
    end = max(0, min(23, int(end_hour)))
    if start == end:
        return False
    current_hour = now_utc.astimezone(NY_TZ).hour
    if start < end:
        return start <= current_hour < end
    return current_hour >= start or current_hour < end


class StockAlertEngineV1:
    """StockOps P0 告警引擎。"""

    def __init__(self) -> None:
        self.supabase = self._init_supabase()

    def _init_supabase(self) -> Client:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("缺少 SUPABASE_URL / SUPABASE_KEY")
        return create_client(url, key)

    def _load_rules(self) -> List[AlertRule]:
        """加载启用规则，缺失时回退默认规则。"""
        try:
            rows = (
                self.supabase.table("stock_alert_rules_v1")
                .select(
                    "rule_key,user_id,signal_type,min_level,min_score,cooldown_sec,"
                    "session_scope,daily_limit,priority"
                )
                .eq("is_active", True)
                .order("priority")
                .limit(300)
                .execute()
                .data
                or []
            )
        except Exception as e:
            logger.warning(f"[ALERT_RULES_FALLBACK] error={str(e)[:120]}")
            rows = []

        rules: List[AlertRule] = []
        for row in rows:
            rules.append(
                AlertRule(
                    rule_key=str(row.get("rule_key") or "default-l3-70")[:96],
                    user_id=str(row.get("user_id") or "system")[:64],
                    signal_type=str(row.get("signal_type") or "opportunity")[:32],
                    min_level=str(row.get("min_level") or "L3")[:2].upper(),
                    min_score=_clamp(_safe_float(row.get("min_score"), 70.0), 0.0, 100.0),
                    cooldown_sec=max(60, _safe_int(row.get("cooldown_sec"), 7200)),
                    session_scope=str(row.get("session_scope") or "all")[:16],
                    daily_limit=max(1, _safe_int(row.get("daily_limit"), 20)),
                    priority=max(1, _safe_int(row.get("priority"), 100)),
                )
            )

        if rules:
            return rules

        return [
            AlertRule(
                rule_key="default-l3-70",
                user_id="system",
                signal_type="opportunity",
                min_level="L3",
                min_score=70.0,
                cooldown_sec=7200,
                session_scope="all",
                daily_limit=20,
                priority=100,
            )
        ]

    def _load_user_prefs(self) -> List[UserPref]:
        """加载用户偏好，缺失时回退 system 默认用户。"""
        try:
            rows = (
                self.supabase.table("stock_alert_user_prefs_v1")
                .select(
                    "user_id,enable_premarket,enable_postmarket,daily_alert_cap,"
                    "watch_tickers,muted_signal_types,quiet_hours_start,quiet_hours_end"
                )
                .eq("is_active", True)
                .limit(300)
                .execute()
                .data
                or []
            )
        except Exception as e:
            logger.warning(f"[ALERT_PREFS_FALLBACK] error={str(e)[:120]}")
            rows = []

        prefs: List[UserPref] = []
        for row in rows:
            watch_tickers = [
                str(item or "").upper()
                for item in (row.get("watch_tickers") or [])
                if str(item or "").strip()
            ]
            muted_types = [
                str(item or "").strip().lower()
                for item in (row.get("muted_signal_types") or [])
                if str(item or "").strip()
            ]
            prefs.append(
                UserPref(
                    user_id=str(row.get("user_id") or "system")[:64],
                    enable_premarket=bool(row.get("enable_premarket", False)),
                    enable_postmarket=bool(row.get("enable_postmarket", True)),
                    daily_alert_cap=max(1, _safe_int(row.get("daily_alert_cap"), 20)),
                    watch_tickers=watch_tickers,
                    muted_signal_types=muted_types,
                    quiet_hours_start=max(0, min(23, _safe_int(row.get("quiet_hours_start"), 0))),
                    quiet_hours_end=max(0, min(23, _safe_int(row.get("quiet_hours_end"), 0))),
                )
            )

        if prefs:
            return prefs

        return [
            UserPref(
                user_id="system",
                enable_premarket=False,
                enable_postmarket=True,
                daily_alert_cap=20,
                watch_tickers=[],
                muted_signal_types=[],
                quiet_hours_start=0,
                quiet_hours_end=0,
            )
        ]

    def _load_opportunities(self, limit: int) -> List[Dict[str, Any]]:
        try:
            return (
                self.supabase.table("stock_opportunities_v2")
                .select(
                    "id,ticker,side,horizon,opportunity_score,risk_level,why_now,"
                    "source_signal_ids,source_event_ids,as_of"
                )
                .eq("is_active", True)
                .order("opportunity_score", desc=True)
                .limit(limit)
                .execute()
                .data
                or []
            )
        except Exception as e:
            logger.warning(f"[ALERT_LOAD_OPPS_FALLBACK] error={str(e)[:120]}")
            return []

    def _load_signal_map(self, tickers: Sequence[str], limit: int) -> Dict[str, Dict[str, Any]]:
        if not tickers:
            return {}
        try:
            rows = (
                self.supabase.table("stock_signals_v2")
                .select("ticker,level,signal_score,confidence,source_mix,as_of")
                .eq("is_active", True)
                .in_("ticker", list(set(tickers))[:500])
                .order("signal_score", desc=True)
                .limit(limit)
                .execute()
                .data
                or []
            )
        except Exception as e:
            logger.warning(f"[ALERT_LOAD_SIGNALS_FALLBACK] error={str(e)[:120]}")
            return {}

        signal_map: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            ticker = str(row.get("ticker") or "").upper()
            if ticker and ticker not in signal_map:
                signal_map[ticker] = row
        return signal_map

    def _load_user_daily_counts(self, user_ids: Sequence[str], now_utc: datetime) -> Dict[str, int]:
        if not user_ids:
            return {}
        day_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        try:
            rows = (
                self.supabase.table("stock_alert_events_v1")
                .select("user_id")
                .in_("user_id", list(set(user_ids))[:500])
                .gte("created_at", day_start)
                .limit(3000)
                .execute()
                .data
                or []
            )
        except Exception as e:
            logger.warning(f"[ALERT_DAILY_COUNT_FALLBACK] error={str(e)[:120]}")
            return defaultdict(int)

        counts: Dict[str, int] = defaultdict(int)
        for row in rows:
            user_id = str(row.get("user_id") or "").strip()
            if user_id:
                counts[user_id] += 1
        return counts

    def _session_allowed(self, session_tag: str, pref: UserPref, rule: AlertRule, now_utc: datetime) -> bool:
        if rule.session_scope not in ("all", session_tag):
            return False
        if _in_quiet_hours(now_utc, pref.quiet_hours_start, pref.quiet_hours_end):
            return False
        if session_tag == "premarket" and not pref.enable_premarket:
            return False
        if session_tag == "postmarket" and not pref.enable_postmarket:
            return False
        if session_tag == "closed":
            return False
        return True

    def _rule_match(self, rule: AlertRule, level: str, score: float, signal_type: str) -> bool:
        if rule.signal_type not in ("all", signal_type):
            return False
        if _level_value(level) < _level_value(rule.min_level):
            return False
        if score < rule.min_score:
            return False
        return True

    def _alert_key(
        self,
        user_id: str,
        ticker: str,
        signal_type: str,
        dedupe_window_iso: str,
        rule_key: str,
    ) -> str:
        seed = f"{user_id}:{ticker}:{signal_type}:{dedupe_window_iso}:{rule_key}"
        digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
        return f"alert:{digest[:24]}"

    def _build_rows(
        self,
        run_id: str,
        rules: List[AlertRule],
        prefs: List[UserPref],
        opportunities: List[Dict[str, Any]],
        signal_map: Dict[str, Dict[str, Any]],
        now_utc: datetime,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        user_counts = self._load_user_daily_counts([item.user_id for item in prefs], now_utc)
        rules_by_user: Dict[str, List[AlertRule]] = defaultdict(list)
        for rule in sorted(rules, key=lambda item: item.priority):
            rules_by_user[rule.user_id].append(rule)

        session_tag = _session_tag(now_utc)
        now_iso = now_utc.isoformat()

        for pref in prefs:
            user_id = pref.user_id
            cap = max(1, min(pref.daily_alert_cap, 200))
            emitted = user_counts.get(user_id, 0)
            user_rules = rules_by_user.get(user_id) or rules_by_user.get("system") or []
            if not user_rules:
                continue

            for opp in opportunities:
                if emitted >= cap:
                    break

                ticker = str(opp.get("ticker") or "").upper()
                if not ticker:
                    continue
                if pref.watch_tickers and ticker not in pref.watch_tickers:
                    continue

                signal = signal_map.get(ticker) or {}
                level = str(signal.get("level") or opp.get("risk_level") or "L1").upper()
                opp_score = _clamp(_safe_float(opp.get("opportunity_score"), 0.0), 0.0, 100.0)
                side = str(opp.get("side") or "NEUTRAL").upper()
                if side not in ("LONG", "SHORT", "NEUTRAL"):
                    side = "NEUTRAL"

                for rule in user_rules:
                    signal_type = str(rule.signal_type or "opportunity").lower()
                    if signal_type in pref.muted_signal_types:
                        continue
                    if not self._session_allowed(session_tag, pref, rule, now_utc):
                        continue
                    if not self._rule_match(rule, level=level, score=opp_score, signal_type="opportunity"):
                        continue

                    window_iso = _window_floor(now_utc, rule.cooldown_sec).isoformat()
                    alert_key = self._alert_key(
                        user_id=user_id,
                        ticker=ticker,
                        signal_type="opportunity",
                        dedupe_window_iso=window_iso,
                        rule_key=rule.rule_key,
                    )
                    title = f"{ticker} {side} {level} 异动提醒"
                    why_now = str(opp.get("why_now") or "")[:500]

                    rows.append(
                        {
                            "alert_key": alert_key,
                            "user_id": user_id,
                            "ticker": ticker,
                            "signal_type": "opportunity",
                            "signal_level": level,
                            "alert_score": round(opp_score, 2),
                            "side": side,
                            "title": title[:220],
                            "why_now": why_now,
                            "session_tag": session_tag,
                            "dedupe_window": window_iso,
                            "payload": {
                                "rule_key": rule.rule_key,
                                "opportunity_id": int(opp.get("id") or 0),
                                "source_signal_ids": opp.get("source_signal_ids") or [],
                                "source_event_ids": opp.get("source_event_ids") or [],
                                "opportunity_as_of": _to_iso(opp.get("as_of"), fallback=now_iso),
                                "signal_score": _safe_float(signal.get("signal_score"), 0.0),
                                "signal_confidence": _safe_float(signal.get("confidence"), 0.0),
                            },
                            "status": "pending",
                            "run_id": run_id,
                            "as_of": now_iso,
                            "is_active": True,
                        }
                    )
                    emitted += 1
                    break

        return rows

    def _upsert_rows(self, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        try:
            self.supabase.table("stock_alert_events_v1").upsert(
                rows,
                on_conflict="alert_key",
            ).execute()
            return len(rows)
        except Exception as e:
            logger.warning(f"[ALERT_UPSERT_FALLBACK] error={str(e)[:120]}")
            return 0

    def run(self, run_id: str, hours: int, opp_limit: int, signal_limit: int) -> Dict[str, Any]:
        """执行规则引擎并写入 alert events。"""
        started = _now_utc()
        logger.info(
            f"[STOCK_ALERT_V1_START] run_id={run_id} hours={hours} "
            f"opp_limit={opp_limit} signal_limit={signal_limit}"
        )

        rules = self._load_rules()
        prefs = self._load_user_prefs()
        opportunities = self._load_opportunities(limit=opp_limit)
        if not opportunities:
            logger.info("[STOCK_ALERT_V1_EMPTY] no active opportunities")
            return {
                "run_id": run_id,
                "rules": len(rules),
                "users": len(prefs),
                "opportunities": 0,
                "alerts_written": 0,
            }

        tickers = [str(row.get("ticker") or "").upper() for row in opportunities if row.get("ticker")]
        signal_map = self._load_signal_map(tickers=tickers, limit=signal_limit)
        rows = self._build_rows(
            run_id=run_id,
            rules=rules,
            prefs=prefs,
            opportunities=opportunities,
            signal_map=signal_map,
            now_utc=started,
        )
        written = self._upsert_rows(rows)
        elapsed = (_now_utc() - started).total_seconds()

        logger.info(
            f"[STOCK_ALERT_V1_DONE] run_id={run_id} rules={len(rules)} users={len(prefs)} "
            f"opps={len(opportunities)} built={len(rows)} written={written} elapsed={elapsed:.1f}s"
        )
        return {
            "run_id": run_id,
            "rules": len(rules),
            "users": len(prefs),
            "opportunities": len(opportunities),
            "alerts_built": len(rows),
            "alerts_written": written,
            "elapsed_sec": round(elapsed, 2),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="StockOps P0 告警规则引擎")
    parser.add_argument("--run-id", type=str, default="", help="外部 run id")
    parser.add_argument("--hours", type=int, default=72, help="保留参数，当前逻辑按 active 读取")
    parser.add_argument("--opp-limit", type=int, default=300, help="机会读取上限")
    parser.add_argument("--signal-limit", type=int, default=500, help="信号读取上限")
    args = parser.parse_args()

    run_id = args.run_id.strip() or f"alert-v1-{_now_utc().strftime('%Y%m%d%H%M%S')}"
    engine = StockAlertEngineV1()
    metrics = engine.run(
        run_id=run_id,
        hours=max(1, args.hours),
        opp_limit=max(20, args.opp_limit),
        signal_limit=max(20, args.signal_limit),
    )
    logger.info("[STOCK_ALERT_V1_METRICS] " + ", ".join(f"{k}={v}" for k, v in metrics.items()))


if __name__ == "__main__":
    main()
