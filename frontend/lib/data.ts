import { createClient, SupabaseClient } from "@supabase/supabase-js";

import {
  AiDebateView,
  AlertCenterItem,
  AlertFeedbackLabel,
  AlertUserPrefs,
  AlertStatus,
  AlertSide,
  DashboardData,
  DataQualitySnapshot,
  EvidenceItem,
  EntityRelationItem,
  HotCluster,
  IndirectImpactItem,
  MarketRegime,
  MarketSnapshot,
  OpportunityItem,
  PortfolioHoldingItem,
  RiskLevel,
  SentinelSignal,
  SourceMix,
  TickerProfileItem,
  TransmissionPath,
  XSourceRadarItem,
  TickerSignalDigest
} from "@/lib/types";
import {
  readAiDebateViewFlag,
  readEvidenceLayerFlag,
  readTransmissionLayerFlag
} from "@/lib/feature-flags";

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
const EVENT_TYPE_LABELS: Record<string, string> = {
  earnings: "财报",
  macro: "宏观",
  policy: "政策",
  flow: "资金流",
  sector: "行业",
  news: "新闻"
};
const INDIRECT_THEME_LABELS: Record<string, string> = {
  macro: "宏观",
  rate_fx: "利率/汇率",
  policy: "政策",
  geopolitics: "地缘",
  commodity: "大宗商品",
  supply_chain: "供应链"
};
const TICKER_PROFILE_SEED: Record<string, TickerProfileItem> = {
  SPY: {
    ticker: "SPY",
    display_name: "SPDR S&P 500 ETF",
    asset_type: "etf",
    sector: "Index",
    industry: "US Large Cap",
    summary_cn: "跟踪标普500，适合观察美股整体风险偏好与市场趋势。"
  },
  QQQ: {
    ticker: "QQQ",
    display_name: "Invesco QQQ Trust",
    asset_type: "etf",
    sector: "Index",
    industry: "Nasdaq 100",
    summary_cn: "跟踪纳指100，科技权重高，对成长风格与利率更敏感。"
  },
  DIA: {
    ticker: "DIA",
    display_name: "SPDR Dow Jones Industrial Average ETF",
    asset_type: "etf",
    sector: "Index",
    industry: "Dow 30",
    summary_cn: "跟踪道琼斯工业指数，偏大盘蓝筹，防御属性相对更强。"
  },
  IWM: {
    ticker: "IWM",
    display_name: "iShares Russell 2000 ETF",
    asset_type: "etf",
    sector: "Index",
    industry: "Small Cap",
    summary_cn: "跟踪罗素2000小盘股，常用于衡量风险偏好与内需弹性。"
  },
  XLF: {
    ticker: "XLF",
    display_name: "Financial Select Sector SPDR",
    asset_type: "etf",
    sector: "Financials",
    industry: "Sector ETF",
    summary_cn: "金融板块ETF，对利率曲线、信用环境与监管变化敏感。"
  },
  XLK: {
    ticker: "XLK",
    display_name: "Technology Select Sector SPDR",
    asset_type: "etf",
    sector: "Technology",
    industry: "Sector ETF",
    summary_cn: "科技板块ETF，受AI资本开支、业绩预期和估值影响较大。"
  },
  XLE: {
    ticker: "XLE",
    display_name: "Energy Select Sector SPDR",
    asset_type: "etf",
    sector: "Energy",
    industry: "Sector ETF",
    summary_cn: "能源板块ETF，与油价、地缘风险和供需周期关系紧密。"
  },
  XLV: {
    ticker: "XLV",
    display_name: "Health Care Select Sector SPDR",
    asset_type: "etf",
    sector: "Healthcare",
    industry: "Sector ETF",
    summary_cn: "医疗板块ETF，兼具防御属性与政策监管敏感性。"
  },
  SMH: {
    ticker: "SMH",
    display_name: "VanEck Semiconductor ETF",
    asset_type: "etf",
    sector: "Technology",
    industry: "Semiconductors",
    summary_cn: "半导体ETF，受AI算力周期、库存与资本开支影响显著。"
  },
  TLT: {
    ticker: "TLT",
    display_name: "iShares 20+ Year Treasury Bond ETF",
    asset_type: "etf",
    sector: "Rates",
    industry: "US Treasury",
    summary_cn: "美债长久期ETF，反映利率预期与避险情绪变化。"
  },
  AAPL: {
    ticker: "AAPL",
    display_name: "Apple Inc.",
    asset_type: "equity",
    sector: "Technology",
    industry: "Consumer Electronics",
    summary_cn: "消费电子龙头，关注新品周期、服务收入与全球需求变化。"
  },
  MSFT: {
    ticker: "MSFT",
    display_name: "Microsoft Corporation",
    asset_type: "equity",
    sector: "Technology",
    industry: "Software",
    summary_cn: "软件与云计算龙头，关键变量是云增速、AI商业化与利润率。"
  },
  NVDA: {
    ticker: "NVDA",
    display_name: "NVIDIA Corporation",
    asset_type: "equity",
    sector: "Technology",
    industry: "Semiconductors",
    summary_cn: "AI芯片核心公司，关注数据中心需求、供给节奏与估值波动。"
  },
  AMZN: {
    ticker: "AMZN",
    display_name: "Amazon.com, Inc.",
    asset_type: "equity",
    sector: "Consumer Discretionary",
    industry: "E-commerce & Cloud",
    summary_cn: "电商与云双引擎公司，重点看AWS增速、消费强度与利润改善。"
  },
  GOOGL: {
    ticker: "GOOGL",
    display_name: "Alphabet Inc.",
    asset_type: "equity",
    sector: "Technology",
    industry: "Internet Services",
    summary_cn: "搜索与广告平台龙头，关注广告景气、云业务与AI竞争格局。"
  },
  META: {
    ticker: "META",
    display_name: "Meta Platforms, Inc.",
    asset_type: "equity",
    sector: "Technology",
    industry: "Social Media",
    summary_cn: "社交广告平台公司，核心变量为广告效率、用户增长和AI投入。"
  },
  TSLA: {
    ticker: "TSLA",
    display_name: "Tesla, Inc.",
    asset_type: "equity",
    sector: "Consumer Discretionary",
    industry: "EV & Energy Storage",
    summary_cn: "新能源车龙头，关注交付增速、价格策略与自动驾驶进展。"
  }
};

