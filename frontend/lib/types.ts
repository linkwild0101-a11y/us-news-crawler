export type RiskLevel = "L0" | "L1" | "L2" | "L3" | "L4";

export interface SourceMix {
  x_count: number;
  article_count: number;
  other_count: number;
  source_total: number;
  x_ratio: number;
  mixed_sources: boolean;
  top_x_handles: string[];
  latest_x_at: string;
  latest_news_at: string;
}

export interface MarketSnapshot {
  snapshot_date: string;
  spy: number | null;
  qqq: number | null;
  dia: number | null;
  vix: number | null;
  us10y: number | null;
  dxy: number | null;
  risk_level: RiskLevel;
  daily_brief: string;
  updated_at: string;
}

export interface SentinelSignal {
  id: number;
  cluster_id: number | null;
  sentinel_id: string;
  alert_level: RiskLevel;
  risk_score: number;
  description: string;
  trigger_reasons: string[];
  evidence_links: string[];
  source_mix?: SourceMix | null;
  created_at: string;
}

export interface TickerSignalDigest {
  ticker: string;
  signal_count_24h: number;
  related_cluster_count_24h: number;
  risk_level: RiskLevel;
  top_sentinel_levels: string[];
  updated_at: string;
}

export interface HotCluster {
  id: number;
  category: string;
  primary_title: string;
  summary: string;
  article_count: number;
  created_at: string;
}

export interface EntityRelationItem {
  id: number;
  entity1_name: string;
  entity2_name: string;
  relation_text: string;
  confidence: number;
  last_seen: string;
}

export interface OpportunityItem {
  id: number;
  ticker: string;
  side: "LONG" | "SHORT";
  horizon: "A" | "B";
  opportunity_score: number;
  confidence: number;
  risk_level: RiskLevel;
  why_now: string;
  invalid_if: string;
  catalysts: string[];
  factor_breakdown: Record<string, number>;
  source_signal_ids: number[];
  source_cluster_ids: number[];
  source_event_ids?: number[];
  source_origin?: "Direct" | "Indirect";
  source_mix?: SourceMix | null;
  evidence_ids?: number[];
  path_ids?: number[];
  uncertainty_flags?: string[];
  counter_view?: string;
  ai_debate_view?: AiDebateView | null;
  evidences?: EvidenceItem[];
  transmission_paths?: TransmissionPath[];
  expires_at: string;
  as_of: string;
}

export interface EvidenceItem {
  id: number;
  opportunity_id: number | null;
  ticker: string;
  source_type: string;
  source_ref: string;
  source_url: string;
  source_name: string;
  published_at: string;
  quote_snippet: string;
  numeric_facts: Array<Record<string, unknown>>;
  confidence: number;
  as_of: string;
}

export interface TransmissionPath {
  id: number;
  opportunity_id: number | null;
  path_key: string;
  ticker: string;
  macro_factor: string;
  industry: string;
  direction: "LONG" | "SHORT" | "NEUTRAL";
  strength: number;
  reason: string;
  evidence_ids: number[];
  as_of: string;
}

export interface AiDebateView {
  pro_case: string;
  counter_case: string;
  uncertainties: string[];
  pre_trade_checks: string[];
}

export interface XSourceRadarItem {
  handle: string;
  mentions: number;
  mixed_count: number;
  avg_x_ratio: number;
  latest_at: string;
}

export interface IndirectImpactItem {
  id: number;
  theme: string;
  impact_scope: "index" | "sector" | "ticker";
  summary: string;
  candidate_tickers: string[];
  relevance_score: number;
  confidence: number;
  promotion_status: "pending" | "promoted" | "rejected";
  as_of: string;
}

export interface MarketRegime {
  regime_date: string;
  risk_state: string;
  vol_state: string;
  liquidity_state: string;
  regime_score: number;
  summary: string;
}

export interface DashboardData {
  opportunities: OpportunityItem[];
  alerts: AlertCenterItem[];
  alertPrefs: AlertUserPrefs;
  portfolioHoldings: PortfolioHoldingItem[];
  portfolioAdvice: PortfolioAdviceItem[];
  tickerProfiles: Record<string, TickerProfileItem>;
  marketRegime: MarketRegime | null;
  marketSnapshot: MarketSnapshot;
  dataQuality: DataQualitySnapshot;
  sentinelSignals: SentinelSignal[];
  tickerDigest: TickerSignalDigest[];
  xSourceRadar: XSourceRadarItem[];
  indirectImpacts: IndirectImpactItem[];
  hotClusters: HotCluster[];
  relations: EntityRelationItem[];
  dataUpdatedAt: string;
}

export interface DataQualitySnapshot {
  freshness_minutes: number;
  freshness_level: "fresh" | "stale" | "critical";
  source_health_status: "healthy" | "degraded" | "critical";
  source_health_healthy: number;
  source_health_degraded: number;
  source_health_critical: number;
}

export type AlertSide = "LONG" | "SHORT" | "NEUTRAL";
export type AlertStatus = "pending" | "sent" | "deduped" | "dropped";
export type AlertFeedbackLabel = "useful" | "noise";

export interface AlertCenterItem {
  id: number;
  user_id: string;
  ticker: string;
  signal_type: string;
  signal_level: RiskLevel;
  alert_score: number;
  side: AlertSide;
  title: string;
  why_now: string;
  session_tag: string;
  status: AlertStatus;
  dedupe_window: string;
  created_at: string;
  feedback_useful_count: number;
  feedback_noise_count: number;
  latest_feedback_label: AlertFeedbackLabel | null;
}

export interface AlertUserPrefs {
  user_id: string;
  enable_premarket: boolean;
  enable_postmarket: boolean;
  daily_alert_cap: number;
  quiet_hours_start: number;
  quiet_hours_end: number;
  watch_tickers: string[];
  muted_signal_types: string[];
}

export interface PortfolioHoldingItem {
  id: number;
  portfolio_id: number;
  user_id: string;
  ticker: string;
  side: "LONG" | "SHORT";
  quantity: number;
  avg_cost: number;
  market_value: number;
  weight: number;
  notes: string;
  updated_at: string;
}

export type PortfolioAdviceType = "add" | "reduce" | "hold" | "hedge" | "watch" | "review";
export type PortfolioAdviceStatus = "pending" | "accepted" | "dismissed" | "expired";

export interface PortfolioAdviceItem {
  id: number;
  advice_key: string;
  user_id: string;
  portfolio_id: number;
  ticker: string;
  holding_side: "LONG" | "SHORT";
  advice_type: PortfolioAdviceType;
  action_side: "LONG" | "SHORT" | "NEUTRAL";
  priority_score: number;
  confidence: number;
  risk_level: RiskLevel;
  trigger_points: string[];
  invalid_if: string;
  status: PortfolioAdviceStatus;
  valid_until: string;
  as_of: string;
  updated_at: string;
}

export interface TickerProfileItem {
  ticker: string;
  display_name: string;
  asset_type: "equity" | "etf" | "index" | "macro" | "unknown";
  sector: string;
  industry: string;
  summary_cn: string;
}
