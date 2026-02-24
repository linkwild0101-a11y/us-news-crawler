#!/usr/bin/env python3
"""StockOps P1 ticker 中文简介批量补全脚本。"""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from supabase import create_client

try:
    from scripts.llm_client import LLMClient
except Exception:  # pragma: no cover - 兼容直接执行
    from llm_client import LLMClient  # type: ignore

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _init_supabase():
    """初始化 Supabase 客户端。"""
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


def _table_available(supabase, table_name: str, probe: str = "id") -> bool:
    try:
        supabase.table(table_name).select(probe).limit(1).execute()
        return True
    except Exception as exc:
        logger.warning("[PROFILE_ENRICH_TABLE_MISSING] table=%s err=%s", table_name, str(exc)[:120])
        return False


def _load_pending_queue(supabase, limit: int) -> List[Dict[str, Any]]:
    rows = (
        supabase.table("stock_ticker_profile_enrich_queue_v1")
        .select("id,ticker,reason,retry_count")
        .eq("is_active", True)
        .in_("status", ["pending", "failed"])
        .order("updated_at", desc=False)
        .limit(limit)
        .execute()
        .data
        or []
    )
    return rows


def _mark_queue_running(supabase, queue_id: int, run_id: str) -> None:
    supabase.table("stock_ticker_profile_enrich_queue_v1").update(
        {
            "status": "running",
            "run_id": run_id,
            "as_of": _now_iso(),
        }
    ).eq("id", queue_id).execute()


def _load_profile_row(supabase, ticker: str) -> Optional[Dict[str, Any]]:
    row = (
        supabase.table("stock_ticker_profiles_v1")
        .select("ticker,display_name,asset_type,sector,industry,summary_cn,quality_score")
        .eq("ticker", ticker)
        .limit(1)
        .maybe_single()
        .execute()
        .data
    )
    if row:
        return row
    return None


def _build_prompt(row: Dict[str, Any]) -> str:
    ticker = str(row.get("ticker") or "").upper().strip()
    display_name = str(row.get("display_name") or "").strip()
    asset_type = str(row.get("asset_type") or "equity").strip()
    sector = str(row.get("sector") or "Unknown").strip()
    industry = str(row.get("industry") or "Unknown").strip()
    existing_summary = str(row.get("summary_cn") or "").strip()
    return (
        "你是美股研究助理。请输出 JSON，格式为："
        '{"summary_cn":"", "quality_score":0.0}。'
        "summary_cn 要求：\n"
        "1) 使用简体中文，20-60字；\n"
        "2) 客观描述该标的业务属性与需关注变量；\n"
        "3) 禁止任何投资建议、保证收益、夸张措辞；\n"
        "4) 只输出 JSON，不要额外文本。\n\n"
        f"ticker={ticker}\n"
        f"display_name={display_name}\n"
        f"asset_type={asset_type}\n"
        f"sector={sector}\n"
        f"industry={industry}\n"
        f"existing_summary={existing_summary}\n"
    )


def _parse_llm_payload(payload: Dict[str, Any]) -> Tuple[str, float]:
    summary = str(payload.get("summary_cn") or "").strip()
    score = max(0.0, min(1.0, _safe_float(payload.get("quality_score"), 0.8)))
    if not summary:
        summary = "该标的与美股主题相关，建议结合行业景气与财务数据持续跟踪。"
        score = max(score, 0.65)
    if len(summary) > 300:
        summary = summary[:300]
    return summary, score


def _update_profile_row(
    supabase,
    ticker: str,
    run_id: str,
    summary: str,
    score: float,
) -> None:
    now_iso = _now_iso()
    payload = {
        "summary_cn": summary,
        "summary_source": "llm",
        "quality_score": score,
        "last_llm_at": now_iso,
        "run_id": run_id,
        "as_of": now_iso,
        "is_active": True,
    }
    try:
        supabase.table("stock_ticker_profiles_v1").update(payload).eq("ticker", ticker).execute()
    except Exception as exc:
        logger.warning("[PROFILE_ENRICH_PROFILE_FALLBACK] ticker=%s err=%s", ticker, str(exc)[:120])
        fallback = {
            "summary_cn": summary,
            "run_id": run_id,
            "as_of": now_iso,
            "is_active": True,
        }
        supabase.table("stock_ticker_profiles_v1").update(fallback).eq("ticker", ticker).execute()


def _mark_queue_failed(
    supabase,
    queue_id: int,
    run_id: str,
    prev_retry_count: int,
    message: str,
) -> None:
    next_retry = datetime.now(timezone.utc).timestamp() + min(3600, 60 * (prev_retry_count + 1))
    next_retry_iso = datetime.fromtimestamp(next_retry, tz=timezone.utc).isoformat()
    supabase.table("stock_ticker_profile_enrich_queue_v1").update(
        {
            "status": "failed",
            "retry_count": prev_retry_count + 1,
            "last_error": message[:240],
            "next_retry_at": next_retry_iso,
            "run_id": run_id,
            "as_of": _now_iso(),
        }
    ).eq("id", queue_id).execute()


