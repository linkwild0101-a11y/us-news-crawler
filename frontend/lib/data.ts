import { createClient, SupabaseClient } from "@supabase/supabase-js";

import {
  DashboardData,
  EntityRelationItem,
  HotCluster,
  MarketSnapshot,
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

function calculateTopRisk(signals: SentinelSignal[]): RiskLevel {
  return signals.reduce<RiskLevel>((maxLevel, signal) => {
    return LEVEL_ORDER[signal.alert_level] > LEVEL_ORDER[maxLevel] ? signal.alert_level : maxLevel;
  }, "L1");
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
  signals: SentinelSignal[]
): Promise<HotCluster[]> {
  const stockClusterIds = Array.from(
    new Set(
      signals
        .map((signal) => signal.cluster_id)
        .filter((clusterId): clusterId is number => typeof clusterId === "number" && clusterId > 0)
    )
  );

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

  if (!client) {
    const now = new Date().toISOString();
    return {
      marketSnapshot: baseSnapshot(),
      sentinelSignals: [],
      tickerDigest: FALLBACK_TICKERS.map((ticker) => ({
        ticker,
        signal_count_24h: 0,
        related_cluster_count_24h: 0,
        risk_level: "L1",
        top_sentinel_levels: [],
        updated_at: now
      })),
      hotClusters: [],
      relations: [],
      dataUpdatedAt: now
    };
  }

  const sentinelSignals = await querySentinelSignals(client);

  const [marketSnapshot, tickerDigest, hotClusters, relations] = await Promise.all([
    queryMarketSnapshot(client, sentinelSignals),
    queryTickerDigest(client, sentinelSignals),
    queryHotClusters(client, sentinelSignals),
    queryEntityRelations(client)
  ]);

  const topSignalTime = sentinelSignals[0]?.created_at || "";
  const topClusterTime = hotClusters[0]?.created_at || "";
  const topRelationTime = relations[0]?.last_seen || "";

  return {
    marketSnapshot,
    sentinelSignals,
    tickerDigest,
    hotClusters,
    relations,
    dataUpdatedAt: getLatestTimestamp([
      marketSnapshot.updated_at,
      topSignalTime,
      topClusterTime,
      topRelationTime
    ])
  };
}