function normalizeAssetType(value: unknown): TickerProfileItem["asset_type"] {
  const text = String(value || "unknown").toLowerCase().trim();
  if (text === "equity" || text === "etf" || text === "index" || text === "macro") {
    return text;
  }
  return "unknown";
}

function fallbackTickerProfile(ticker: string): TickerProfileItem {
  const upper = ticker.toUpperCase().trim();
  const seeded = TICKER_PROFILE_SEED[upper];
  if (seeded) {
    return seeded;
  }
  return {
    ticker: upper,
    display_name: upper,
    asset_type: "unknown",
    sector: "Unknown",
    industry: "Unknown",
    summary_cn: "美股观察标的，建议结合原文证据与行业背景做二次判断。"
  };
}

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

function hasChinese(text: string): boolean {
  return /[\u4e00-\u9fff]/.test(text);
}

function toZhTextOrPending(text: string, fallback = "翻译处理中"): string {
  const normalized = text.trim();
  if (!normalized) {
    return fallback;
  }
  return hasChinese(normalized) ? normalized : fallback;
}

function toZhClusterCategory(eventType: string): string {
  const key = String(eventType || "news").toLowerCase();
  return EVENT_TYPE_LABELS[key] || "新闻";
}

function toZhClusterLabel(value: unknown): string {
  const text = String(value || "").trim();
  if (!text) {
    return "新闻";
  }
  if (hasChinese(text)) {
    return text;
  }
  return toZhClusterCategory(text);
}

function parseTimestampMs(value: string): number | null {
  const ts = Date.parse(value);
  if (!Number.isFinite(ts)) {
    return null;
  }
  return ts;
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

function toAlertSide(value: unknown): AlertSide {
  const text = String(value || "NEUTRAL").toUpperCase();
  if (text === "LONG" || text === "SHORT" || text === "NEUTRAL") {
    return text;
  }
  return "NEUTRAL";
}

function toAlertStatus(value: unknown): AlertStatus {
  const text = String(value || "pending").toLowerCase();
  if (text === "pending" || text === "sent" || text === "deduped" || text === "dropped") {
    return text;
  }
  return "pending";
}

function toAlertFeedbackLabel(value: unknown): AlertFeedbackLabel | null {
  const text = String(value || "").toLowerCase();
  if (text === "useful" || text === "noise") {
    return text;
  }
  return null;
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

function toSourceMix(value: unknown): SourceMix | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const row = value as Record<string, unknown>;
  const xCount = Math.max(0, Number(row.x_count || 0));
  const articleCount = Math.max(0, Number(row.article_count || 0));
  const otherCount = Math.max(0, Number(row.other_count || 0));
  const sourceTotalRaw = Number(row.source_total || xCount + articleCount + otherCount);
  const sourceTotal = Math.max(1, Number.isFinite(sourceTotalRaw) ? sourceTotalRaw : 1);
  const ratioRaw = Number(row.x_ratio || 0);
  const xRatio = Number.isFinite(ratioRaw) ? Math.max(0, Math.min(1, ratioRaw)) : 0;
  const handles = Array.isArray(row.top_x_handles)
    ? row.top_x_handles
      .map((item) => String(item || "").trim())
      .filter((item) => item.length > 0)
      .slice(0, 3)
    : [];
  return {
    x_count: Math.round(xCount),
    article_count: Math.round(articleCount),
    other_count: Math.round(otherCount),
    source_total: Math.round(sourceTotal),
    x_ratio: xRatio,
    mixed_sources: Boolean(row.mixed_sources),
    top_x_handles: handles,
    latest_x_at: toIsoString(row.latest_x_at),
    latest_news_at: toIsoString(row.latest_news_at)
  };
}

function toObjectArray(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) {
    return [];
  }
  const filtered = value.filter((item) => item && typeof item === "object" && !Array.isArray(item));
  return filtered as Array<Record<string, unknown>>;
}

function buildAiDebateView(opportunity: OpportunityItem): AiDebateView | null {
  const proCase = String(opportunity.why_now || "").trim();
  const counterCase = String(opportunity.counter_view || "").trim();
  const uncertainties = (opportunity.uncertainty_flags || [])
    .map((item) => String(item || "").trim())
    .filter((item) => item.length > 0);

  if (!proCase && !counterCase && uncertainties.length === 0) {
    return null;
  }

  const checks = [
    "先核对原文关键数字和发布时间是否一致。",
    "确认是否存在24小时内反向催化。",
    "结合仓位与风险限额决定执行节奏。"
  ];

  return {
    pro_case: proCase || "当前信号与催化结构支持该方向。",
    counter_case: counterCase || "若出现反向宏观/行业催化，当前观点可能失效。",
    uncertainties: uncertainties.length > 0 ? uncertainties : ["证据存在时效与来源偏差风险。"],
    pre_trade_checks: checks
  };
}

function stableIdFromText(text: string): number {
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) {
    hash = ((hash << 5) - hash + text.charCodeAt(i)) | 0;
  }
  const positive = Math.abs(hash);
  return positive === 0 ? 1 : positive;
}

function buildDataQualitySnapshot(
  dataUpdatedAt: string,
  sourceHealth: { healthy: number; degraded: number; critical: number }
): DataQualitySnapshot {
  const updatedTs = parseTimestampMs(dataUpdatedAt);
  const nowTs = Date.now();
  const freshnessMinutes = updatedTs === null
    ? 9999
    : Math.max(0, Math.round((nowTs - updatedTs) / 60000));
  let freshnessLevel: DataQualitySnapshot["freshness_level"] = "critical";
  if (freshnessMinutes <= 30) {
    freshnessLevel = "fresh";
  } else if (freshnessMinutes <= 120) {
    freshnessLevel = "stale";
  }

  let sourceHealthStatus: DataQualitySnapshot["source_health_status"] = "healthy";
  if (sourceHealth.critical > 0) {
    sourceHealthStatus = "critical";
  } else if (sourceHealth.degraded > 0) {
    sourceHealthStatus = "degraded";
  }

  return {
    freshness_minutes: freshnessMinutes,
    freshness_level: freshnessLevel,
    source_health_status: sourceHealthStatus,
    source_health_healthy: sourceHealth.healthy,
    source_health_degraded: sourceHealth.degraded,
    source_health_critical: sourceHealth.critical
  };
}

