#!/usr/bin/env python3
"""Stock V3 Champion/Challenger 对照评分脚本。"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

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

RISK_BONUS = {
    "L0": 4.0,
    "L1": 2.0,
    "L2": 0.0,
    "L3": -3.0,
    "L4": -6.0,
}


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


def _clamp(value: float, left: float, right: float) -> float:
    return max(left, min(right, value))


def _parse_as_of(value: Any) -> datetime:
    try:
        text = str(value or "").replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo:
            return parsed.astimezone(timezone.utc)
        return parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return _now_utc()


def _load_candidates(supabase, lookback_hours: int, limit: int) -> List[Dict[str, Any]]:
    cutoff = (_now_utc() - timedelta(hours=lookback_hours)).isoformat()
    rows = (
        supabase.table("stock_opportunities_v2")
        .select(
            "id,ticker,side,horizon,risk_level,opportunity_score,confidence,catalysts,"
            "source_signal_ids,as_of,run_id"
        )
        .eq("is_active", True)
        .gte("as_of", cutoff)
        .order("opportunity_score", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    return rows


def _to_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _expected_hit_proxy(score: float, confidence: float) -> float:
    return round(_clamp((score / 100.0) * 0.6 + confidence * 0.4, 0.0, 1.0), 6)


def _score_one(row: Dict[str, Any]) -> Dict[str, Any]:
    champion_score = _clamp(_safe_float(row.get("opportunity_score"), 0.0), 0.0, 100.0)
    confidence = _clamp(_safe_float(row.get("confidence"), 0.0), 0.0, 1.0)
    risk_level = str(row.get("risk_level") or "L2").upper()
    side = str(row.get("side") or "LONG").upper()
    catalysts = _to_str_list(row.get("catalysts"))
    signal_ids = row.get("source_signal_ids") if isinstance(row.get("source_signal_ids"), list) else []

    age_hours = max(0.0, (_now_utc() - _parse_as_of(row.get("as_of"))).total_seconds() / 3600.0)
    freshness_bonus = max(0.0, 6.0 - age_hours * 0.8)
    catalyst_bonus = min(10.0, len(catalysts) * 2.2)
    density_bonus = min(6.0, len(signal_ids) * 0.7)
    risk_adjust = RISK_BONUS.get(risk_level, 0.0)
    side_adjust = 1.0 if side == "SHORT" and risk_level in ("L3", "L4") else 0.0

    challenger_score = _clamp(
        champion_score * 0.52
        + confidence * 35.0
        + freshness_bonus
        + catalyst_bonus
        + density_bonus
        + risk_adjust
        + side_adjust,
        0.0,
        100.0,
    )

    champion_hit = _expected_hit_proxy(champion_score, confidence)
    challenger_hit = _expected_hit_proxy(challenger_score, confidence)
    score_delta = round(challenger_score - champion_score, 4)

    return {
        "champion_score": round(champion_score, 4),
        "challenger_score": round(challenger_score, 4),
        "score_delta": score_delta,
        "champion_hit": champion_hit,
        "challenger_hit": challenger_hit,
        "details": {
            "freshness_bonus": round(freshness_bonus, 4),
            "catalyst_bonus": round(catalyst_bonus, 4),
            "density_bonus": round(density_bonus, 4),
            "risk_adjust": round(risk_adjust, 4),
            "side_adjust": round(side_adjust, 4),
            "source_signal_count": len(signal_ids),
            "catalyst_count": len(catalysts),
        },
    }


def _build_scorecards(
    rows: List[Dict[str, Any]],
    run_id: str,
    promote_margin: float,
    champion_model: str,
    challenger_model: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    payloads: List[Dict[str, Any]] = []
    challenger_win = 0
    champion_win = 0
    promote_count = 0
    delta_sum = 0.0

    for row in rows:
        opportunity_id = int(row.get("id") or 0)
        ticker = str(row.get("ticker") or "").upper()
        side = str(row.get("side") or "LONG").upper()
        horizon = str(row.get("horizon") or "A").upper()
        if opportunity_id <= 0 or not ticker or side not in ("LONG", "SHORT"):
            continue

        scored = _score_one(row)
        hit_diff = scored["challenger_hit"] - scored["champion_hit"]
        winner = "tie"
        promote_candidate = False
        if hit_diff >= promote_margin:
            winner = "challenger"
            challenger_win += 1
            promote_candidate = True
            promote_count += 1
        elif hit_diff <= -promote_margin:
            winner = "champion"
            champion_win += 1
        delta_sum += scored["score_delta"]

        payloads.append(
            {
                "run_id": run_id,
                "score_date": _now_utc().date().isoformat(),
                "opportunity_id": opportunity_id,
                "ticker": ticker,
                "side": side,
                "horizon": horizon,
                "champion_model": champion_model,
                "challenger_model": challenger_model,
                "champion_score": scored["champion_score"],
                "challenger_score": scored["challenger_score"],
                "score_delta": scored["score_delta"],
                "expected_hit_proxy": scored["challenger_hit"],
                "winner": winner,
                "promote_candidate": promote_candidate,
                "details": {
                    "champion_hit_proxy": scored["champion_hit"],
                    "challenger_hit_proxy": scored["challenger_hit"],
                    **scored["details"],
                },
                "as_of": _now_utc().isoformat(),
            }
        )

    total = len(payloads)
    metrics = {
        "cc_candidates_total": float(total),
        "cc_challenger_win_count": float(challenger_win),
        "cc_champion_win_count": float(champion_win),
        "cc_promote_candidate_count": float(promote_count),
        "cc_challenger_win_rate": round(challenger_win / total, 4) if total else 0.0,
        "cc_avg_score_delta": round(delta_sum / total, 4) if total else 0.0,
    }
    return payloads, metrics


def _log_run_start(
    supabase,
    run_id: str,
    lookback_hours: int,
    limit: int,
    promote_margin: float,
    champion_model: str,
    challenger_model: str,
) -> None:
    payload = {
        "run_id": run_id,
        "pipeline_name": "stock_v3_champion_challenger",
        "pipeline_version": os.getenv("GITHUB_SHA", "")[:12] or "local",
        "trigger_type": os.getenv("GITHUB_EVENT_NAME", "manual"),
        "status": "running",
        "started_at": _now_utc().isoformat(),
        "input_window": {
            "lookback_hours": lookback_hours,
            "limit": limit,
        },
        "params_json": {
            "lookback_hours": lookback_hours,
            "limit": limit,
            "promote_margin": promote_margin,
            "champion_model": champion_model,
            "challenger_model": challenger_model,
        },
        "commit_sha": os.getenv("GITHUB_SHA", "")[:40],
        "as_of": _now_utc().isoformat(),
    }
    try:
        supabase.table("research_runs").upsert(payload, on_conflict="run_id").execute()
    except Exception as e:
        logger.warning(f"[CC_V3_RUN_START_FAILED] error={str(e)[:120]}")


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
        logger.warning(f"[CC_V3_RUN_FINISH_FAILED] error={str(e)[:120]}")


def _upsert_scorecards(supabase, rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    supabase.table("signal_model_scorecards").upsert(
        rows,
        on_conflict="run_id,opportunity_id,challenger_model",
    ).execute()
    return len(rows)


def _upsert_run_metrics(supabase, run_id: str, metrics: Dict[str, float]) -> int:
    rows = [
        {
            "run_id": run_id,
            "metric_name": key,
            "metric_value": float(value),
            "metric_unit": "ratio" if "rate" in key else "count",
        }
        for key, value in metrics.items()
    ]
    if not rows:
        return 0
    try:
        supabase.table("research_run_metrics").upsert(
            rows,
            on_conflict="run_id,metric_name",
        ).execute()
        return len(rows)
    except Exception as e:
        logger.warning(f"[CC_V3_METRICS_UPSERT_FAILED] error={str(e)[:120]}")
        return 0


def run_champion_challenger(
    run_id: Optional[str],
    lookback_hours: int,
    limit: int,
    promote_margin: float,
    champion_model: str,
    challenger_model: str,
) -> Dict[str, Any]:
    supabase = _init_supabase()
    final_run_id = run_id or f"cc-{_now_utc().strftime('%Y%m%d%H%M%S')}"
    _log_run_start(
        supabase=supabase,
        run_id=final_run_id,
        lookback_hours=lookback_hours,
        limit=limit,
        promote_margin=promote_margin,
        champion_model=champion_model,
        challenger_model=challenger_model,
    )

    try:
        candidates = _load_candidates(
            supabase=supabase,
            lookback_hours=lookback_hours,
            limit=limit,
        )
        rows, metrics = _build_scorecards(
            rows=candidates,
            run_id=final_run_id,
            promote_margin=max(0.0, promote_margin),
            champion_model=champion_model,
            challenger_model=challenger_model,
        )
        upserted = _upsert_scorecards(supabase=supabase, rows=rows)
        _upsert_run_metrics(supabase=supabase, run_id=final_run_id, metrics=metrics)

        summary = {
            "run_id": final_run_id,
            "candidates": len(candidates),
            "scorecards_upserted": upserted,
            **metrics,
        }
        _log_run_finish(
            supabase=supabase,
            run_id=final_run_id,
            status="success",
            notes=f"scorecards_upserted={upserted}",
        )
        logger.info("[CC_V3_DONE] " + ", ".join([f"{k}={v}" for k, v in summary.items()]))
        return summary
    except Exception as e:
        _log_run_finish(
            supabase=supabase,
            run_id=final_run_id,
            status="failed",
            notes=f"error={str(e)[:300]}",
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock V3 champion/challenger runner")
    parser.add_argument("--run-id", type=str, default=None, help="评分 run_id")
    parser.add_argument("--lookback-hours", type=int, default=168, help="候选回看小时")
    parser.add_argument("--limit", type=int, default=1200, help="最多处理候选数")
    parser.add_argument("--promote-margin", type=float, default=0.03, help="晋级边际")
    parser.add_argument("--champion-model", type=str, default="v2_rule", help="champion 模型名")
    parser.add_argument("--challenger-model", type=str, default="v3_alt", help="challenger 模型名")
    args = parser.parse_args()

    summary = run_champion_challenger(
        run_id=args.run_id,
        lookback_hours=max(1, args.lookback_hours),
        limit=max(1, args.limit),
        promote_margin=max(0.0, args.promote_margin),
        champion_model=args.champion_model.strip() or "v2_rule",
        challenger_model=args.challenger_model.strip() or "v3_alt",
    )
    logger.info("[CC_V3_METRICS] " + ", ".join([f"{k}={v}" for k, v in summary.items()]))


if __name__ == "__main__":
    main()
