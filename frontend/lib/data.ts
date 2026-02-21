import { createClient, SupabaseClient } from "@supabase/supabase-js";

import {
  DashboardData,
  EntityRelationItem,
  HotCluster,
  MarketRegime,
  MarketSnapshot,
  OpportunityItem,
  RiskLevel,
  SentinelSignal,
  TickerSignalDigest
} from "@/lib/types";

const LEVEL_ORDER: Record<RiskLevel, number> = {
  L0: 0,
  L1: 1,
  L2: 2,
  L3: 3,
  L4: 4
};

const FALLBACK_TICKERS = ["SPY", "QQQ", "DIA", "IWM", "XLF", "XLK", "XLE", "XLV"];
const STOCK_TICKERS = new Set([
  "SPY",
  "QQQ",
  "DIA",
  "IWM",
  "VTI",
  "VOO",
  "XLF",
  "XLK",
  "XLE",
  "XLV",
  "XLI",
  "XLP",
  "XLY",
  "XLU",
  "XLRE",
  "SMH",
  "SOXX",
  "TLT",
  "DXY",
  "VIX",
  "AAPL",
  "MSFT",
  "NVDA",
  "AMZN",
  "GOOGL",
  "META",
  "TSLA"
]);
const STOCK_HINTS = [
  "美股",
  "纳斯达克",
  "納斯達克",
  "道琼斯",
  "道瓊斯",
  "标普",
  "標普",
  "华尔街",
  "華爾街",
  "ETF",
  "EARNINGS",
  "RATE CUT",
  "RATE HIKE",
  "FED",
  "FOMC",
  "TREASURY",
  "YIELD",
  "DXY",
  "VIX"
];
const STOCK_CLUSTER_HINTS = [
  "美股",
  "美國股市",
  "财报",
  "財報",
  "业绩",
  "業績",
  "股价",
  "股價",
  "估值",
  "加息",
  "降息",
  "纳斯达克",
  "納斯達克",
  "标普",
  "標普",
  "道琼斯",
  "道瓊斯",
  "华尔街",
  "華爾街",
  "ETF",
  "EARNINGS",
  "GUIDANCE",
  "IPO",
  "FED",
  "FOMC",
  "TREASURY",
  "YIELD"
];
const TICKER_PATTERN = /\b[A-Z]{2,5}\b/g;
const TRUE_VALUES = new Set(["1", "true", "yes", "on"]);

function readV2Enabled(): boolean {
  const raw = String(
    process.env.NEXT_PUBLIC_DASHBOARD_READ_V2
    || process.env.DASHBOARD_READ_V2
    || ""
  ).trim().toLowerCase();
  return TRUE_VALUES.has(raw);
}

function toIsoString(value: unknown): string {
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  return new Date().toISOString();
}

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function toScore(value: unknown): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return 0;
  }
  return Math.max(0, Math.min(1, parsed));
}

function toLevel(value: unknown): RiskLevel {
  const text = String(value || "L1").toUpperCase();
  if (text === "L0" || text === "L1" || text === "L2" || text === "L3" || text === "L4") {
    return text;
  }
  return "L1";
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => String(item || "").trim())
    .filter((item) => item.length > 0)
    .slice(0, 5);
}

function toCatalystArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => {
      if (typeof item === "string") {
        return item.trim();
      }
      if (!item || typeof item !== "object" || Array.isArray(item)) {
        return "";
      }
      const row = item as Record<string, unknown>;
      const eventType = String(row.event_type || "").trim();
      const count = Number(row.count || 0);
      if (!eventType) {
        return "";
      }
      if (count > 0) {
        return `${eventType} x${count}`;
      }
      return eventType;
    })
    .filter((item) => item.length > 0)
    .slice(0, 5);
}

function toNumberMap(value: unknown): Record<string, number> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  const result: Record<string, number> = {};
  for (const [key, raw] of Object.entries(value as Record<string, unknown>)) {
    const num = Number(raw);
    if (Number.isFinite(num)) {
      result[key] = num;
    }
  }
  return result;
}