async function querySourceHealth(
  client: SupabaseClient
): Promise<{ healthy: number; degraded: number; critical: number }> {
  const fallback = { healthy: 0, degraded: 0, critical: 0 };
  const lookbackIso = new Date(Date.now() - 72 * 3600 * 1000).toISOString();
  try {
    const { data, error } = await client
      .from("source_health_daily")
      .select("source_id,status,as_of")
      .gte("as_of", lookbackIso)
      .order("as_of", { ascending: false })
      .limit(120);
    if (error) {
      throw error;
    }

    const latestBySource = new Map<string, string>();
    for (const row of (data || []) as unknown as Array<Record<string, unknown>>) {
      const sourceId = String(row.source_id || "").trim();
      const status = String(row.status || "healthy").trim().toLowerCase();
      if (!sourceId || latestBySource.has(sourceId)) {
        continue;
      }
      latestBySource.set(sourceId, status);
    }
    if (latestBySource.size === 0) {
      return fallback;
    }
    const healthy = Array.from(latestBySource.values()).filter((item) => item === "healthy").length;
    const degraded = Array.from(latestBySource.values()).filter((item) => item === "degraded").length;
    const critical = Array.from(latestBySource.values()).filter((item) => item === "critical").length;
    return { healthy, degraded, critical };
  } catch (error) {
    console.warn("[FRONTEND_SOURCE_HEALTH_FALLBACK]", error);
    return fallback;
  }
}

async function queryAlertCenter(client: SupabaseClient): Promise<AlertCenterItem[]> {
  try {
    const { data: eventRows, error: eventError } = await client
      .from("stock_alert_events_v1")
      .select(
        "id,user_id,ticker,signal_type,signal_level,alert_score,side,title,why_now,"
        + "session_tag,status,dedupe_window,created_at"
      )
      .eq("is_active", true)
      .order("created_at", { ascending: false })
      .limit(120);
    if (eventError) {
      throw eventError;
    }

    const events = (eventRows || []) as unknown as Array<Record<string, unknown>>;
    if (events.length === 0) {
      return [];
    }

    const alertIds = events
      .map((row) => Number(row.id || 0))
      .filter((id) => Number.isFinite(id) && id > 0);
    const feedbackStats = new Map<number, {
      useful: number;
      noise: number;
      latestLabel: AlertFeedbackLabel | null;
      latestAt: string;
    }>();

    if (alertIds.length > 0) {
      const { data: feedbackRows, error: feedbackError } = await client
        .from("stock_alert_feedback_v1")
        .select("alert_id,label,created_at")
        .in("alert_id", alertIds)
        .order("created_at", { ascending: false })
        .limit(2000);
      if (feedbackError) {
        throw feedbackError;
      }
      for (const row of (feedbackRows || []) as unknown as Array<Record<string, unknown>>) {
        const alertId = Number(row.alert_id || 0);
        if (!Number.isFinite(alertId) || alertId <= 0) {
          continue;
        }
        const label = toAlertFeedbackLabel(row.label);
        if (!label) {
          continue;
        }
        const createdAt = toIsoString(row.created_at);
        const prev = feedbackStats.get(alertId) || {
          useful: 0,
          noise: 0,
          latestLabel: null,
          latestAt: ""
        };
        if (label === "useful") {
          prev.useful += 1;
        } else {
          prev.noise += 1;
        }
        if (!prev.latestAt || createdAt > prev.latestAt) {
          prev.latestAt = createdAt;
          prev.latestLabel = label;
        }
        feedbackStats.set(alertId, prev);
      }
    }

    return events.map((row) => {
      const alertId = Number(row.id || 0);
      const stats = feedbackStats.get(alertId);
      return {
        id: alertId,
        user_id: String(row.user_id || "system"),
        ticker: String(row.ticker || "").toUpperCase(),
        signal_type: String(row.signal_type || "opportunity"),
        signal_level: toLevel(row.signal_level),
        alert_score: Math.max(0, Math.min(100, Number(row.alert_score || 0))),
        side: toAlertSide(row.side),
        title: String(row.title || ""),
        why_now: String(row.why_now || ""),
        session_tag: String(row.session_tag || "regular"),
        status: toAlertStatus(row.status),
        dedupe_window: toIsoString(row.dedupe_window),
        created_at: toIsoString(row.created_at),
        feedback_useful_count: stats?.useful || 0,
        feedback_noise_count: stats?.noise || 0,
        latest_feedback_label: stats?.latestLabel || null
      } as AlertCenterItem;
    });
  } catch (error) {
    console.warn("[FRONTEND_ALERT_CENTER_FALLBACK]", error);
    return [];
  }
}

async function queryAlertPrefs(client: SupabaseClient): Promise<AlertUserPrefs> {
  const fallback: AlertUserPrefs = {
    user_id: "system",
    enable_premarket: false,
    enable_postmarket: true,
    daily_alert_cap: 20,
    quiet_hours_start: 0,
    quiet_hours_end: 0,
    watch_tickers: [],
    muted_signal_types: []
  };

  try {
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
    if (error || !data) {
      if (error) {
        throw error;
      }
      return fallback;
    }
    const row = data as unknown as Record<string, unknown>;

    return {
      user_id: String(row.user_id || "system"),
      enable_premarket: Boolean(row.enable_premarket),
      enable_postmarket: Boolean(row.enable_postmarket),
      daily_alert_cap: Math.max(1, Math.min(200, Number(row.daily_alert_cap || 20))),
      quiet_hours_start: Math.max(0, Math.min(23, Number(row.quiet_hours_start || 0))),
      quiet_hours_end: Math.max(0, Math.min(23, Number(row.quiet_hours_end || 0))),
      watch_tickers: Array.isArray(row.watch_tickers)
        ? row.watch_tickers
          .map((item: unknown) => String(item || "").toUpperCase().trim())
          .filter((item: string) => item.length > 0)
        : [],
      muted_signal_types: Array.isArray(row.muted_signal_types)
        ? row.muted_signal_types
          .map((item: unknown) => String(item || "").toLowerCase().trim())
          .filter((item: string) => item.length > 0)
        : []
    };
  } catch (error) {
    console.warn("[FRONTEND_ALERT_PREFS_FALLBACK]", error);
    return fallback;
  }
}

