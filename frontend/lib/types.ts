export type RiskLevel = "L0" | "L1" | "L2" | "L3" | "L4";

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
  expires_at: string;
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
  marketRegime: MarketRegime | null;
  marketSnapshot: MarketSnapshot;
  dataQuality: DataQualitySnapshot;
  sentinelSignals: SentinelSignal[];
  tickerDigest: TickerSignalDigest[];
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
