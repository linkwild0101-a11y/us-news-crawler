import { createClient } from "@supabase/supabase-js";
import { NextRequest, NextResponse } from "next/server";

export const runtime = "edge";

interface HoldingPayload {
  ticker: string;
  side: "LONG" | "SHORT";
  quantity: number;
  avg_cost: number;
  market_value: number;
  weight: number;
  notes: string;
}

function readSupabaseConfig(): { url: string; key: string } | null {
  const url = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL || "";
  const key = process.env.SUPABASE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";
  if (!url || !key) {
    return null;
  }
  return { url, key };
}

function parseHoldingPayload(body: unknown): HoldingPayload | null {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return null;
  }
  const row = body as Record<string, unknown>;
  const ticker = String(row.ticker || "").toUpperCase().trim();
  const sideText = String(row.side || "LONG").toUpperCase().trim();
  const side: "LONG" | "SHORT" = sideText === "SHORT" ? "SHORT" : "LONG";

  const quantity = Number(row.quantity || 0);
  const avgCost = Number(row.avgCost || 0);
  const marketValue = Number(row.marketValue || 0);
  const weight = Number(row.weight || 0);
  const notes = String(row.notes || "").trim().slice(0, 240);

  if (!ticker || ticker.length > 16) {
    return null;
  }
  if (!Number.isFinite(quantity) || quantity < 0) {
    return null;
  }
  if (!Number.isFinite(avgCost) || avgCost < 0) {
    return null;
  }
  if (!Number.isFinite(marketValue) || marketValue < 0) {
    return null;
  }
  if (!Number.isFinite(weight) || weight < -1 || weight > 1) {
    return null;
  }

  return {
    ticker,
    side,
    quantity,
    avg_cost: avgCost,
    market_value: marketValue,
    weight,
    notes
  };
}

function parseDeletePayload(body: unknown): { id: number } | null {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return null;
  }
  const row = body as Record<string, unknown>;
  const id = Number(row.id || 0);
  if (!Number.isFinite(id) || id <= 0) {
    return null;
  }
  return { id };
}

async function ensureDefaultPortfolio(client: any): Promise<number> {
  const { data: existingRows, error: existingError } = await client
    .from("stock_portfolios_v1")
    .select("id")
    .eq("is_active", true)
    .eq("user_id", "system")
    .eq("portfolio_key", "default")
    .order("updated_at", { ascending: false })
    .limit(1);
  if (existingError) {
    throw existingError;
  }

  const existingList = (existingRows || []) as Array<Record<string, unknown>>;
  const existingId = Number(existingList[0]?.id || 0);
  if (existingId > 0) {
    return existingId;
  }

  const nowIso = new Date().toISOString();
  const { error: insertError } = await client.from("stock_portfolios_v1").upsert(
    {
      user_id: "system",
      portfolio_key: "default",
      display_name: "Default Portfolio",
      base_currency: "USD",
      risk_profile: "balanced",
      max_position_weight: 0.2,
      max_gross_exposure: 1,
      max_single_name_risk: 0.08,
      metadata: { source: "frontend" },
      run_id: `frontend-holdings-${Date.now()}`,
      as_of: nowIso,
      is_active: true
    },
    { onConflict: "user_id,portfolio_key" }
  );
  if (insertError) {
    throw insertError;
  }

  const { data: latestRows, error: latestError } = await client
    .from("stock_portfolios_v1")
    .select("id")
    .eq("is_active", true)
    .eq("user_id", "system")
    .eq("portfolio_key", "default")
    .order("updated_at", { ascending: false })
    .limit(1);
  if (latestError) {
    throw latestError;
  }

  const latestList = (latestRows || []) as Array<Record<string, unknown>>;
  const latestId = Number(latestList[0]?.id || 0);
  if (latestId <= 0) {
    throw new Error("portfolio_not_ready");
  }
  return latestId;
}