function collectTickerTokens(text: string): string[] {
  const matches = text.toUpperCase().match(TICKER_PATTERN) || [];
  return matches.filter((token) => STOCK_TICKERS.has(token));
}

function textContainsStockHint(text: string): boolean {
  const upper = text.toUpperCase();
  return STOCK_HINTS.some((hint) => upper.includes(hint.toUpperCase()));
}

function isStockSignal(row: {
  sentinel_id: string;
  description: string;
  trigger_reasons: string[];
  details: unknown;
}): boolean {
  const details = typeof row.details === "object" && row.details ? row.details : {};
  const relatedTickers = Array.isArray((details as Record<string, unknown>).related_tickers)
    ? ((details as Record<string, unknown>).related_tickers as unknown[])
    : [];
  for (const item of relatedTickers) {
    if (STOCK_TICKERS.has(String(item || "").toUpperCase())) {
      return true;
    }
  }

  const payload = [row.sentinel_id, row.description, ...row.trigger_reasons].join(" ");
  if (collectTickerTokens(payload).length > 0) {
    return true;
  }
  return textContainsStockHint(payload);
}

function signalMentionsTicker(signal: SentinelSignal, tickerSet: Set<string>): boolean {
  const payload = `${signal.sentinel_id} ${signal.description} ${signal.trigger_reasons.join(" ")}`;
  const tokens = collectTickerTokens(payload);
  if (tokens.some((item) => tickerSet.has(item))) {
    return true;
  }
  return Array.from(tickerSet).some((ticker) => payload.toUpperCase().includes(ticker));
}

function isStockCluster(row: {
  primary_title: string;
  summary: string;
}): boolean {
  const payload = `${row.primary_title} ${row.summary}`;
  if (collectTickerTokens(payload).length > 0) {
    return true;
  }
  const upper = payload.toUpperCase();
  return STOCK_CLUSTER_HINTS.some((hint) => upper.includes(hint.toUpperCase()));
}

function isStockRelationText(text: string): boolean {
  if (collectTickerTokens(text).length > 0) {
    return true;
  }
  const upper = text.toUpperCase();
  return STOCK_CLUSTER_HINTS.some((hint) => upper.includes(hint.toUpperCase()));
}

function buildReadonlyClient(): SupabaseClient | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    return null;
  }
  return createClient(url, anonKey, {
    auth: {
      autoRefreshToken: false,
      persistSession: false
    },
    global: {
      headers: {
        "x-client-info": "us-monitor-mobile-frontend"
      }
    }
  });
}

function baseSnapshot(): MarketSnapshot {
  const now = new Date().toISOString();
  return {
    snapshot_date: now,
    spy: null,
    qqq: null,
    dia: null,
    vix: null,
    us10y: null,
    dxy: null,
    risk_level: "L1",
    daily_brief: "暂无美股聚合快照，已回退到股票相关信号视图。",
    updated_at: now
  };
}

function deriveBriefFromSignals(signals: SentinelSignal[]): string {
  if (!signals.length) {
    return "最近24小时暂无与美股相关的 L1-L4 告警。";
  }

  const high = signals.filter((item) => item.alert_level === "L4" || item.alert_level === "L3").length;
  const medium = signals.filter((item) => item.alert_level === "L2").length;
  const latest = signals[0]?.description || "监控系统已捕获新的风险线索。";

  if (high > 0) {
    return `最近24小时出现 ${high} 条美股高风险告警，建议优先关注 L3/L4。${latest}`;
  }
  if (medium > 0) {
    return `最近24小时出现 ${medium} 条美股中风险告警，建议持续跟踪。${latest}`;
  }
  return `系统已捕获 ${signals.length} 条美股低风险告警，市场情绪整体可控。${latest}`;
}