async function queryPortfolioHoldings(client: SupabaseClient): Promise<PortfolioHoldingItem[]> {
  try {
    const { data: portfolioRows, error: portfolioError } = await client
      .from("stock_portfolios_v1")
      .select("id")
      .eq("is_active", true)
      .eq("user_id", "system")
      .eq("portfolio_key", "default")
      .limit(1);
    if (portfolioError) {
      throw portfolioError;
    }
    const portfolioId = Number(portfolioRows?.[0]?.id || 0);
    if (portfolioId <= 0) {
      return [];
    }

    const { data, error } = await client
      .from("stock_portfolio_holdings_v1")
      .select(
        "id,portfolio_id,user_id,ticker,side,quantity,avg_cost,market_value,"
        + "weight,notes,updated_at"
      )
      .eq("is_active", true)
      .eq("portfolio_id", portfolioId)
      .order("updated_at", { ascending: false })
      .limit(300);
    if (error) {
      throw error;
    }

    const rows = (data || []) as unknown as Array<Record<string, unknown>>;
    return rows.map((row) => {
      const side = String(row.side || "LONG").toUpperCase() === "SHORT" ? "SHORT" : "LONG";
      return {
        id: Number(row.id || 0),
        portfolio_id: Number(row.portfolio_id || portfolioId),
        user_id: String(row.user_id || "system"),
        ticker: String(row.ticker || "").toUpperCase(),
        side,
        quantity: Number(row.quantity || 0),
        avg_cost: Number(row.avg_cost || 0),
        market_value: Number(row.market_value || 0),
        weight: Number(row.weight || 0),
        notes: String(row.notes || ""),
        updated_at: toIsoString(row.updated_at)
      };
    });
  } catch (error) {
    console.warn("[FRONTEND_PORTFOLIO_HOLDINGS_FALLBACK]", error);
    return [];
  }
}

async function queryTickerProfiles(
  client: SupabaseClient,
  tickers: string[]
): Promise<Record<string, TickerProfileItem>> {
  const requested = Array.from(
    new Set(
      tickers
        .map((item) => String(item || "").toUpperCase().trim())
        .filter((item) => item.length > 0)
    )
  );
  const fallbackMap: Record<string, TickerProfileItem> = {};
  for (const ticker of requested) {
    fallbackMap[ticker] = fallbackTickerProfile(ticker);
  }

  if (requested.length === 0) {
    return fallbackMap;
  }

  try {
    const { data, error } = await client
      .from("stock_ticker_profiles_v1")
      .select("ticker,display_name,asset_type,sector,industry,summary_cn")
      .eq("is_active", true)
      .in("ticker", requested)
      .limit(500);
    if (error) {
      throw error;
    }

    const rows = (data || []) as unknown as Array<Record<string, unknown>>;
    for (const row of rows) {
      const ticker = String(row.ticker || "").toUpperCase().trim();
      if (!ticker) {
        continue;
      }
      fallbackMap[ticker] = {
        ticker,
        display_name: String(row.display_name || ticker),
        asset_type: normalizeAssetType(row.asset_type),
        sector: String(row.sector || "Unknown"),
        industry: String(row.industry || "Unknown"),
        summary_cn: String(row.summary_cn || fallbackTickerProfile(ticker).summary_cn)
      };
    }
    return fallbackMap;
  } catch (error) {
    console.warn("[FRONTEND_TICKER_PROFILE_FALLBACK]", error);
    return fallbackMap;
  }
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
      .select(
        "id,ticker,level,signal_score,explanation,trigger_factors,"
        + "source_event_ids,source_mix,as_of"
      )
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
        source_mix: toSourceMix(row.source_mix),
        created_at: toIsoString(row.as_of)
      };
    });
  } catch (error) {
    console.warn("[FRONTEND_V2_SIGNAL_FALLBACK]", error);
    return [];
  }
}

