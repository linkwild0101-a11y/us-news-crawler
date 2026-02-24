"""StockOps FastAPI 旁路服务。"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from supabase import create_client

APP_VERSION = "0.1.0"

app = FastAPI(title="StockOps API", version=APP_VERSION)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _init_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_KEY missing")
    return create_client(url, key)


class HealthResponse(BaseModel):
    ok: bool
    service: str
    version: str
    ts_utc: str


class AlertItem(BaseModel):
    id: int
    user_id: str
    ticker: str
    signal_type: str
    signal_level: str
    alert_score: float
    side: str
    title: str
    why_now: str
    status: str
    created_at: str


class AlertsResponse(BaseModel):
    items: List[AlertItem]
    total: int


class FeedbackPayload(BaseModel):
    user_id: str = Field(default="system", max_length=64)
    label: str = Field(pattern="^(useful|noise)$")
    reason: Optional[str] = Field(default="", max_length=240)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        ok=True,
        service="stockops_api",
        version=APP_VERSION,
        ts_utc=_now_iso(),
    )


@app.get("/alerts", response_model=AlertsResponse)
def list_alerts(
    user_id: str = Query(default="system"),
    limit: int = Query(default=60, ge=1, le=300),
    status: Optional[str] = Query(default=None),
) -> AlertsResponse:
    try:
        supabase = _init_supabase()
        query = (
            supabase.table("stock_alert_events_v1")
            .select(
                "id,user_id,ticker,signal_type,signal_level,alert_score,"
                "side,title,why_now,status,created_at"
            )
            .eq("is_active", True)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        if status:
            query = query.eq("status", status)
        rows = query.execute().data or []
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"alerts_read_failed: {str(exc)[:120]}")

    items: List[AlertItem] = []
    for row in rows:
        items.append(
            AlertItem(
                id=_safe_int(row.get("id"), 0),
                user_id=str(row.get("user_id") or "system"),
                ticker=str(row.get("ticker") or "").upper(),
                signal_type=str(row.get("signal_type") or "opportunity"),
                signal_level=str(row.get("signal_level") or "L1"),
                alert_score=max(0.0, min(100.0, _safe_float(row.get("alert_score"), 0.0))),
                side=str(row.get("side") or "NEUTRAL"),
                title=str(row.get("title") or ""),
                why_now=str(row.get("why_now") or ""),
                status=str(row.get("status") or "pending"),
                created_at=str(row.get("created_at") or ""),
            )
        )

    return AlertsResponse(items=items, total=len(items))


@app.post("/alerts/{alert_id}/feedback")
def submit_feedback(alert_id: int, payload: FeedbackPayload) -> Dict[str, Any]:
    if alert_id <= 0:
        raise HTTPException(status_code=400, detail="invalid_alert_id")

    try:
        supabase = _init_supabase()
        row = {
            "alert_id": alert_id,
            "user_id": payload.user_id,
            "label": payload.label,
            "reason": payload.reason or "",
            "payload": {"source": "stockops_api"},
            "run_id": f"stockops-api-feedback-{int(datetime.now().timestamp())}",
            "as_of": _now_iso(),
        }
        result = supabase.table("stock_alert_feedback_v1").insert(row).execute()
        written = len(result.data or [])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"feedback_write_failed: {str(exc)[:120]}")

    return {
        "ok": True,
        "alert_id": alert_id,
        "written": written,
    }