async function querySentinelSignals(client: SupabaseClient): Promise<SentinelSignal[]> {
  try {
    const { data, error } = await client
      .from("analysis_signals")
      .select(
        "id,cluster_id,sentinel_id,alert_level,risk_score,description,trigger_reasons,"
        + "evidence_links,details,created_at"
      )
      .eq("signal_type", "watchlist_alert")
      .order("created_at", { ascending: false })
      .limit(60);

    if (error) {
      throw error;
    }

    const rawRows = (data || []) as unknown as Array<Record<string, unknown>>;
    const rows = rawRows.map((row) => ({
      id: Number(row.id || 0),
      cluster_id: row.cluster_id === null || row.cluster_id === undefined ? null : Number(row.cluster_id),
      sentinel_id: String(row.sentinel_id || "unknown_sentinel"),
      alert_level: toLevel(row.alert_level),
      risk_score: toScore(row.risk_score),
      description: String(row.description || "哨兵告警"),
      trigger_reasons: toStringArray(row.trigger_reasons),
      evidence_links: toStringArray(row.evidence_links),
      details: row.details,
      created_at: toIsoString(row.created_at)
    }));

    return rows
      .filter((row) =>
        isStockSignal({
          sentinel_id: row.sentinel_id,
          description: row.description,
          trigger_reasons: row.trigger_reasons,
          details: row.details
        })
      )
      .slice(0, 24)
      .map(({ details: _details, ...signal }) => signal);
  } catch (error) {
    console.warn("[FRONTEND_SIGNAL_QUERY_FALLBACK]", error);
    return [];
  }
}

interface V2SnapshotRow {
  snapshot_time: string;
  market_brief: string;
  risk_badge: RiskLevel;
  as_of: string;
}

async function queryV2Signals(client: SupabaseClient): Promise<SentinelSignal[]> {
  try {
    const { data, error } = await client
      .from("stock_signals_v2")
      .select("id,ticker,level,signal_score,explanation,trigger_factors,source_event_ids,as_of")
      .eq("is_active", true)
      .order("signal_score", { ascending: false })
      .limit(30);

    if (error) {
      throw error;
    }

    const rows = (data || []) as unknown as Array<Record<string, unknown>>;
    return rows.map((row) => {
      const ticker = String(row.ticker || "").toUpperCase();
      return {
        id: Number(row.id || 0),
        cluster_id: null,
        sentinel_id: `stock_v2:${ticker || "UNKNOWN"}`,
        alert_level: toLevel(row.level),
        risk_score: Math.max(0, Math.min(1, Number(row.signal_score || 0) / 100)),
        description: String(row.explanation || `${ticker} Stock V2 信号`),
        trigger_reasons: toCatalystArray(row.trigger_factors),
        evidence_links: Array.isArray(row.source_event_ids)
          ? row.source_event_ids
            .map((item) => Number(item || 0))
            .filter((item) => item > 0)
            .slice(0, 5)
            .map((id) => `event:${id}`)
          : [],
        created_at: toIsoString(row.as_of)
      };
    });
  } catch (error) {
    console.warn("[FRONTEND_V2_SIGNAL_FALLBACK]", error);
    return [];
  }
}

async function queryV2Opportunities(client: SupabaseClient): Promise<OpportunityItem[]> {
  try {
    const { data, error } = await client
      .from("stock_opportunities_v2")
      .select(
        "id,ticker,side,horizon,opportunity_score,confidence,risk_level,why_now,invalid_if,"
        + "catalysts,source_signal_ids,source_event_ids,expires_at,as_of"
      )
      .eq("is_active", true)
      .order("opportunity_score", { ascending: false })
      .limit(40);

    if (error) {
      throw error;
    }

    const rows = (data || []) as unknown as Array<Record<string, unknown>>;
    const now = new Date().toISOString();
    return rows
      .map((row) => {
        const side: OpportunityItem["side"] = String(row.side || "LONG").toUpperCase() === "SHORT"
          ? "SHORT"
          : "LONG";
        const horizon: OpportunityItem["horizon"] = String(row.horizon || "A").toUpperCase() === "B"
          ? "B"
          : "A";
        return {
          id: Number(row.id || 0),
          ticker: String(row.ticker || "").toUpperCase(),
          side,
          horizon,
          opportunity_score: Number(row.opportunity_score || 0),
          confidence: toScore(row.confidence),
          risk_level: toLevel(row.risk_level),
          why_now: String(row.why_now || ""),
          invalid_if: String(row.invalid_if || ""),
          catalysts: toCatalystArray(row.catalysts),
          factor_breakdown: {},
          source_signal_ids: Array.isArray(row.source_signal_ids)
            ? row.source_signal_ids
              .map((item: unknown) => Number(item || 0))
              .filter((item) => item > 0)
            : [],
          source_cluster_ids: [],
          expires_at: toIsoString(row.expires_at),
          as_of: toIsoString(row.as_of)
        };
      })
      .filter((item) => item.ticker && item.expires_at >= now);
  } catch (error) {
    console.warn("[FRONTEND_V2_OPPORTUNITY_FALLBACK]", error);
    return [];
  }
}