async function queryV2Opportunities(client: SupabaseClient): Promise<OpportunityItem[]> {
  const selectWithEvidence = (
    "id,ticker,side,horizon,opportunity_score,confidence,risk_level,why_now,invalid_if,"
    + "catalysts,source_signal_ids,source_event_ids,source_mix,evidence_ids,path_ids,"
    + "uncertainty_flags,counter_view,expires_at,as_of"
  );
  const selectLegacy = (
    "id,ticker,side,horizon,opportunity_score,confidence,risk_level,why_now,invalid_if,"
    + "catalysts,source_signal_ids,source_event_ids,source_mix,expires_at,as_of"
  );

  async function runQuery(selectClause: string): Promise<Array<Record<string, unknown>>> {
    const { data, error } = await client
      .from("stock_opportunities_v2")
      .select(selectClause)
      .eq("is_active", true)
      .order("opportunity_score", { ascending: false })
      .limit(40);
    if (error) {
      throw error;
    }
    return (data || []) as unknown as Array<Record<string, unknown>>;
  }

  try {
    let rows: Array<Record<string, unknown>> = [];
    try {
      rows = await runQuery(selectWithEvidence);
    } catch (firstError) {
      const errorText = String(firstError || "");
      if (
        errorText.includes("evidence_ids")
        || errorText.includes("path_ids")
        || errorText.includes("counter_view")
        || errorText.includes("uncertainty_flags")
      ) {
        console.warn("[FRONTEND_V2_OPP_SELECT_FALLBACK]", firstError);
        rows = await runQuery(selectLegacy);
      } else {
        throw firstError;
      }
    }

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
          source_event_ids: Array.isArray(row.source_event_ids)
            ? row.source_event_ids
              .map((item: unknown) => Number(item || 0))
              .filter((item) => item > 0)
            : [],
          source_cluster_ids: [],
          source_mix: toSourceMix(row.source_mix),
          evidence_ids: Array.isArray(row.evidence_ids)
            ? row.evidence_ids
              .map((item: unknown) => Number(item || 0))
              .filter((item) => item > 0)
            : [],
          path_ids: Array.isArray(row.path_ids)
            ? row.path_ids
              .map((item: unknown) => Number(item || 0))
              .filter((item) => item > 0)
            : [],
          uncertainty_flags: toStringArray(row.uncertainty_flags),
          counter_view: String(row.counter_view || "").trim(),
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

async function queryV2IndirectImpacts(client: SupabaseClient): Promise<IndirectImpactItem[]> {
  try {
    const { data, error } = await client
      .from("stock_indirect_events_v2")
      .select(
        "id,theme,impact_scope,summary,candidate_tickers,relevance_score,"
        + "confidence,promotion_status,as_of"
      )
      .eq("is_active", true)
      .order("relevance_score", { ascending: false })
      .order("as_of", { ascending: false })
      .limit(16);

    if (error) {
      throw error;
    }

    const rows = (data || []) as unknown as Array<Record<string, unknown>>;
    return rows.map((row) => {
      const scopeText = String(row.impact_scope || "sector").toLowerCase();
      const promotionText = String(row.promotion_status || "pending").toLowerCase();
      return {
        id: Number(row.id || 0),
        theme: INDIRECT_THEME_LABELS[String(row.theme || "")] || String(row.theme || "其他"),
        impact_scope: scopeText === "index" || scopeText === "ticker" ? scopeText : "sector",
        summary: String(row.summary || ""),
        candidate_tickers: Array.isArray(row.candidate_tickers)
          ? row.candidate_tickers
            .map((item) => String(item || "").toUpperCase())
            .filter((item) => item.length > 0)
            .slice(0, 4)
          : [],
        relevance_score: Math.max(0, Math.min(100, Number(row.relevance_score || 0))),
        confidence: toScore(row.confidence),
        promotion_status: promotionText === "promoted" || promotionText === "rejected"
          ? promotionText
          : "pending",
        as_of: toIsoString(row.as_of)
      };
    });
  } catch (error) {
    console.warn("[FRONTEND_V2_INDIRECT_FALLBACK]", error);
    return [];
  }
}

async function queryV2EvidenceMap(
  client: SupabaseClient,
  opportunityIds: number[]
): Promise<Map<number, EvidenceItem[]>> {
  if (opportunityIds.length === 0) {
    return new Map();
  }
  try {
    const { data, error } = await client
      .from("stock_evidence_v2")
      .select(
        "id,opportunity_id,ticker,source_type,source_ref,source_url,source_name,published_at,"
        + "quote_snippet,numeric_facts,confidence,as_of"
      )
      .eq("is_active", true)
      .in("opportunity_id", opportunityIds)
      .order("confidence", { ascending: false })
      .limit(1200);

    if (error) {
      throw error;
    }

    const map = new Map<number, EvidenceItem[]>();
    for (const row of (data || []) as unknown as Array<Record<string, unknown>>) {
      const oppId = Number(row.opportunity_id || 0);
      if (!Number.isFinite(oppId) || oppId <= 0) {
        continue;
      }
      const item: EvidenceItem = {
        id: Number(row.id || 0),
        opportunity_id: oppId,
        ticker: String(row.ticker || "").toUpperCase(),
        source_type: String(row.source_type || "article"),
        source_ref: String(row.source_ref || ""),
        source_url: String(row.source_url || ""),
        source_name: String(row.source_name || ""),
        published_at: toIsoString(row.published_at),
        quote_snippet: String(row.quote_snippet || ""),
        numeric_facts: toObjectArray(row.numeric_facts),
        confidence: toScore(row.confidence),
        as_of: toIsoString(row.as_of)
      };
      const existing = map.get(oppId) || [];
      existing.push(item);
      map.set(oppId, existing);
    }
    for (const [oppId, rows] of map.entries()) {
      map.set(oppId, rows.slice(0, 6));
    }
    return map;
  } catch (error) {
    console.warn("[FRONTEND_V2_EVIDENCE_FALLBACK]", error);
    return new Map();
  }
}

async function queryV2TransmissionMap(
  client: SupabaseClient,
  opportunityIds: number[]
): Promise<Map<number, TransmissionPath[]>> {
  if (opportunityIds.length === 0) {
    return new Map();
  }
  try {
    const { data, error } = await client
      .from("stock_transmission_paths_v2")
      .select(
        "id,opportunity_id,path_key,ticker,macro_factor,industry,direction,strength,reason,"
        + "evidence_ids,as_of"
      )
      .eq("is_active", true)
      .in("opportunity_id", opportunityIds)
      .order("strength", { ascending: false })
      .limit(800);

    if (error) {
      throw error;
    }

    const map = new Map<number, TransmissionPath[]>();
    for (const row of (data || []) as unknown as Array<Record<string, unknown>>) {
      const oppId = Number(row.opportunity_id || 0);
      if (!Number.isFinite(oppId) || oppId <= 0) {
        continue;
      }
      const directionText = String(row.direction || "NEUTRAL").toUpperCase();
      const direction: TransmissionPath["direction"] = directionText === "LONG"
        ? "LONG"
        : directionText === "SHORT"
          ? "SHORT"
          : "NEUTRAL";
      const item: TransmissionPath = {
        id: Number(row.id || 0),
        opportunity_id: oppId,
        path_key: String(row.path_key || ""),
        ticker: String(row.ticker || "").toUpperCase(),
        macro_factor: String(row.macro_factor || "宏观因子"),
        industry: String(row.industry || "Unknown"),
        direction,
        strength: Math.max(0, Math.min(1, Number(row.strength || 0))),
        reason: String(row.reason || ""),
        evidence_ids: Array.isArray(row.evidence_ids)
          ? row.evidence_ids.map((item) => Number(item || 0)).filter((item) => item > 0)
          : [],
        as_of: toIsoString(row.as_of)
      };
      const existing = map.get(oppId) || [];
      existing.push(item);
      map.set(oppId, existing);
    }
    for (const [oppId, rows] of map.entries()) {
      map.set(oppId, rows.slice(0, 3));
    }
    return map;
  } catch (error) {
    console.warn("[FRONTEND_V2_PATH_FALLBACK]", error);
    return new Map();
  }
}

function calculateTopRisk(signals: SentinelSignal[]): RiskLevel {
  return signals.reduce<RiskLevel>((maxLevel, signal) => {
    return LEVEL_ORDER[signal.alert_level] > LEVEL_ORDER[maxLevel] ? signal.alert_level : maxLevel;
  }, "L1");
}

async function queryV2IndirectEventIdSet(
  client: SupabaseClient,
  eventIds: number[]
): Promise<Set<number>> {
  if (eventIds.length === 0) {
    return new Set();
  }
  try {
    const { data, error } = await client
      .from("stock_events_v2")
      .select("id,source_type")
      .in("id", eventIds)
      .limit(2000);
    if (error) {
      throw error;
    }
    const indirectIds = new Set<number>();
    for (const row of (data || []) as unknown as Array<Record<string, unknown>>) {
      const sourceType = String(row.source_type || "").toLowerCase();
      const eventId = Number(row.id || 0);
      if (eventId > 0 && sourceType === "indirect_promoted") {
        indirectIds.add(eventId);
      }
    }
    return indirectIds;
  } catch (error) {
    console.warn("[FRONTEND_V2_EVENT_SOURCE_FALLBACK]", error);
    return new Set();
  }
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
    category: toZhClusterLabel(row.category),
    primary_title: hasChinese(String(row.primary_title || ""))
      ? String(row.primary_title || "")
      : `${toZhClusterLabel(row.category)}事件簇`,
    summary: toZhTextOrPending(String(row.summary || ""), "翻译处理中"),
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
        const relationText = String(row.relation_text || "关联");
        return {
          id: Number(row.id || 0),
          entity1_name: entityNameMap.get(entity1Id) || `Entity#${entity1Id}`,
          entity2_name: entityNameMap.get(entity2Id) || `Entity#${entity2Id}`,
          relation_text: hasChinese(relationText) ? relationText : "关联证据翻译处理中",
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

function buildTickerDigestFromV2(
  signals: SentinelSignal[],
  opportunities: OpportunityItem[]
): TickerSignalDigest[] {
  const fromSignals = buildTickerDigestFromSignals(signals);
  if (fromSignals.length > 0) {
    return fromSignals;
  }

  return opportunities.slice(0, 20).map((item) => ({
    ticker: item.ticker,
    signal_count_24h: Math.max(1, item.source_signal_ids.length),
    related_cluster_count_24h: item.source_cluster_ids.length,
    risk_level: item.risk_level,
    top_sentinel_levels: [item.risk_level],
    updated_at: item.as_of
  }));
}

function buildXSourceRadar(
  signals: SentinelSignal[],
  opportunities: OpportunityItem[]
): XSourceRadarItem[] {
  const bucket = new Map<string, { mentions: number; mixed: number; ratioSum: number; latestAt: string }>();
  const merge = (sourceMix?: SourceMix | null, createdAt = "") => {
    if (!sourceMix || sourceMix.x_count <= 0) {
      return;
    }
    const ratio = Math.max(0, Math.min(1, sourceMix.x_ratio));
    const handles = sourceMix.top_x_handles || [];
    for (const handleRaw of handles) {
      const handle = String(handleRaw || "").trim();
      if (!handle) {
        continue;
      }
      const prev = bucket.get(handle) || { mentions: 0, mixed: 0, ratioSum: 0, latestAt: createdAt };
      prev.mentions += 1;
      prev.ratioSum += ratio;
      if (sourceMix.mixed_sources) {
        prev.mixed += 1;
      }
      if (!prev.latestAt || createdAt > prev.latestAt) {
        prev.latestAt = createdAt;
      }
      bucket.set(handle, prev);
    }
  };

  for (const signal of signals) {
    merge(signal.source_mix, signal.created_at);
  }
  for (const opp of opportunities) {
    merge(opp.source_mix, opp.as_of);
  }

  return Array.from(bucket.entries())
    .map(([handle, value]) => ({
      handle,
      mentions: value.mentions,
      mixed_count: value.mixed,
      avg_x_ratio: Number((value.ratioSum / Math.max(1, value.mentions)).toFixed(4)),
      latest_at: value.latestAt || new Date().toISOString()
    }))
    .sort((a, b) => {
      if (b.mentions !== a.mentions) {
        return b.mentions - a.mentions;
      }
      return b.avg_x_ratio - a.avg_x_ratio;
    })
    .slice(0, 10);
}

async function queryV2HotClusters(client: SupabaseClient): Promise<HotCluster[]> {
  try {
    const { data, error } = await client
      .from("stock_events_v2")
      .select("id,event_type,summary,details,as_of")
      .eq("is_active", true)
      .order("as_of", { ascending: false })
      .limit(240);

    if (error) {
      throw error;
    }

    const rows = (data || []) as unknown as Array<Record<string, unknown>>;
    const grouped = new Map<string, Array<Record<string, unknown>>>();
    for (const row of rows) {
      const eventType = String(row.event_type || "news").toLowerCase();
      const current = grouped.get(eventType) || [];
      current.push(row);
      grouped.set(eventType, current);
    }

    const clusters: HotCluster[] = Array.from(grouped.entries()).map(([eventType, items]) => {
      const latest = items[0] || {};
      const details = (
        latest.details
        && typeof latest.details === "object"
        && !Array.isArray(latest.details)
      )
        ? latest.details as Record<string, unknown>
        : {};
      const titleZh = String(details.title_zh || details.summary_zh || "").trim();
      const summaryLatest = String(latest.summary || "").trim();
      const title = titleZh
        || (hasChinese(summaryLatest) ? summaryLatest : `${toZhClusterCategory(eventType)}事件簇`);
      const summary = items
        .slice(0, 3)
        .map((item) => {
          const itemDetails = (
            item.details
            && typeof item.details === "object"
            && !Array.isArray(item.details)
          ) ? item.details as Record<string, unknown> : {};
          const summaryZh = String(itemDetails.summary_zh || "").trim();
          if (summaryZh) {
            return summaryZh;
          }
          const summaryRaw = String(item.summary || "").trim();
          if (hasChinese(summaryRaw)) {
            return summaryRaw;
          }
          return "翻译处理中";
        })
        .filter((item) => item.length > 0)
        .join("；");

      return {
        id: Number(latest.id || 0),
        category: toZhClusterCategory(eventType),
        primary_title: title || `${toZhClusterCategory(eventType)}事件簇`,
        summary: summary || "暂无摘要",
        article_count: items.length,
        created_at: toIsoString(latest.as_of)
      };
    });

    clusters.sort((a, b) => {
      if (b.article_count !== a.article_count) {
        return b.article_count - a.article_count;
      }
      return b.created_at.localeCompare(a.created_at);
    });

    return clusters.slice(0, 20);
  } catch (error) {
    console.warn("[FRONTEND_V2_CLUSTER_FALLBACK]", error);
    return [];
  }
}

async function queryV2Relations(client: SupabaseClient): Promise<EntityRelationItem[]> {
  try {
    const { data: eventRows, error: eventError } = await client
      .from("stock_events_v2")
      .select("id,as_of")
      .eq("is_active", true)
      .order("as_of", { ascending: false })
      .limit(300);

    if (eventError) {
      throw eventError;
    }
    const eventList = (eventRows || []) as unknown as Array<Record<string, unknown>>;
    const eventIds = eventList
      .map((item) => Number(item.id || 0))
      .filter((item) => item > 0);
    if (eventIds.length === 0) {
      return [];
    }
    const eventTimeMap = new Map(
      eventList.map((item) => [Number(item.id || 0), toIsoString(item.as_of)])
    );

    const { data: mapRows, error: mapError } = await client
      .from("stock_event_tickers_v2")
      .select("event_id,ticker,confidence")
      .in("event_id", eventIds);

    if (mapError) {
      throw mapError;
    }

    const tickerMap = new Map<number, Array<{ ticker: string; confidence: number }>>();
    for (const row of (mapRows || []) as unknown as Array<Record<string, unknown>>) {
      const eventId = Number(row.event_id || 0);
      if (eventId <= 0) {
        continue;
      }
      const ticker = String(row.ticker || "").toUpperCase().trim();
      if (!ticker) {
        continue;
      }
      const bucket = tickerMap.get(eventId) || [];
      bucket.push({ ticker, confidence: toScore(row.confidence) });
      tickerMap.set(eventId, bucket);
    }

    const pairStats = new Map<string, { count: number; confidence: number; last_seen: string }>();
    for (const [eventId, rows] of tickerMap.entries()) {
      const uniqueTickers = Array.from(new Set(rows.map((item) => item.ticker))).sort();
      if (uniqueTickers.length < 2) {
        continue;
      }
      const avgConfidence = rows.reduce((acc, item) => acc + item.confidence, 0) / rows.length;
      const lastSeen = eventTimeMap.get(eventId) || new Date().toISOString();
      for (let i = 0; i < uniqueTickers.length - 1; i += 1) {
        for (let j = i + 1; j < uniqueTickers.length; j += 1) {
          const key = `${uniqueTickers[i]}|${uniqueTickers[j]}`;
          const prev = pairStats.get(key);
          if (!prev) {
            pairStats.set(key, { count: 1, confidence: avgConfidence, last_seen: lastSeen });
            continue;
          }
          prev.count += 1;
          prev.confidence = (prev.confidence + avgConfidence) / 2;
          if (lastSeen > prev.last_seen) {
            prev.last_seen = lastSeen;
          }
          pairStats.set(key, prev);
        }
      }
    }

    return Array.from(pairStats.entries())
      .map(([key, value]) => {
        const [left, right] = key.split("|");
        const confidence = Math.max(0, Math.min(1, 0.45 + value.count * 0.08 + value.confidence * 0.2));
        return {
          id: stableIdFromText(key),
          entity1_name: left,
          entity2_name: right,
          relation_text: `同一美股事件中共同出现 ${value.count} 次`,
          confidence,
          last_seen: value.last_seen
        };
      })
      .sort((a, b) => {
        if (b.confidence !== a.confidence) {
          return b.confidence - a.confidence;
        }
        return b.last_seen.localeCompare(a.last_seen);
      })
      .slice(0, 20);
  } catch (error) {
    console.warn("[FRONTEND_V2_RELATION_FALLBACK]", error);
    return [];
  }
}

async function getDashboardDataFromV2(client: SupabaseClient): Promise<DashboardData | null> {
  const evidenceEnabled = readEvidenceLayerFlag();
  const transmissionEnabled = readTransmissionLayerFlag();
  const aiDebateEnabled = readAiDebateViewFlag();

  const [
    sentinelSignals,
    rawOpportunities,
    marketRegime,
    v2Snapshot,
    indirectImpacts,
    alerts,
    alertPrefs,
    portfolioHoldings
  ] = await Promise.all([
    queryV2Signals(client),
    queryV2Opportunities(client),
    queryV2Regime(client),
    queryV2Snapshot(client),
    queryV2IndirectImpacts(client),
    queryAlertCenter(client),
    queryAlertPrefs(client),
    queryPortfolioHoldings(client)
  ]);

  if (!v2Snapshot && sentinelSignals.length === 0 && rawOpportunities.length === 0) {
    return null;
  }

  let opportunities = rawOpportunities;
  if (rawOpportunities.length > 0 && (evidenceEnabled || transmissionEnabled || aiDebateEnabled)) {
    const opportunityIds = rawOpportunities
      .map((item) => Number(item.id || 0))
      .filter((item) => Number.isFinite(item) && item > 0);

    const [evidenceMap, pathMap] = await Promise.all([
      evidenceEnabled ? queryV2EvidenceMap(client, opportunityIds) : Promise.resolve(new Map()),
      transmissionEnabled ? queryV2TransmissionMap(client, opportunityIds) : Promise.resolve(new Map())
    ]);

    opportunities = rawOpportunities.map((item) => {
      const evidenceRows = evidenceEnabled ? (evidenceMap.get(item.id) || []) : [];
      const pathRows = transmissionEnabled ? (pathMap.get(item.id) || []) : [];
      const debateView = aiDebateEnabled ? buildAiDebateView(item) : null;
      return {
        ...item,
        evidences: evidenceRows,
        transmission_paths: pathRows,
        ai_debate_view: debateView
      };
    });
  }

  if (opportunities.length > 0) {
    const sourceEventIds = Array.from(
      new Set(
        opportunities.flatMap((item) => item.source_event_ids || []).filter((item) => item > 0)
      )
    );
    const indirectEventIds = await queryV2IndirectEventIdSet(client, sourceEventIds);
    opportunities = opportunities.map((item) => {
      const hasIndirect = (item.source_event_ids || []).some((eventId) => indirectEventIds.has(eventId));
      return {
        ...item,
        source_origin: hasIndirect ? "Indirect" : "Direct"
      };
    });
  }

  const tickerDigest = buildTickerDigestFromV2(sentinelSignals, opportunities);
  const xSourceRadar = buildXSourceRadar(sentinelSignals, opportunities);
  const focusTickers = new Set(opportunities.map((item) => item.ticker));
  const filteredSignals = focusTickers.size
    ? sentinelSignals.filter((item) => signalMentionsTicker(item, focusTickers))
    : sentinelSignals;

  const [marketSnapshotRaw, v2HotClusters, v2Relations] = await Promise.all([
    queryMarketSnapshot(client, filteredSignals),
    queryV2HotClusters(client),
    queryV2Relations(client)
  ]);
  const tickerUniverse = new Set<string>();
  for (const item of opportunities) {
    if (item.ticker) {
      tickerUniverse.add(item.ticker);
    }
  }
  for (const item of alerts) {
    if (item.ticker) {
      tickerUniverse.add(item.ticker);
    }
  }
  for (const item of tickerDigest) {
    if (item.ticker) {
      tickerUniverse.add(item.ticker);
    }
  }
  for (const item of portfolioHoldings) {
    if (item.ticker) {
      tickerUniverse.add(item.ticker);
    }
  }
  const tickerProfiles = await queryTickerProfiles(client, Array.from(tickerUniverse));
  const hotClusters = v2HotClusters;
  const relations = v2Relations;

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
  const topIndirectTime = indirectImpacts[0]?.as_of || "";
  const dataUpdatedAt = getLatestTimestamp([
    marketSnapshot.updated_at,
    v2Snapshot?.snapshot_time || "",
    topOpportunityTime,
    topSignalTime,
    topClusterTime,
    topRelationTime,
    topIndirectTime
  ]);
  const sourceHealth = await querySourceHealth(client);

  return {
    opportunities,
    alerts,
    alertPrefs,
    portfolioHoldings,
    tickerProfiles,
    marketRegime,
    marketSnapshot,
    dataQuality: buildDataQualitySnapshot(dataUpdatedAt, sourceHealth),
    sentinelSignals: filteredSignals,
    tickerDigest,
    xSourceRadar,
    indirectImpacts,
    hotClusters,
    relations,
    dataUpdatedAt
  };
}

function getLatestTimestamp(values: string[]): string {
  let latestValue = "";
  let latestTs = -1;
  for (const value of values) {
    const currentTs = parseTimestampMs(value);
    if (currentTs === null || currentTs < latestTs) {
      continue;
    }
    latestValue = value;
    latestTs = currentTs;
  }
  return latestValue || new Date().toISOString();
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
      alerts: [],
      alertPrefs: {
        user_id: "system",
        enable_premarket: false,
        enable_postmarket: true,
        daily_alert_cap: 20,
        quiet_hours_start: 0,
        quiet_hours_end: 0,
        watch_tickers: [],
        muted_signal_types: []
      },
      portfolioHoldings: [],
      tickerProfiles: Object.fromEntries(
        fallbackTickerRows.map((row) => [row.ticker, fallbackTickerProfile(row.ticker)])
      ),
      marketRegime: null,
      marketSnapshot: baseSnapshot(),
      dataQuality: buildDataQualitySnapshot(now, { healthy: 0, degraded: 0, critical: 0 }),
      sentinelSignals: [],
      tickerDigest: fallbackTickerRows,
      xSourceRadar: [],
      indirectImpacts: [],
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
  const alerts = await queryAlertCenter(client);
  const alertPrefs = await queryAlertPrefs(client);
  const portfolioHoldings = await queryPortfolioHoldings(client);

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
  const dataUpdatedAt = getLatestTimestamp([
    marketSnapshot.updated_at,
    topOpportunityTime,
    topSignalTime,
    topClusterTime,
    topRelationTime
  ]);
  const sourceHealth = await querySourceHealth(client);
  const xSourceRadar = buildXSourceRadar(filteredSignals, opportunities);
  const tickerUniverse = new Set<string>();
  for (const item of opportunities) {
    if (item.ticker) {
      tickerUniverse.add(item.ticker);
    }
  }
  for (const item of alerts) {
    if (item.ticker) {
      tickerUniverse.add(item.ticker);
    }
  }
  for (const item of tickerDigest) {
    if (item.ticker) {
      tickerUniverse.add(item.ticker);
    }
  }
  for (const item of portfolioHoldings) {
    if (item.ticker) {
      tickerUniverse.add(item.ticker);
    }
  }
  const tickerProfiles = await queryTickerProfiles(client, Array.from(tickerUniverse));

  return {
    opportunities,
    alerts,
    alertPrefs,
    portfolioHoldings,
    tickerProfiles,
    marketRegime,
    marketSnapshot,
    dataQuality: buildDataQualitySnapshot(dataUpdatedAt, sourceHealth),
    sentinelSignals: filteredSignals,
    tickerDigest,
    xSourceRadar,
    indirectImpacts: [],
    hotClusters,
    relations,
    dataUpdatedAt
  };
}
