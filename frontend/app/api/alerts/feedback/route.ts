import { createClient } from "@supabase/supabase-js";
import { NextRequest, NextResponse } from "next/server";

export const runtime = "edge";

interface FeedbackPayload {
  alertId: number;
  label: "useful" | "noise";
  reason?: string;
  userId?: string;
}

function readSupabaseConfig(): { url: string; key: string } | null {
  const url = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL || "";
  const key = process.env.SUPABASE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";
  if (!url || !key) {
    return null;
  }
  return { url, key };
}

function parsePayload(body: unknown): FeedbackPayload | null {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return null;
  }
  const row = body as Record<string, unknown>;
  const alertId = Number(row.alertId || 0);
  const labelText = String(row.label || "").toLowerCase();
  if (!Number.isFinite(alertId) || alertId <= 0) {
    return null;
  }
  if (labelText !== "useful" && labelText !== "noise") {
    return null;
  }
  const reason = String(row.reason || "").slice(0, 240);
  const userId = String(row.userId || "system").slice(0, 64) || "system";
  return {
    alertId,
    label: labelText,
    reason,
    userId
  };
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const config = readSupabaseConfig();
  if (!config) {
    return NextResponse.json(
      { error: "supabase_config_missing" },
      { status: 503 }
    );
  }

  const payload = parsePayload(await request.json().catch(() => null));
  if (!payload) {
    return NextResponse.json(
      { error: "bad_request" },
      { status: 400 }
    );
  }

  const client = createClient(config.url, config.key, {
    auth: { persistSession: false, autoRefreshToken: false }
  });

  const nowIso = new Date().toISOString();
  const runId = `frontend-feedback-${Date.now()}`;
  const { error } = await client
    .from("stock_alert_feedback_v1")
    .insert({
      alert_id: payload.alertId,
      user_id: payload.userId,
      label: payload.label,
      reason: payload.reason || "",
      payload: {
        source: "frontend",
        user_agent: request.headers.get("user-agent") || ""
      },
      run_id: runId,
      as_of: nowIso
    });

  if (error) {
    console.error("[ALERT_FEEDBACK_WRITE_FAILED]", error);
    return NextResponse.json(
      { error: "write_failed" },
      { status: 500 }
    );
  }

  return NextResponse.json({ ok: true });
}