async function queryV2Regime(client: SupabaseClient): Promise<MarketRegime | null> {
  try {
    const { data, error } = await client
      .from("stock_market_regime_v2")
      .select("regime_date,risk_state,vol_state,liquidity_state,regime_score,summary,as_of")
      .eq("is_active", true)
      .order("as_of", { ascending: false })
      .limit(1)
      .maybeSingle();

    if (error || !data) {
      if (error) {
        throw error;
      }
      return null;
    }

    return {
      regime_date: toIsoString(data.regime_date),
      risk_state: String(data.risk_state || "neutral"),
      vol_state: String(data.vol_state || "mid_vol"),
      liquidity_state: String(data.liquidity_state || "neutral"),
      regime_score: Number(data.regime_score || 0),
      summary: String(data.summary || "")
    };
  } catch (error) {
    console.warn("[FRONTEND_V2_REGIME_FALLBACK]", error);
    return null;
  }
}

async function queryV2Snapshot(client: SupabaseClient): Promise<V2SnapshotRow | null> {
  try {
    const { data, error } = await client
      .from("stock_dashboard_snapshot_v2")
      .select("snapshot_time,market_brief,risk_badge,as_of")
      .eq("is_active", true)
      .order("snapshot_time", { ascending: false })
      .limit(1)
      .maybeSingle();

    if (error || !data) {
      if (error) {
        throw error;
      }
      return null;
    }

    return {
      snapshot_time: toIsoString(data.snapshot_time),
      market_brief: String(data.market_brief || ""),
      risk_badge: toLevel(data.risk_badge),
      as_of: toIsoString(data.as_of)
    };
  } catch (error) {
    console.warn("[FRONTEND_V2_SNAPSHOT_FALLBACK]", error);
    return null;
  }
}

function calculateTopRisk(signals: SentinelSignal[]): RiskLevel {
  return signals.reduce<RiskLevel>((maxLevel, signal) => {
    return LEVEL_ORDER[signal.alert_level] > LEVEL_ORDER[maxLevel] ? signal.alert_level : maxLevel;
  }, "L1");
}