async function listHoldings(
  client: any,
  portfolioId: number
): Promise<Array<Record<string, unknown>>> {
  const { data, error } = await client
    .from("stock_portfolio_holdings_v1")
    .select(
      "id,portfolio_id,user_id,ticker,side,quantity,avg_cost,market_value,"
      + "weight,notes,updated_at"
    )
    .eq("is_active", true)
    .eq("portfolio_id", portfolioId)
    .order("updated_at", { ascending: false })
    .limit(400);
  if (error) {
    throw error;
  }
  return (data || []) as Array<Record<string, unknown>>;
}

export async function GET(): Promise<NextResponse> {
  const config = readSupabaseConfig();
  if (!config) {
    return NextResponse.json({ error: "supabase_config_missing" }, { status: 503 });
  }

  const client = createClient(config.url, config.key, {
    auth: { persistSession: false, autoRefreshToken: false }
  });

  try {
    const portfolioId = await ensureDefaultPortfolio(client);
    const items = await listHoldings(client, portfolioId);
    return NextResponse.json({ ok: true, portfolio_id: portfolioId, items }, { status: 200 });
  } catch (error) {
    console.error("[PORTFOLIO_HOLDINGS_GET_FAILED]", error);
    return NextResponse.json({ error: "read_failed" }, { status: 500 });
  }
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const config = readSupabaseConfig();
  if (!config) {
    return NextResponse.json({ error: "supabase_config_missing" }, { status: 503 });
  }

  const payload = parseHoldingPayload(await request.json().catch(() => null));
  if (!payload) {
    return NextResponse.json({ error: "bad_request" }, { status: 400 });
  }

  const client = createClient(config.url, config.key, {
    auth: { persistSession: false, autoRefreshToken: false }
  });

  try {
    const portfolioId = await ensureDefaultPortfolio(client);
    const nowIso = new Date().toISOString();
    const upsertRow = {
      portfolio_id: portfolioId,
      user_id: "system",
      ticker: payload.ticker,
      side: payload.side,
      quantity: payload.quantity,
      avg_cost: payload.avg_cost,
      market_value: payload.market_value,
      weight: payload.weight,
      notes: payload.notes,
      tags: [],
      run_id: `frontend-holdings-${Date.now()}`,
      as_of: nowIso,
      is_active: true
    };

    const { error: writeError } = await client
      .from("stock_portfolio_holdings_v1")
      .upsert(upsertRow, { onConflict: "portfolio_id,ticker,side" });

    if (writeError) {
      throw writeError;
    }

    const items = await listHoldings(client, portfolioId);
    return NextResponse.json({ ok: true, portfolio_id: portfolioId, items }, { status: 200 });
  } catch (error) {
    console.error("[PORTFOLIO_HOLDINGS_WRITE_FAILED]", error);
    return NextResponse.json({ error: "write_failed" }, { status: 500 });
  }
}

export async function DELETE(request: NextRequest): Promise<NextResponse> {
  const config = readSupabaseConfig();
  if (!config) {
    return NextResponse.json({ error: "supabase_config_missing" }, { status: 503 });
  }

  const payload = parseDeletePayload(await request.json().catch(() => null));
  if (!payload) {
    return NextResponse.json({ error: "bad_request" }, { status: 400 });
  }

  const client = createClient(config.url, config.key, {
    auth: { persistSession: false, autoRefreshToken: false }
  });

  try {
    const portfolioId = await ensureDefaultPortfolio(client);
    const { error: updateError } = await client
      .from("stock_portfolio_holdings_v1")
      .update({
        is_active: false,
        run_id: `frontend-holdings-delete-${Date.now()}`,
        as_of: new Date().toISOString()
      })
      .eq("id", payload.id)
      .eq("portfolio_id", portfolioId)
      .eq("user_id", "system");

    if (updateError) {
      throw updateError;
    }

    const items = await listHoldings(client, portfolioId);
    return NextResponse.json({ ok: true, portfolio_id: portfolioId, items }, { status: 200 });
  } catch (error) {
    console.error("[PORTFOLIO_HOLDINGS_DELETE_FAILED]", error);
    return NextResponse.json({ error: "delete_failed" }, { status: 500 });
  }
}