def _insert_run_log(supabase, run_id: str, payload: Dict[str, Any]) -> None:
    if not _table_available(supabase, "stock_ticker_profile_sync_runs_v1"):
        return
    row = {
        "run_id": run_id,
        "stage": "enrich",
        "status": "success",
        "input_count": _safe_int(payload.get("input_count")),
        "updated_count": _safe_int(payload.get("updated_count")),
        "queued_count": 0,
        "llm_success_count": _safe_int(payload.get("llm_success_count")),
        "llm_failed_count": _safe_int(payload.get("llm_failed_count")),
        "duration_sec": _safe_float(payload.get("duration_sec")),
        "error_summary": str(payload.get("error_summary") or "")[:240],
        "payload": payload,
        "as_of": _now_iso(),
    }
    supabase.table("stock_ticker_profile_sync_runs_v1").upsert(
        row, on_conflict="run_id"
    ).execute()


def run_enrich(run_id: str, limit: int, sleep_ms: int, dry_run: bool) -> Dict[str, Any]:
    """批量消费队列并补全 ticker 中文简介。"""
    start_ts = time.time()
    supabase = _init_supabase()

    if not _table_available(supabase, "stock_ticker_profile_enrich_queue_v1"):
        return {
            "run_id": run_id,
            "status": "queue_missing",
            "input_count": 0,
            "updated_count": 0,
            "llm_success_count": 0,
            "llm_failed_count": 0,
        }

    queue_rows = _load_pending_queue(supabase, limit=max(1, limit))
    if not queue_rows:
        result = {
            "run_id": run_id,
            "status": "ok",
            "input_count": 0,
            "updated_count": 0,
            "llm_success_count": 0,
            "llm_failed_count": 0,
            "duration_sec": round(time.time() - start_ts, 3),
        }
        _insert_run_log(supabase, run_id=run_id, payload=result)
        return result

    if not dry_run and not (os.getenv("DASHSCOPE_API_KEY") or os.getenv("ALIBABA_API_KEY")):
        result = {
            "run_id": run_id,
            "status": "llm_key_missing",
            "input_count": len(queue_rows),
            "updated_count": 0,
            "llm_success_count": 0,
            "llm_failed_count": 0,
            "duration_sec": round(time.time() - start_ts, 3),
        }
        _insert_run_log(supabase, run_id=run_id, payload=result)
        return result

    client = LLMClient()
    success = 0
    failed = 0
    errors: List[str] = []

    for row in queue_rows:
        queue_id = _safe_int(row.get("id"), 0)
        ticker = str(row.get("ticker") or "").upper().strip()
        prev_retry = _safe_int(row.get("retry_count"), 0)
        if queue_id <= 0 or not ticker:
            continue

        profile_row = _load_profile_row(supabase, ticker)
        if not profile_row:
            _mark_queue_failed(
                supabase,
                queue_id=queue_id,
                run_id=run_id,
                prev_retry_count=prev_retry,
                message="profile_not_found",
            )
            failed += 1
            continue

        if not dry_run:
            _mark_queue_running(supabase, queue_id=queue_id, run_id=run_id)

        prompt = _build_prompt(profile_row)
        try:
            if dry_run:
                summary = str(profile_row.get("summary_cn") or "").strip() or "dry-run summary"
                score = max(0.8, _safe_float(profile_row.get("quality_score"), 0.8))
            else:
                payload = client.summarize(prompt=prompt, use_cache=False)
                summary, score = _parse_llm_payload(payload)
                _update_profile_row(
                    supabase=supabase,
                    ticker=ticker,
                    run_id=run_id,
                    summary=summary,
                    score=score,
                )
                supabase.table("stock_ticker_profile_enrich_queue_v1").update(
                    {
                        "status": "done",
                        "last_error": "",
                        "next_retry_at": None,
                        "run_id": run_id,
                        "as_of": _now_iso(),
                    }
                ).eq("id", queue_id).execute()

            success += 1
            logger.info(
                "[PROFILE_ENRICH_PROGRESS] ticker=%s idx=%s/%s success=%s failed=%s",
                ticker,
                success + failed,
                len(queue_rows),
                success,
                failed,
            )
        except Exception as exc:
            failed += 1
            err = str(exc)[:180]
            errors.append(f"{ticker}:{err}")
            if not dry_run:
                _mark_queue_failed(
                    supabase=supabase,
                    queue_id=queue_id,
                    run_id=run_id,
                    prev_retry_count=prev_retry,
                    message=err,
                )
            logger.warning("[PROFILE_ENRICH_FAILED] ticker=%s err=%s", ticker, err)

        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000)

    result = {
        "run_id": run_id,
        "status": "ok",
        "input_count": len(queue_rows),
        "updated_count": success,
        "llm_success_count": success,
        "llm_failed_count": failed,
        "error_summary": " | ".join(errors[:8]),
        "duration_sec": round(time.time() - start_ts, 3),
    }
    _insert_run_log(supabase, run_id=run_id, payload=result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StockOps P1 ticker profile enrich")
    parser.add_argument("--run-id", type=str, default="")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--sleep-ms", type=int, default=150)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_id = args.run_id.strip() or "ticker-profile-enrich-" + datetime.now(
        timezone.utc
    ).strftime("%Y%m%d%H%M%S")
    logger.info(
        "[PROFILE_ENRICH_START] run_id=%s limit=%s dry_run=%s",
        run_id,
        args.limit,
        args.dry_run,
    )
    result = run_enrich(
        run_id=run_id,
        limit=max(1, args.limit),
        sleep_ms=max(0, args.sleep_ms),
        dry_run=bool(args.dry_run),
    )
    logger.info("[PROFILE_ENRICH_RESULT] %s", result)


if __name__ == "__main__":
    main()