async function queryOpportunities(
  client: SupabaseClient,
  tickerDigest: TickerSignalDigest[],
  signals: SentinelSignal[]
): Promise<OpportunityItem[]> {
  try {
    const { data, error } = await client
      .from("opportunities")
      .select(
        "id,ticker,side,horizon,opportunity_score,confidence,risk_level,why_now,invalid_if,"
        + "catalysts,factor_breakdown,source_signal_ids,source_cluster_ids,expires_at,as_of"
      )
      .order("opportunity_score", { ascending: false })
      .limit(30);

    if (error) {
      throw error;
    }

    const rawRows = (data || []) as unknown as Array<Record<string, unknown>>;
    const rows: OpportunityItem[] = rawRows.map((row) => {
      const side: OpportunityItem["side"] = String(row.side || "LONG").toUpperCase() === "SHORT"
        ? "SHORT"
        : "LONG";
      const horizon: OpportunityItem["horizon"] = String(row.horizon || "A").toUpperCase() === "B"
        ? "B"
        : "A";
      return {
        id: Number(row.id || 0),
        ticker: String(row.ticker || "").toUpperCase(),
        side,
        horizon,
        opportunity_score: Number(row.opportunity_score || 0),
        confidence: toScore(row.confidence),
        risk_level: toLevel(row.risk_level),
        why_now: String(row.why_now || ""),
        invalid_if: String(row.invalid_if || ""),
        catalysts: toStringArray(row.catalysts),
        factor_breakdown: toNumberMap(row.factor_breakdown),
        source_signal_ids: Array.isArray(row.source_signal_ids)
          ? row.source_signal_ids
            .map((item: unknown) => Number(item || 0))
            .filter((item) => item > 0)
          : [],
        source_cluster_ids: Array.isArray(row.source_cluster_ids)
          ? row.source_cluster_ids
            .map((item: unknown) => Number(item || 0))
            .filter((item) => item > 0)
          : [],
        expires_at: toIsoString(row.expires_at),
        as_of: toIsoString(row.as_of)
      };
    });

    const now = new Date().toISOString();
    return rows.filter((item) => item.ticker && item.expires_at >= now);
  } catch (error) {
    console.warn("[FRONTEND_OPPORTUNITY_FALLBACK]", error);
    const map = new Map(tickerDigest.map((item) => [item.ticker, item]));
    return FALLBACK_TICKERS.slice(0, 8).map((ticker, idx) => {
      const digest = map.get(ticker);
      const signalCount = digest?.signal_count_24h || 0;
      const side = idx % 3 === 0 ? "SHORT" : "LONG";
      return {
        id: idx + 1,
        ticker,
        side,
        horizon: "A",
        opportunity_score: Math.max(20, Math.min(85, 45 + signalCount * 5)),
        confidence: Math.max(0.45, Math.min(0.8, 0.5 + signalCount * 0.04)),
        risk_level: digest?.risk_level || "L1",
        why_now: signalCount
          ? `${ticker} 近24h出现 ${signalCount} 条相关信号，短期存在交易窗口。`
          : `${ticker} 暂无明确信号，建议低权重跟踪。`,
        invalid_if: side === "LONG"
          ? "若风险偏好转弱且相关信号清零，机会失效。"
          : "若风险偏好快速修复且负面信号消失，机会失效。",
        catalysts: signals
          .filter((item) => item.description.toUpperCase().includes(ticker))
          .slice(0, 2)
          .map((item) => item.description),
        factor_breakdown: {},
        source_signal_ids: [],
        source_cluster_ids: [],
        expires_at: new Date(Date.now() + 48 * 3600 * 1000).toISOString(),
        as_of: new Date().toISOString()
      };
    });
  }
}

async function queryMarketRegime(client: SupabaseClient): Promise<MarketRegime | null> {
  try {
    const { data, error } = await client
      .from("market_regime_daily")
      .select("regime_date,risk_state,vol_state,liquidity_state,regime_score,summary")
      .order("regime_date", { ascending: false })
      .limit(1)
      .maybeSingle();

    if (error || !data) {
      if (error) {
        throw error;
      }
      return null;
    }

    return {
      regime_date: toIsoString(data.regime_date),
      risk_state: String(data.risk_state || "neutral"),
      vol_state: String(data.vol_state || "mid_vol"),
      liquidity_state: String(data.liquidity_state || "neutral"),
      regime_score: Number(data.regime_score || 0),
      summary: String(data.summary || "")
    };
  } catch (error) {
    console.warn("[FRONTEND_REGIME_FALLBACK]", error);
    return null;
  }
}

async function queryMarketSnapshot(
  client: SupabaseClient,
  signals: SentinelSignal[]
): Promise<MarketSnapshot> {
  const derivedRisk = calculateTopRisk(signals);
  const derivedBrief = deriveBriefFromSignals(signals);

  try {
    const { data, error } = await client
      .from("market_snapshot_daily")
      .select(
        "snapshot_date,spy,qqq,dia,vix,us10y,dxy,risk_level,daily_brief,updated_at"
      )
      .order("snapshot_date", { ascending: false })
      .limit(1)
      .maybeSingle();

    if (error) {
      throw error;
    }

    if (!data) {
      const snapshot = baseSnapshot();
      snapshot.risk_level = derivedRisk;
      snapshot.daily_brief = derivedBrief;
      return snapshot;
    }

    return {
      snapshot_date: toIsoString(data.snapshot_date),
      spy: toNumber(data.spy),
      qqq: toNumber(data.qqq),
      dia: toNumber(data.dia),
      vix: toNumber(data.vix),
      us10y: toNumber(data.us10y),
      dxy: toNumber(data.dxy),
      risk_level: derivedRisk,
      daily_brief: derivedBrief,
      updated_at: toIsoString(data.updated_at)
    };
  } catch (error) {
    console.warn("[FRONTEND_MARKET_SNAPSHOT_FALLBACK]", error);
    const snapshot = baseSnapshot();
    snapshot.risk_level = derivedRisk;
    snapshot.daily_brief = derivedBrief;
    return snapshot;
  }
}

