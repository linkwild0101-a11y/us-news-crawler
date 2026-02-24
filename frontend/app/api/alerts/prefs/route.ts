import { createClient } from "@supabase/supabase-js";
import { NextRequest, NextResponse } from "next/server";

export const runtime = "edge";

interface PrefsPayload {
  user_id: string;
  enable_premarket: boolean;
  enable_postmarket: boolean;
  daily_alert_cap: number;
  quiet_hours_start: number;
  quiet_hours_end: number;
}

function readSupabaseConfig(): { url: string; key: string } | null {
  const url = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL || "";
  const key = process.env.SUPABASE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";
  if (!url || !key) {
    return null;
  }
  return { url, key };
}

function parsePayload(body: unknown): PrefsPayload | null {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return null;
  }
  const row = body as Record<string, unknown>;
  const userId = String(row.userId || "system").slice(0, 64).trim() || "system";
  const enablePremarket = Boolean(row.enablePremarket);
  const enablePostmarket = Boolean(row.enablePostmarket);
  const dailyCap = Number(row.dailyAlertCap || 20);
  const quietHoursStart = Number(row.quietHoursStart || 0);
  const quietHoursEnd = Number(row.quietHoursEnd || 0);
  if (!Number.isFinite(dailyCap)) {
    return null;
  }
  if (!Number.isFinite(quietHoursStart) || !Number.isFinite(quietHoursEnd)) {
    return null;
  }
  return {
    user_id: userId,
    enable_premarket: enablePremarket,
    enable_postmarket: enablePostmarket,
    daily_alert_cap: Math.max(1, Math.min(200, Math.round(dailyCap))),
    quiet_hours_start: Math.max(0, Math.min(23, Math.round(quietHoursStart))),
    quiet_hours_end: Math.max(0, Math.min(23, Math.round(quietHoursEnd)))
  };
}

export async function GET(): Promise<NextResponse> {
  const config = readSupabaseConfig();
  if (!config) {
    return NextResponse.json({ error: "supabase_config_missing" }, { status: 503 });
  }
  const client = createClient(config.url, config.key, {
    auth: { persistSession: false, autoRefreshToken: false }
  });

  const { data, error } = await client
    .from("stock_alert_user_prefs_v1")
    .select(
      "user_id,enable_premarket,enable_postmarket,daily_alert_cap,quiet_hours_start,"
      + "quiet_hours_end,watch_tickers,muted_signal_types"
    )
    .eq("is_active", true)
    .eq("user_id", "system")
    .order("updated_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error) {
    return NextResponse.json({ error: "read_failed" }, { status: 500 });
  }
  if (!data) {
    return NextResponse.json(
      {
        user_id: "system",
        enable_premarket: false,
        enable_postmarket: true,
        daily_alert_cap: 20,
        quiet_hours_start: 0,
        quiet_hours_end: 0,
        watch_tickers: [],
        muted_signal_types: []
      },
      { status: 200 }
    );
  }
  return NextResponse.json(data, { status: 200 });
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
    user_id: payload.user_id,
    enable_premarket: payload.enable_premarket,
    enable_postmarket: payload.enable_postmarket,
    daily_alert_cap: payload.daily_alert_cap,
    quiet_hours_start: payload.quiet_hours_start,
    quiet_hours_end: payload.quiet_hours_end,
    watch_tickers: [],
    muted_signal_types: [],
    run_id: `frontend-prefs-${Date.now()}`,
    as_of: nowIso,
    is_active: true
  };

  const { error } = await client
    .from("stock_alert_user_prefs_v1")
    .upsert(row, { onConflict: "user_id" });

  if (error) {
    return NextResponse.json({ error: "write_failed" }, { status: 500 });
  }
  return NextResponse.json({ ok: true, prefs: row }, { status: 200 });
}
