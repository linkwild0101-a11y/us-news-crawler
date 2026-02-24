import { createClient } from "@supabase/supabase-js";
import { NextRequest, NextResponse } from "next/server";

export const runtime = "edge";

interface OpenPayload {
  alertId: number;
  userId: string;
}

function readSupabaseConfig(): { url: string; key: string } | null {
  const url = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL || "";
  const key = process.env.SUPABASE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";
  if (!url || !key) {
    return null;
  }
  return { url, key };
}

function parsePayload(body: unknown): OpenPayload | null {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return null;
  }
  const row = body as Record<string, unknown>;
  const alertId = Number(row.alertId || 0);
  const userId = String(row.userId || "system").slice(0, 64).trim() || "system";
  if (!Number.isFinite(alertId) || alertId <= 0) {
    return null;
  }
  return {
    alertId,
    userId
  };
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const config = readSupabaseConfig();
  if (!config) {
    return NextResponse.json({ error: "supabase_config_missing" }, { status: 503 });
  }

  const payload = parsePayload(await request.json().catch(() => null));
  if (!payload) {
    return NextResponse.json({ error: "bad_request" }, { status: 400 });
  }

  const client = createClient(config.url, config.key, {
    auth: { persistSession: false, autoRefreshToken: false }
  });

  const nowIso = new Date().toISOString();
  const row = {
    alert_id: payload.alertId,
    user_id: payload.userId,
    source: "frontend",
    payload: {
      source: "frontend",
      user_agent: request.headers.get("user-agent") || ""
    },
    opened_at: nowIso,
    run_id: `frontend-open-${Date.now()}`,
    as_of: nowIso
  };

  const { error } = await client
    .from("stock_alert_open_events_v1")
    .upsert(row, { onConflict: "alert_id,user_id" });

  if (error) {
    console.error("[ALERT_OPEN_WRITE_FAILED]", error);
    return NextResponse.json({ error: "write_failed" }, { status: 500 });
  }

  return NextResponse.json({ ok: true });
}