async function queryTickerDigest(
  client: SupabaseClient,
  signals: SentinelSignal[]
): Promise<TickerSignalDigest[]> {
  try {
    const { data, error } = await client
      .from("ticker_signal_digest")
      .select(
        "ticker,signal_count_24h,related_cluster_count_24h,risk_level,top_sentinel_levels,updated_at"
      )
      .order("signal_count_24h", { ascending: false })
      .limit(20);

    if (error) {
      throw error;
    }

    const rows = (data || []).map((row) => ({
      ticker: String(row.ticker || "").toUpperCase(),
      signal_count_24h: Number(row.signal_count_24h || 0),
      related_cluster_count_24h: Number(row.related_cluster_count_24h || 0),
      risk_level: toLevel(row.risk_level),
      top_sentinel_levels: toStringArray(row.top_sentinel_levels),
      updated_at: toIsoString(row.updated_at)
    }));

    return rows.filter((item) => item.ticker.length > 0);
  } catch (error) {
    console.warn("[FRONTEND_TICKER_DIGEST_FALLBACK]", error);

    return FALLBACK_TICKERS.map((ticker) => {
      const matched = signals.filter((item) => item.description.toUpperCase().includes(ticker));
      const level = matched.length ? calculateTopRisk(matched) : "L1";
      return {
        ticker,
        signal_count_24h: matched.length,
        related_cluster_count_24h: matched.length,
        risk_level: level,
        top_sentinel_levels: matched.slice(0, 3).map((item) => item.alert_level),
        updated_at: new Date().toISOString()
      };
    });
  }
}

async function queryHotClusters(
  client: SupabaseClient,
  signals: SentinelSignal[],
  opportunities: OpportunityItem[]
): Promise<HotCluster[]> {
  const clusterFromOpp = opportunities.flatMap((item) => item.source_cluster_ids);
  const clusterFromSignal = signals
    .map((signal) => signal.cluster_id)
    .filter((clusterId): clusterId is number => typeof clusterId === "number" && clusterId > 0);
  const stockClusterIds = Array.from(new Set([...clusterFromOpp, ...clusterFromSignal]));

  const toCluster = (row: Record<string, unknown>): HotCluster => ({
    id: Number(row.id || 0),
    category: String(row.category || "unknown"),
    primary_title: String(row.primary_title || "Untitled"),
    summary: String(row.summary || "暂无摘要"),
    article_count: Number(row.article_count || 0),
    created_at: toIsoString(row.created_at)
  });

  try {
    if (stockClusterIds.length > 0) {
      const { data, error } = await client
        .from("analysis_clusters")
        .select("id,category,primary_title,summary,article_count,created_at")
        .in("id", stockClusterIds.slice(0, 40))
        .order("created_at", { ascending: false })
        .limit(20);

      if (error) {
        throw error;
      }

      return (data || []).map((row) => toCluster(row as Record<string, unknown>));
    }

    const { data, error } = await client
      .from("analysis_clusters")
      .select("id,category,primary_title,summary,article_count,created_at")
      .order("created_at", { ascending: false })
      .limit(60);

    if (error) {
      throw error;
    }

    return (data || [])
      .filter((row) =>
        isStockCluster({
          primary_title: String(row.primary_title || ""),
          summary: String(row.summary || "")
        })
      )
      .slice(0, 20)
      .map((row) => toCluster(row as Record<string, unknown>));
  } catch (error) {
    console.warn("[FRONTEND_CLUSTER_QUERY_FALLBACK]", error);
    return [];
  }
}

