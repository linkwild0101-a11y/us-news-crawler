#!/usr/bin/env python3
"""StockOps P1 ticker 中文简介批量补全脚本。"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import os
import threading
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

_thread_local = threading.local()

_REASON_PRIORITY: Dict[str, int] = {
    "low_quality": 0,
    "missing_summary": 1,
    "new_symbol": 2,
}

_PRIORITY_SOURCES = {"portfolio", "watchlist", "recent_signal"}


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
    now_iso = _now_iso()
    base = (
        supabase.table("stock_ticker_profile_enrich_queue_v1")
        .select("id,ticker,reason,retry_count,next_retry_at")
        .eq("is_active", True)
        .in_("status", ["pending", "failed"])
        .order("updated_at", desc=False)
        .limit(limit)
    )
    # 仅拉取可立即重试的 failed 记录，避免同一错误高频重试。
    try:
        data = base.or_(f"next_retry_at.is.null,next_retry_at.lte.{now_iso}").execute().data or []
    except Exception:
        data = base.execute().data or []
    return data


def _mark_queue_running(supabase, queue_id: int, run_id: str) -> None:
    supabase.table("stock_ticker_profile_enrich_queue_v1").update(
        {
            "status": "running",
            "run_id": run_id,
            "as_of": _now_iso(),
        }
    ).eq("id", queue_id).execute()


def _mark_queue_done(supabase, queue_id: int, run_id: str, note: str = "") -> None:
    supabase.table("stock_ticker_profile_enrich_queue_v1").update(
        {
            "status": "done",
            "last_error": note[:240],
            "next_retry_at": None,
            "run_id": run_id,
            "as_of": _now_iso(),
        }
    ).eq("id", queue_id).execute()


def _load_priority_tickers(supabase, limit: int = 5000) -> List[str]:
    if not _table_available(supabase, "stock_universe_members_v1"):
        return []
    try:
        rows = (
            supabase.table("stock_universe_members_v1")
            .select("ticker,source_type")
            .eq("is_active", True)
            .in_("source_type", sorted(_PRIORITY_SOURCES))
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        logger.warning("[PROFILE_ENRICH_PRIORITY_LOAD_FAILED] err=%s", str(exc)[:140])
        return []

    tickers = {
        str(row.get("ticker") or "").upper().strip()
        for row in rows
        if str(row.get("ticker") or "").strip()
    }
    return sorted(tickers)


def _get_worker_supabase():
    client = getattr(_thread_local, "supabase", None)
    if client is None:
        client = _init_supabase()
        setattr(_thread_local, "supabase", client)
    return client


def _get_worker_llm_client() -> LLMClient:
    client = getattr(_thread_local, "llm_client", None)
    if client is None:
        client = LLMClient()
        setattr(_thread_local, "llm_client", client)
    return client


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
        '{"summary_cn":"", "quality_score":0.0, "asset_type":"", "sector":"", "industry":""}。'
        "summary_cn 要求：\n"
        "1) 使用简体中文，20-60字；\n"
        "2) 客观描述该标的业务属性与需关注变量；\n"
        "3) 禁止任何投资建议、保证收益、夸张措辞；\n"
        "4) asset_type 仅允许: equity/etf/index/macro/unknown；\n"
        "5) sector 与 industry 用英文常用行业词（如 Technology, Semiconductor, Gold ETF）；\n"
        "6) 只输出 JSON，不要额外文本。\n\n"
        f"ticker={ticker}\n"
        f"display_name={display_name}\n"
        f"asset_type={asset_type}\n"
        f"sector={sector}\n"
        f"industry={industry}\n"
        f"existing_summary={existing_summary}\n"
    )


def _parse_llm_payload(payload: Dict[str, Any], row: Dict[str, Any]) -> Tuple[str, float, str, str, str]:
    summary = str(payload.get("summary_cn") or "").strip()
    score = max(0.0, min(1.0, _safe_float(payload.get("quality_score"), 0.8)))
    asset_type = str(payload.get("asset_type") or row.get("asset_type") or "unknown").strip().lower()
    if asset_type not in {"equity", "etf", "index", "macro", "unknown"}:
        asset_type = str(row.get("asset_type") or "unknown").strip().lower() or "unknown"
    sector = str(payload.get("sector") or row.get("sector") or "Unknown").strip()[:64] or "Unknown"
    industry = str(payload.get("industry") or row.get("industry") or "Unknown").strip()[:64] or "Unknown"
    if not summary:
        summary = "该标的与美股主题相关，建议结合行业景气与财务数据持续跟踪。"
        score = max(score, 0.65)
    if len(summary) > 300:
        summary = summary[:300]
    return summary, score, asset_type, sector, industry


def _update_profile_row(
    supabase,
    ticker: str,
    run_id: str,
    summary: str,
    score: float,
    asset_type: str,
    sector: str,
    industry: str,
) -> None:
    now_iso = _now_iso()
    payload = {
        "summary_cn": summary,
        "summary_source": "llm",
        "quality_score": score,
        "asset_type": asset_type,
        "sector": sector,
        "industry": industry,
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


def _process_queue_item(
    row: Dict[str, Any],
    run_id: str,
    dry_run: bool,
    sleep_ms: int,
) -> Dict[str, str]:
    supabase = _get_worker_supabase()
    queue_id = _safe_int(row.get("id"), 0)
    ticker = str(row.get("ticker") or "").upper().strip()
    prev_retry = _safe_int(row.get("retry_count"), 0)
    if queue_id <= 0 or not ticker:
        return {"status": "failed", "ticker": ticker or "UNKNOWN", "error": "bad_queue_row"}

    profile_row = _load_profile_row(supabase, ticker)
    if not profile_row:
        if not dry_run:
            _mark_queue_failed(
                supabase,
                queue_id=queue_id,
                run_id=run_id,
                prev_retry_count=prev_retry,
                message="profile_not_found",
            )
        return {"status": "failed", "ticker": ticker, "error": "profile_not_found"}

    if not dry_run:
        _mark_queue_running(supabase, queue_id=queue_id, run_id=run_id)

    prompt = _build_prompt(profile_row)
    try:
        if dry_run:
            summary = str(profile_row.get("summary_cn") or "").strip() or "dry-run summary"
            score = max(0.8, _safe_float(profile_row.get("quality_score"), 0.8))
            asset_type = str(profile_row.get("asset_type") or "unknown").strip().lower() or "unknown"
            sector = str(profile_row.get("sector") or "Unknown").strip() or "Unknown"
            industry = str(profile_row.get("industry") or "Unknown").strip() or "Unknown"
        else:
            llm_client = _get_worker_llm_client()
            payload = llm_client.summarize(prompt=prompt, use_cache=False)
            summary, score, asset_type, sector, industry = _parse_llm_payload(payload, row=profile_row)
            _update_profile_row(
                supabase=supabase,
                ticker=ticker,
                run_id=run_id,
                summary=summary,
                score=score,
                asset_type=asset_type,
                sector=sector,
                industry=industry,
            )
            _mark_queue_done(supabase=supabase, queue_id=queue_id, run_id=run_id)

        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000)
        return {"status": "success", "ticker": ticker, "error": ""}
    except Exception as exc:
        err = str(exc)[:180]
        if not dry_run:
            _mark_queue_failed(
                supabase=supabase,
                queue_id=queue_id,
                run_id=run_id,
                prev_retry_count=prev_retry,
                message=err,
            )
        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000)
        return {"status": "failed", "ticker": ticker, "error": err}


def run_enrich(
    run_id: str,
    limit: int,
    sleep_ms: int,
    dry_run: bool,
    workers: int,
    llm_limit: int,
    enrich_new_symbols: bool,
    auto_complete_skipped: bool,
) -> Dict[str, Any]:
    """批量消费队列并补全 ticker 中文简介。"""
    start_ts = time.time()
    supabase = _init_supabase()

    if not _table_available(supabase, "stock_ticker_profile_enrich_queue_v1"):
        return {
            "run_id": run_id,
            "status": "queue_missing",
            "input_count": 0,
            "llm_target_count": 0,
            "skipped_new_symbol_count": 0,
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
            "llm_target_count": 0,
            "skipped_new_symbol_count": 0,
            "updated_count": 0,
            "llm_success_count": 0,
            "llm_failed_count": 0,
            "duration_sec": round(time.time() - start_ts, 3),
        }
        _insert_run_log(supabase, run_id=run_id, payload=result)
        return result

    priority_tickers = set(_load_priority_tickers(supabase=supabase, limit=8000))
    llm_rows: List[Dict[str, Any]] = []
    skipped_rows: List[Dict[str, Any]] = []
    for row in queue_rows:
        ticker = str(row.get("ticker") or "").upper().strip()
        reason = str(row.get("reason") or "")
        if (
            not enrich_new_symbols
            and reason == "new_symbol"
            and ticker
            and ticker not in priority_tickers
        ):
            skipped_rows.append(row)
            continue
        llm_rows.append(row)

    llm_rows.sort(
        key=lambda row: (
            0 if str(row.get("ticker") or "").upper().strip() in priority_tickers else 1,
            _REASON_PRIORITY.get(str(row.get("reason") or ""), 9),
            _safe_int(row.get("retry_count"), 0),
            str(row.get("ticker") or "").upper().strip(),
        )
    )

    if llm_limit > 0:
        llm_rows = llm_rows[:llm_limit]

    if not dry_run and not (os.getenv("DASHSCOPE_API_KEY") or os.getenv("ALIBABA_API_KEY")):
        result = {
            "run_id": run_id,
            "status": "llm_key_missing",
            "input_count": len(queue_rows),
            "llm_target_count": len(llm_rows),
            "skipped_new_symbol_count": len(skipped_rows),
            "updated_count": 0,
            "llm_success_count": 0,
            "llm_failed_count": 0,
            "duration_sec": round(time.time() - start_ts, 3),
        }
        _insert_run_log(supabase, run_id=run_id, payload=result)
        return result

    skipped_done = 0
    if auto_complete_skipped and not dry_run:
        for row in skipped_rows:
            queue_id = _safe_int(row.get("id"), 0)
            if queue_id <= 0:
                continue
            _mark_queue_done(
                supabase=supabase,
                queue_id=queue_id,
                run_id=run_id,
                note="auto_completed_template",
            )
            skipped_done += 1

    success = 0
    failed = 0
    errors: List[str] = []

    if llm_rows:
        max_workers = max(1, workers)
        step_start_ts = time.time()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    _process_queue_item,
                    row,
                    run_id,
                    dry_run,
                    sleep_ms,
                )
                for row in llm_rows
            ]

            completed = 0
            for future in as_completed(futures):
                completed += 1
                try:
                    item = future.result()
                except Exception as exc:
                    failed += 1
                    errors.append(f"INTERNAL:{str(exc)[:180]}")
                    item = {"status": "failed", "ticker": "UNKNOWN", "error": str(exc)[:180]}

                if item.get("status") == "success":
                    success += 1
                else:
                    failed += 1
                    ticker = str(item.get("ticker") or "UNKNOWN")
                    err = str(item.get("error") or "failed")
                    errors.append(f"{ticker}:{err}")

                elapsed = max(0.001, time.time() - step_start_ts)
                avg_cost = elapsed / max(1, completed)
                eta_sec = max(0.0, (len(llm_rows) - completed) * avg_cost)
                if completed == 1 or completed % 10 == 0 or completed == len(llm_rows):
                    logger.info(
                        "[PROFILE_ENRICH_PROGRESS] idx=%s/%s success=%s failed=%s eta_min=%.1f",
                        completed,
                        len(llm_rows),
                        success,
                        failed,
                        eta_sec / 60.0,
                    )

    result = {
        "run_id": run_id,
        "status": "ok",
        "input_count": len(queue_rows),
        "llm_target_count": len(llm_rows),
        "skipped_new_symbol_count": len(skipped_rows),
        "auto_completed_count": skipped_done,
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
    parser.add_argument("--limit", type=int, default=1200)
    parser.add_argument("--sleep-ms", type=int, default=0)
    parser.add_argument("--workers", type=int, default=8, help="LLM 并行 worker 数")
    parser.add_argument("--llm-limit", type=int, default=120, help="单轮最多 LLM 处理数量，0 表示不限")
    parser.add_argument(
        "--enrich-new-symbols",
        action="store_true",
        help="是否对所有 new_symbol 执行 LLM（默认仅处理重点池）",
    )
    parser.add_argument(
        "--auto-complete-skipped",
        dest="auto_complete_skipped",
        action="store_true",
        help="将跳过的 new_symbol 自动标记为 done（默认开启）",
    )
    parser.add_argument(
        "--no-auto-complete-skipped",
        dest="auto_complete_skipped",
        action="store_false",
        help="跳过 new_symbol 时不改队列状态",
    )
    parser.set_defaults(auto_complete_skipped=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_id = args.run_id.strip() or "ticker-profile-enrich-" + datetime.now(
        timezone.utc
    ).strftime("%Y%m%d%H%M%S")
    logger.info(
        "[PROFILE_ENRICH_START] run_id=%s limit=%s workers=%s llm_limit=%s dry_run=%s",
        run_id,
        args.limit,
        args.workers,
        args.llm_limit,
        args.dry_run,
    )
    result = run_enrich(
        run_id=run_id,
        limit=max(1, args.limit),
        sleep_ms=max(0, args.sleep_ms),
        dry_run=bool(args.dry_run),
        workers=max(1, args.workers),
        llm_limit=max(0, args.llm_limit),
        enrich_new_symbols=bool(args.enrich_new_symbols),
        auto_complete_skipped=bool(args.auto_complete_skipped),
    )
    logger.info("[PROFILE_ENRICH_RESULT] %s", result)


if __name__ == "__main__":
    main()
