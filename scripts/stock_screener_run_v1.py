#!/usr/bin/env python3
"""StockOps P1 策略筛选器运行脚本。"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

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


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


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


def _to_json_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _to_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _init_supabase():
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


def _load_templates(supabase: Any, template_key: str, limit: int) -> List[Dict[str, Any]]:
    query = (
        supabase.table("stock_screener_templates_v1")
        .select(
            "id,template_key,template_name,template_type,universe,default_filters,"
            "scoring_weights,metadata"
        )
        .eq("is_active", True)
        .order("updated_at", desc=True)
        .limit(limit)
    )
    if template_key:
        query = query.eq("template_key", template_key)

    rows = query.execute().data or []
    return rows


def _load_opportunities(supabase: Any, lookback_hours: int, limit: int) -> List[Dict[str, Any]]:
    cutoff = (_now_utc() - timedelta(hours=lookback_hours)).isoformat()
    rows = (
        supabase.table("stock_opportunities_v2")
        .select(
            "id,ticker,side,horizon,risk_level,opportunity_score,confidence,catalysts,"
            "source_signal_ids,as_of"
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


def _match_filters(row: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    score = _safe_float(row.get("opportunity_score"), 0.0)
    confidence = _safe_float(row.get("confidence"), 0.0)
    risk = str(row.get("risk_level") or "L2").upper()
    horizon = str(row.get("horizon") or "B").upper()

    min_score = _safe_float(filters.get("min_score"), 0.0)
    min_confidence = _safe_float(filters.get("min_confidence"), 0.0)
    risk_levels = {item.upper() for item in _to_str_list(filters.get("risk_levels"))}
    horizons = {item.upper() for item in _to_str_list(filters.get("horizon"))}

    if score < min_score:
        return False
    if confidence < min_confidence:
        return False
    if risk_levels and risk not in risk_levels:
        return False
    if horizons and horizon not in horizons:
        return False
    return True


def _calc_freshness_score(as_of: str) -> float:
    try:
        parsed = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return 0.0

    age_h = max(0.0, (_now_utc() - parsed.astimezone(timezone.utc)).total_seconds() / 3600.0)
    return _clamp(1.0 - age_h / 72.0, 0.0, 1.0)


def _calc_risk_score(risk_level: str) -> float:
    risk = str(risk_level or "L2").upper()
    mapping = {
        "L0": 1.0,
        "L1": 0.9,
        "L2": 0.75,
        "L3": 0.55,
        "L4": 0.35,
    }
    return mapping.get(risk, 0.7)


def _score_candidate(row: Dict[str, Any], weights: Dict[str, Any]) -> Dict[str, Any]:
    w_score = _safe_float(weights.get("score"), 0.5)
    w_conf = _safe_float(weights.get("confidence"), 0.3)
    w_fresh = _safe_float(weights.get("freshness"), 0.1)
    w_risk = _safe_float(weights.get("risk"), 0.1)
    w_catalyst = _safe_float(weights.get("catalyst"), 0.0)

    opp_score = _clamp(_safe_float(row.get("opportunity_score"), 0.0) / 100.0, 0.0, 1.0)
    conf = _clamp(_safe_float(row.get("confidence"), 0.0), 0.0, 1.0)
    fresh = _calc_freshness_score(str(row.get("as_of") or ""))
    risk_score = _calc_risk_score(str(row.get("risk_level") or "L2"))
    catalyst_count = len(_to_str_list(row.get("catalysts")))
    catalyst_score = _clamp(catalyst_count / 4.0, 0.0, 1.0)

    raw = (
        opp_score * w_score
        + conf * w_conf
        + fresh * w_fresh
        + risk_score * w_risk
        + catalyst_score * w_catalyst
    )
    final_score = round(_clamp(raw, 0.0, 1.0) * 100.0, 2)

    return {
        "score": final_score,
        "confidence": round(conf, 4),
        "reason_points": [
            f"机会分数 {_safe_float(row.get('opportunity_score'), 0.0):.1f}",
            f"置信度 {conf:.2f}",
            f"新鲜度 {fresh:.2f}",
        ],
        "backtest_metrics": {
            "hit_proxy": round(_clamp(0.6 * opp_score + 0.4 * conf, 0.0, 1.0), 4),
            "drawdown_proxy": round(_clamp(1.0 - risk_score, 0.0, 1.0), 4),
            "vol_proxy": round(_clamp(1.0 - fresh * 0.5, 0.0, 1.0), 4),
        },
    }


def _build_run_key(user_id: str, template_key: str, run_id: str) -> str:
    digest = hashlib.sha1(f"{user_id}:{template_key}:{run_id}".encode("utf-8")).hexdigest()[:18]
    return f"scr-{digest}"


def _run_one_template(
    supabase: Any,
    template: Dict[str, Any],
    opportunities: List[Dict[str, Any]],
    user_id: str,
    run_id: str,
    topn: int,
) -> Dict[str, Any]:
    template_id = _safe_int(template.get("id"), 0)
    template_key = str(template.get("template_key") or "")
    if template_id <= 0 or not template_key:
        return {"template_key": template_key or "", "run_written": 0, "candidates_written": 0}

    filters = _to_json_dict(template.get("default_filters"))
    weights = _to_json_dict(template.get("scoring_weights"))

    run_key = _build_run_key(user_id, template_key, run_id)
    run_row = {
        "run_key": run_key,
        "user_id": user_id,
        "template_id": template_id,
        "run_mode": "preview",
        "universe": str(template.get("universe") or "us_equity"),
        "filters": filters,
        "metrics": {},
        "candidate_count": 0,
        "status": "running",
        "run_id": run_id,
        "as_of": _now_utc().isoformat(),
    }

    upsert_res = (
        supabase.table("stock_screener_runs_v1")
        .upsert(run_row, on_conflict="run_key")
        .execute()
    )
    run_data = upsert_res.data or []
    run_table_id = _safe_int((run_data[0] if run_data else {}).get("id"), 0)
    if run_table_id <= 0:
        fetched = (
            supabase.table("stock_screener_runs_v1")
            .select("id")
            .eq("run_key", run_key)
            .limit(1)
            .maybe_single()
            .execute()
            .data
            or {}
        )
        run_table_id = _safe_int(fetched.get("id"), 0)

    candidates: List[Dict[str, Any]] = []
    for row in opportunities:
        if not _match_filters(row, filters):
            continue
        scored = _score_candidate(row, weights)
        candidates.append(
            {
                "ticker": str(row.get("ticker") or "").upper(),
                "side": str(row.get("side") or "LONG").upper(),
                "risk_level": str(row.get("risk_level") or "L2").upper(),
                "horizon": str(row.get("horizon") or "B").upper(),
                "score": scored["score"],
                "confidence": scored["confidence"],
                "reason_points": scored["reason_points"],
                "backtest_metrics": scored["backtest_metrics"],
                "source_opportunity_id": _safe_int(row.get("id"), 0),
                "source_signal_ids": _to_str_list(row.get("source_signal_ids")),
                "as_of": _now_utc().isoformat(),
            }
        )

    candidates.sort(key=lambda item: (item["score"], item["confidence"]), reverse=True)
    final_rows = candidates[: max(1, topn)]

    if run_table_id > 0 and final_rows:
        payloads: List[Dict[str, Any]] = []
        for idx, item in enumerate(final_rows, start=1):
            payloads.append(
                {
                    "run_id": run_table_id,
                    "ticker": item["ticker"],
                    "side": item["side"],
                    "score": item["score"],
                    "confidence": item["confidence"],
                    "risk_level": item["risk_level"],
                    "horizon": item["horizon"],
                    "rank": idx,
                    "reason_points": item["reason_points"],
                    "backtest_metrics": item["backtest_metrics"],
                    "source_opportunity_id": item["source_opportunity_id"],
                    "source_signal_ids": item["source_signal_ids"],
                    "run_trace_id": run_id,
                    "status": "candidate",
                    "as_of": item["as_of"],
                }
            )

        for offset in range(0, len(payloads), 200):
            batch = payloads[offset : offset + 200]
            supabase.table("stock_screener_candidates_v1").insert(batch).execute()

    metrics = {
        "matched": len(candidates),
        "selected": len(final_rows),
        "avg_score": round(
            sum(item["score"] for item in final_rows) / len(final_rows),
            2,
        )
        if final_rows
        else 0.0,
    }

    if run_table_id > 0:
        (
            supabase.table("stock_screener_runs_v1")
            .update(
                {
                    "status": "success",
                    "candidate_count": len(final_rows),
                    "metrics": metrics,
                    "updated_at": _now_utc().isoformat(),
                }
            )
            .eq("id", run_table_id)
            .execute()
        )

    logger.info(
        "[P1_SCREENER_TEMPLATE_DONE] template=%s matched=%s selected=%s",
        template_key,
        len(candidates),
        len(final_rows),
    )
    return {
        "template_key": template_key,
        "run_written": 1 if run_table_id > 0 else 0,
        "candidates_written": len(final_rows),
        "metrics": metrics,
    }


def run_screener(
    run_id: str,
    user_id: str,
    template_key: str,
    lookback_hours: int,
    opportunity_limit: int,
    template_limit: int,
    topn: int,
) -> Dict[str, Any]:
    supabase = _init_supabase()
    templates = _load_templates(supabase, template_key=template_key, limit=template_limit)
    opportunities = _load_opportunities(
        supabase,
        lookback_hours=lookback_hours,
        limit=opportunity_limit,
    )

    logger.info(
        "[P1_SCREENER_INPUT] templates=%s opportunities=%s user_id=%s",
        len(templates),
        len(opportunities),
        user_id,
    )

    results: List[Dict[str, Any]] = []
    for template in templates:
        try:
            result = _run_one_template(
                supabase,
                template,
                opportunities,
                user_id=user_id,
                run_id=run_id,
                topn=topn,
            )
            results.append(result)
        except Exception as exc:
            logger.error(
                "[P1_SCREENER_TEMPLATE_FAILED] template=%s error=%s",
                str(template.get("template_key") or ""),
                str(exc)[:200],
            )

    total_runs = sum(_safe_int(item.get("run_written"), 0) for item in results)
    total_candidates = sum(_safe_int(item.get("candidates_written"), 0) for item in results)
    summary = {
        "run_id": run_id,
        "template_count": len(templates),
        "opportunities": len(opportunities),
        "runs_written": total_runs,
        "candidates_written": total_candidates,
        "results": results,
    }
    logger.info("[P1_SCREENER_DONE] %s", json.dumps(summary, ensure_ascii=False))
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StockOps P1 screener runner")
    parser.add_argument("--run-id", type=str, default="", help="外部 run id")
    parser.add_argument("--user-id", type=str, default="system", help="执行用户")
    parser.add_argument("--template-key", type=str, default="", help="指定模板，不填则全量")
    parser.add_argument("--lookback-hours", type=int, default=96, help="机会回看小时")
    parser.add_argument("--opportunity-limit", type=int, default=5000, help="机会读取上限")
    parser.add_argument("--template-limit", type=int, default=20, help="模板读取上限")
    parser.add_argument("--topn", type=int, default=40, help="每个模板输出候选数")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    run_id = args.run_id.strip() or f"p1-screener-{_now_utc().strftime('%Y%m%d%H%M%S')}"
    logger.info(
        "[P1_SCREENER_START] run_id=%s template=%s lookback=%s",
        run_id,
        args.template_key or "ALL",
        args.lookback_hours,
    )
    try:
        run_screener(
            run_id=run_id,
            user_id=str(args.user_id or "system")[:64],
            template_key=args.template_key.strip(),
            lookback_hours=max(1, args.lookback_hours),
            opportunity_limit=max(200, args.opportunity_limit),
            template_limit=max(1, args.template_limit),
            topn=max(5, args.topn),
        )
    except Exception as exc:
        message = str(exc)
        if "stock_screener_templates_v1" in message or "stock_screener_runs_v1" in message:
            logger.error(
                "[P1_SCREENER_MISSING_SCHEMA] error=%s; "
                "请先执行 sql/2026-02-24_stock_p1_portfolio_screener_schema.sql",
                message[:200],
            )
            return
        logger.error("[P1_SCREENER_FAILED] error=%s", message[:200])
        raise


if __name__ == "__main__":
    main()