async function queryEntityRelations(client: SupabaseClient): Promise<EntityRelationItem[]> {
  try {
    const { data: relationRows, error: relationError } = await client
      .from("entity_relations")
      .select("id,entity1_id,entity2_id,relation_text,confidence,last_seen")
      .order("last_seen", { ascending: false })
      .limit(20);

    if (relationError) {
      throw relationError;
    }

    const uniqueEntityIds = new Set<number>();
    for (const row of relationRows || []) {
      if (row.entity1_id) {
        uniqueEntityIds.add(Number(row.entity1_id));
      }
      if (row.entity2_id) {
        uniqueEntityIds.add(Number(row.entity2_id));
      }
    }

    const ids = Array.from(uniqueEntityIds);
    let entityNameMap = new Map<number, string>();

    if (ids.length > 0) {
      const { data: entityRows, error: entityError } = await client
        .from("entities")
        .select("id,name")
        .in("id", ids);

      if (!entityError) {
        entityNameMap = new Map((entityRows || []).map((item) => [Number(item.id), String(item.name)]));
      }
    }

    return (relationRows || [])
      .map((row) => {
        const entity1Id = Number(row.entity1_id || 0);
        const entity2Id = Number(row.entity2_id || 0);
        return {
          id: Number(row.id || 0),
          entity1_name: entityNameMap.get(entity1Id) || `Entity#${entity1Id}`,
          entity2_name: entityNameMap.get(entity2Id) || `Entity#${entity2Id}`,
          relation_text: String(row.relation_text || "关联"),
          confidence: Number(row.confidence || 0),
          last_seen: toIsoString(row.last_seen)
        };
      })
      .filter((row) =>
        isStockRelationText(`${row.entity1_name} ${row.entity2_name} ${row.relation_text}`)
      );
  } catch (error) {
    console.warn("[FRONTEND_RELATION_QUERY_FALLBACK]", error);
    return [];
  }
}

function buildTickerDigestFromSignals(signals: SentinelSignal[]): TickerSignalDigest[] {
  const bucket = new Map<string, SentinelSignal[]>();
  for (const signal of signals) {
    const source = String(signal.sentinel_id || "");
    const ticker = source.includes(":") ? source.split(":")[1] : "";
    if (!ticker) {
      continue;
    }
    const items = bucket.get(ticker) || [];
    items.push(signal);
    bucket.set(ticker, items);
  }

  return Array.from(bucket.entries())
    .map(([ticker, rows]) => ({
      ticker,
      signal_count_24h: rows.length,
      related_cluster_count_24h: 0,
      risk_level: calculateTopRisk(rows),
      top_sentinel_levels: rows.slice(0, 3).map((item) => item.alert_level),
      updated_at: rows[0]?.created_at || new Date().toISOString()
    }))
    .sort((a, b) => b.signal_count_24h - a.signal_count_24h);
}

async function getDashboardDataFromV2(client: SupabaseClient): Promise<DashboardData | null> {
  const [sentinelSignals, opportunities, marketRegime, v2Snapshot] = await Promise.all([
    queryV2Signals(client),
    queryV2Opportunities(client),
    queryV2Regime(client),
    queryV2Snapshot(client)
  ]);

  if (!v2Snapshot && sentinelSignals.length === 0 && opportunities.length === 0) {
    return null;
  }

  const tickerDigest = buildTickerDigestFromSignals(sentinelSignals);
  const focusTickers = new Set(opportunities.map((item) => item.ticker));
  const filteredSignals = focusTickers.size
    ? sentinelSignals.filter((item) => signalMentionsTicker(item, focusTickers))
    : sentinelSignals;

  const [marketSnapshotRaw, hotClusters, relations] = await Promise.all([
    queryMarketSnapshot(client, filteredSignals),
    queryHotClusters(client, filteredSignals, opportunities),
    queryEntityRelations(client)
  ]);

  const marketSnapshot: MarketSnapshot = {
    ...marketSnapshotRaw,
    risk_level: v2Snapshot?.risk_badge || marketSnapshotRaw.risk_level,
    daily_brief: v2Snapshot?.market_brief || marketSnapshotRaw.daily_brief,
    updated_at: v2Snapshot?.as_of || marketSnapshotRaw.updated_at
  };

  const topOpportunityTime = opportunities[0]?.as_of || "";
  const topSignalTime = filteredSignals[0]?.created_at || "";
  const topClusterTime = hotClusters[0]?.created_at || "";
  const topRelationTime = relations[0]?.last_seen || "";

  return {
    opportunities,
    marketRegime,
    marketSnapshot,
    sentinelSignals: filteredSignals,
    tickerDigest,
    hotClusters,
    relations,
    dataUpdatedAt: getLatestTimestamp([
      marketSnapshot.updated_at,
      v2Snapshot?.snapshot_time || "",
      topOpportunityTime,
      topSignalTime,
      topClusterTime,
      topRelationTime
    ])
  };
}

function getLatestTimestamp(values: string[]): string {
  return values.reduce<string>((latest, current) => {
    if (!current) {
      return latest;
    }
    return current > latest ? current : latest;
  }, new Date().toISOString());
}

export async function getDashboardData(): Promise<DashboardData> {
  const client = buildReadonlyClient();
  const readV2 = readV2Enabled();

  if (!client) {
    const now = new Date().toISOString();
    const fallbackTickerRows = FALLBACK_TICKERS.map((ticker) => ({
      ticker,
      signal_count_24h: 0,
      related_cluster_count_24h: 0,
      risk_level: "L1" as RiskLevel,
      top_sentinel_levels: [],
      updated_at: now
    }));

    return {
      opportunities: fallbackTickerRows.slice(0, 8).map((row, idx) => ({
        id: idx + 1,
        ticker: row.ticker,
        side: idx % 3 === 0 ? "SHORT" : "LONG",
        horizon: "A",
        opportunity_score: 35,
        confidence: 0.5,
        risk_level: row.risk_level,
        why_now: `${row.ticker} 当前处于观察池，等待新催化信号。`,
        invalid_if: "若无新增催化，保持观望。",
        catalysts: [],
        factor_breakdown: {},
        source_signal_ids: [],
        source_cluster_ids: [],
        expires_at: new Date(Date.now() + 48 * 3600 * 1000).toISOString(),
        as_of: now
      })),
      marketRegime: null,
      marketSnapshot: baseSnapshot(),
      sentinelSignals: [],
      tickerDigest: fallbackTickerRows,
      hotClusters: [],
      relations: [],
      dataUpdatedAt: now
    };
  }

  if (readV2) {
    const v2Data = await getDashboardDataFromV2(client);
    if (v2Data) {
      return v2Data;
    }
    console.warn("[FRONTEND_V2_EMPTY_FALLBACK] V2 数据为空，回退 legacy 聚合");
  }

  const sentinelSignals = await querySentinelSignals(client);
  const tickerDigest = await queryTickerDigest(client, sentinelSignals);
  const opportunities = await queryOpportunities(client, tickerDigest, sentinelSignals);
  const marketRegime = await queryMarketRegime(client);

  const focusTickers = new Set(opportunities.map((item) => item.ticker));
  const filteredSignals = focusTickers.size
    ? sentinelSignals.filter((item) => signalMentionsTicker(item, focusTickers))
    : sentinelSignals;

  const [marketSnapshot, hotClusters, relations] = await Promise.all([
    queryMarketSnapshot(client, filteredSignals),
    queryHotClusters(client, filteredSignals, opportunities),
    queryEntityRelations(client)
  ]);

  const topOpportunityTime = opportunities[0]?.as_of || "";
  const topSignalTime = filteredSignals[0]?.created_at || "";
  const topClusterTime = hotClusters[0]?.created_at || "";
  const topRelationTime = relations[0]?.last_seen || "";

  return {
    opportunities,
    marketRegime,
    marketSnapshot,
    sentinelSignals: filteredSignals,
    tickerDigest,
    hotClusters,
    relations,
    dataUpdatedAt: getLatestTimestamp([
      marketSnapshot.updated_at,
      topOpportunityTime,
      topSignalTime,
      topClusterTime,
      topRelationTime
    ])
  };
}
