"use client";

import { useMemo, useState } from "react";

import { MetricHint } from "@/components/metric-hint";
import { MetricDictionaryCenter } from "@/components/metric-dictionary-center";
import { readDashboardV3ExplainFlag } from "@/lib/feature-flags";
import { METRIC_EXPLANATIONS, MetricKey } from "@/lib/metric-explanations";
import {
  DashboardData,
  OpportunityItem,
  RiskLevel,
  SentinelSignal,
  TickerSignalDigest
} from "@/lib/types";

type DashboardTab = "opportunities" | "market" | "signals" | "evidence";

const TABS: { id: DashboardTab; label: string; icon: string }[] = [
  { id: "opportunities", label: "机会", icon: "🎯" },
  { id: "market", label: "市场", icon: "📈" },
  { id: "signals", label: "信号", icon: "🚨" },
  { id: "evidence", label: "证据", icon: "🧩" }
];

function levelClass(level: RiskLevel): string {
  if (level === "L4" || level === "L3") {
    return "text-riskHigh bg-red-500/10 border-red-400/30";
  }
  if (level === "L2") {
    return "text-riskMid bg-amber-500/10 border-amber-300/30";
  }
  return "text-riskLow bg-emerald-500/10 border-emerald-300/30";
}

function sideClass(side: OpportunityItem["side"]): string {
  if (side === "LONG") {
    return "text-riskLow bg-emerald-500/10 border-emerald-300/30";
  }
  return "text-riskHigh bg-red-500/10 border-red-400/30";
}

function horizonClass(horizon: OpportunityItem["horizon"]): string {
  if (horizon === "A") {
    return "text-accent bg-cyan-500/10 border-cyan-300/30";
  }
  return "text-textMuted bg-slate-500/10 border-slate-300/30";
}

function formatNumber(value: number | null, digits = 2): string {
  if (value === null || Number.isNaN(value)) {
    return "--";
  }
  return value.toFixed(digits);
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:${String(
    date.getMinutes()
  ).padStart(2, "0")}`;
}

function levelWeight(level: RiskLevel): number {
  if (level === "L4") {
    return 4;
  }
  if (level === "L3") {
    return 3;
  }
  if (level === "L2") {
    return 2;
  }
  if (level === "L1") {
    return 1;
  }
  return 0;
}

function rankTicker(items: TickerSignalDigest[]): TickerSignalDigest[] {
  return [...items].sort((a, b) => {
    const riskDiff = levelWeight(b.risk_level) - levelWeight(a.risk_level);
    if (riskDiff !== 0) {
      return riskDiff;
    }
    return b.signal_count_24h - a.signal_count_24h;
  });
}

function rankOpportunities(items: OpportunityItem[]): OpportunityItem[] {
  return [...items].sort((a, b) => {
    if (a.horizon !== b.horizon) {
      return a.horizon === "A" ? -1 : 1;
    }
    if (b.opportunity_score !== a.opportunity_score) {
      return b.opportunity_score - a.opportunity_score;
    }
    return b.confidence - a.confidence;
  });
}

function LabelWithHint({ label, hintKey }: { label: string; hintKey: MetricKey }) {
  return (
    <span className="inline-flex items-center">
      {label}
      <MetricHint explanation={METRIC_EXPLANATIONS[hintKey]} />
    </span>
  );
}

function SignalCard({ signal }: { signal: SentinelSignal }) {
  return (
    <article className="rounded-xl border border-slate-700/80 bg-panel p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-xs text-textMuted">{signal.sentinel_id}</span>
        <span className={`rounded-md border px-2 py-0.5 text-xs font-semibold ${levelClass(signal.alert_level)}`}>
          {signal.alert_level} · {Math.round(signal.risk_score * 100)}
        </span>
      </div>
      <p className="text-sm text-textMain">{signal.description}</p>
      {signal.trigger_reasons.length > 0 && (
        <p className="mt-2 text-xs text-textMuted">
          <LabelWithHint label="触发" hintKey="trigger_reasons" />: {signal.trigger_reasons.slice(0, 2).join("；")}
        </p>
      )}
      <div className="mt-2 text-xs text-textMuted">{formatTime(signal.created_at)}</div>
    </article>
  );
}

function OpportunityCard({ item }: { item: OpportunityItem }) {
  return (
    <article className="rounded-xl border border-slate-700/80 bg-panel p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">{item.ticker}</h3>
          <p className="mt-1 text-xs text-textMuted">更新 {formatTime(item.as_of)}</p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <span className={`rounded-md border px-2 py-0.5 text-xs font-semibold ${sideClass(item.side)}`}>
            {item.side}
          </span>
          <span className={`rounded-md border px-2 py-0.5 text-xs font-semibold ${horizonClass(item.horizon)}`}>
            H{item.horizon}
          </span>
          <span className={`rounded-md border px-2 py-0.5 text-xs font-semibold ${levelClass(item.risk_level)}`}>
            {item.risk_level}
          </span>
        </div>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-2 text-sm">
        <div className="rounded-lg bg-card/70 p-2">
          <div className="text-xs text-textMuted">
            <LabelWithHint label="机会分" hintKey="opportunity_score" />
          </div>
          <div className="mt-1 font-semibold">{item.opportunity_score.toFixed(1)}</div>
        </div>
        <div className="rounded-lg bg-card/70 p-2">
          <div className="text-xs text-textMuted">
            <LabelWithHint label="置信度" hintKey="confidence" />
          </div>
          <div className="mt-1 font-semibold">{Math.round(item.confidence * 100)}%</div>
        </div>
      </div>

      <p className="text-sm leading-6 text-textMain">{item.why_now}</p>
      <p className="mt-2 text-xs leading-5 text-textMuted">
        <LabelWithHint label="失效条件" hintKey="invalid_if" />: {item.invalid_if}
      </p>

      {item.catalysts.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {item.catalysts.slice(0, 3).map((catalyst) => (
            <span
              key={`${item.id}-${catalyst}`}
              className="rounded-md border border-slate-600/70 bg-card/70 px-2 py-1 text-xs text-textMuted"
            >
              {catalyst}
            </span>
          ))}
        </div>
      )}

      <div className="mt-3 text-xs text-textMuted">
        信号证据 {item.source_signal_ids.length} · 聚类证据 {item.source_cluster_ids.length} · 到期
        {" "}
        {formatTime(item.expires_at)}
      </div>
    </article>
  );
}

export function MobileDashboard({ data }: { data: DashboardData }) {
  const [activeTab, setActiveTab] = useState<DashboardTab>("opportunities");
  const [dictOpen, setDictOpen] = useState(false);
  const showV3ExplainBadge = readDashboardV3ExplainFlag();

  const rankedTicker = useMemo(() => rankTicker(data.tickerDigest), [data.tickerDigest]);
  const opportunities = useMemo(() => rankOpportunities(data.opportunities), [data.opportunities]);
  const longOpportunities = opportunities.filter((item) => item.side === "LONG");
  const shortOpportunities = opportunities.filter((item) => item.side === "SHORT");
  const topSignals = data.sentinelSignals.slice(0, 16);
  const topClusters = data.hotClusters.slice(0, 12);
  const topRelations = data.relations.slice(0, 10);

  return (
    <div className="mx-auto min-h-screen max-w-6xl bg-bg px-4 pb-24 pt-4 text-textMain md:px-6 md:pb-10">
      <header className="mb-4 rounded-2xl border border-slate-700/80 bg-panel p-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold">
              US-Monitor 美股机会看板
              {showV3ExplainBadge && (
                <span className="ml-2 rounded border border-cyan-400/40 px-1.5 py-0.5 text-[10px] text-accent">
                  V3 Explain Beta
                </span>
              )}
            </h1>
            <p className="mt-1 text-xs text-textMuted">数据更新时间: {formatTime(data.dataUpdatedAt)}</p>
            {data.marketRegime?.summary && (
              <p className="mt-2 text-xs text-textMuted">
                <LabelWithHint label="市场状态" hintKey="market_state_summary" />: {data.marketRegime.summary}
              </p>
            )}
          </div>
          <div className="flex items-start gap-2">
            <button
              type="button"
              onClick={() => setDictOpen(true)}
              className="rounded-md border border-slate-600 px-2 py-1 text-xs text-textMuted hover:text-textMain"
            >
              指标字典
            </button>
            <span className={`rounded-md border px-2 py-1 text-xs font-semibold ${levelClass(data.marketSnapshot.risk_level)}`}>
              <LabelWithHint label={`风险 ${data.marketSnapshot.risk_level}`} hintKey="dashboard_risk_level" />
            </span>
          </div>
        </div>
      </header>

      <nav className="mb-4 hidden grid-cols-4 gap-2 md:grid">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={`rounded-xl border px-3 py-2 text-sm transition ${
              activeTab === tab.id
                ? "border-accent/60 bg-card text-textMain"
                : "border-slate-700/80 bg-panel text-textMuted"
            }`}
          >
            {tab.icon} {tab.label}
          </button>
        ))}
      </nav>

      {activeTab === "opportunities" && (
        <section className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <article className="rounded-xl border border-slate-700/80 bg-panel p-3">
              <div className="text-xs text-textMuted">
                <LabelWithHint label="总机会数" hintKey="total_opportunities" />
              </div>
              <div className="mt-1 text-lg font-semibold">{opportunities.length}</div>
            </article>
            <article className="rounded-xl border border-slate-700/80 bg-panel p-3">
              <div className="text-xs text-textMuted">
                <LabelWithHint label="Horizon A" hintKey="horizon_a" />
              </div>
              <div className="mt-1 text-lg font-semibold">
                {opportunities.filter((item) => item.horizon === "A").length}
              </div>
            </article>
            <article className="rounded-xl border border-slate-700/80 bg-panel p-3">
              <div className="text-xs text-textMuted">
                <LabelWithHint label="LONG" hintKey="long_count" />
              </div>
              <div className="mt-1 text-lg font-semibold text-riskLow">{longOpportunities.length}</div>
            </article>
            <article className="rounded-xl border border-slate-700/80 bg-panel p-3">
              <div className="text-xs text-textMuted">
                <LabelWithHint label="SHORT" hintKey="short_count" />
              </div>
              <div className="mt-1 text-lg font-semibold text-riskHigh">{shortOpportunities.length}</div>
            </article>
          </div>

          <article className="rounded-xl border border-slate-700/80 bg-panel p-4">
            <div className="mb-2 text-sm font-semibold">机会简报</div>
            <p className="text-sm leading-6 text-textMain">{data.marketSnapshot.daily_brief}</p>
          </article>

          {opportunities.length > 0 ? (
            <div className="grid gap-3 lg:grid-cols-2">
              {opportunities.map((item) => (
                <OpportunityCard key={item.id} item={item} />
              ))}
            </div>
          ) : (
            <article className="rounded-xl border border-slate-700/80 bg-panel p-4 text-sm text-textMuted">
              暂无可交易机会，建议等待新的美股催化信号。
            </article>
          )}
        </section>
      )}

      {activeTab === "market" && (
        <section className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
            <article className="rounded-xl border border-slate-700/80 bg-panel p-3">
              <div className="text-xs text-textMuted">
                <LabelWithHint label="SPY" hintKey="spy" />
              </div>
              <div className="mt-1 text-lg font-semibold">{formatNumber(data.marketSnapshot.spy)}</div>
            </article>
            <article className="rounded-xl border border-slate-700/80 bg-panel p-3">
              <div className="text-xs text-textMuted">
                <LabelWithHint label="QQQ" hintKey="qqq" />
              </div>
              <div className="mt-1 text-lg font-semibold">{formatNumber(data.marketSnapshot.qqq)}</div>
            </article>
            <article className="rounded-xl border border-slate-700/80 bg-panel p-3">
              <div className="text-xs text-textMuted">
                <LabelWithHint label="DIA" hintKey="dia" />
              </div>
              <div className="mt-1 text-lg font-semibold">{formatNumber(data.marketSnapshot.dia)}</div>
            </article>
            <article className="rounded-xl border border-slate-700/80 bg-panel p-3">
              <div className="text-xs text-textMuted">
                <LabelWithHint label="VIX" hintKey="vix" />
              </div>
              <div className="mt-1 text-lg font-semibold">{formatNumber(data.marketSnapshot.vix)}</div>
            </article>
            <article className="rounded-xl border border-slate-700/80 bg-panel p-3">
              <div className="text-xs text-textMuted">
                <LabelWithHint label="10Y" hintKey="us10y" />
              </div>
              <div className="mt-1 text-lg font-semibold">{formatNumber(data.marketSnapshot.us10y)}</div>
            </article>
            <article className="rounded-xl border border-slate-700/80 bg-panel p-3">
              <div className="text-xs text-textMuted">
                <LabelWithHint label="DXY" hintKey="dxy" />
              </div>
              <div className="mt-1 text-lg font-semibold">{formatNumber(data.marketSnapshot.dxy)}</div>
            </article>
          </div>

          <article className="rounded-xl border border-slate-700/80 bg-panel p-4">
            <h2 className="mb-3 text-sm font-semibold">股票信号热度</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {rankedTicker.slice(0, 10).map((row) => (
                <div key={row.ticker} className="rounded-lg border border-slate-700/80 bg-card/40 p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <div className="font-semibold">{row.ticker}</div>
                    <span className={`rounded-md border px-2 py-0.5 text-xs font-semibold ${levelClass(row.risk_level)}`}>
                      {row.risk_level}
                    </span>
                  </div>
                  <div className="text-xs text-textMuted">
                    <LabelWithHint label="24h 信号" hintKey="signal_count_24h" /> {row.signal_count_24h}
                    {" · "}
                    <LabelWithHint label="关联热点" hintKey="related_cluster_count_24h" /> {row.related_cluster_count_24h}
                  </div>
                </div>
              ))}
            </div>
          </article>
        </section>
      )}

      {activeTab === "signals" && (
        <section className="space-y-4">
          <article className="rounded-xl border border-slate-700/80 bg-panel p-4">
            <h2 className="mb-3 text-sm font-semibold">
              最新 L1-L4 哨兵（仅美股相关）
              <MetricHint explanation={METRIC_EXPLANATIONS.sentinel_level_score} />
            </h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {topSignals.length > 0 ? (
                topSignals.map((signal) => <SignalCard key={signal.id} signal={signal} />)
              ) : (
                <p className="text-sm text-textMuted">暂无美股相关哨兵告警</p>
              )}
            </div>
          </article>
        </section>
      )}

      {activeTab === "evidence" && (
        <section className="space-y-4">
          <article className="rounded-xl border border-slate-700/80 bg-panel p-4">
            <h2 className="mb-3 text-sm font-semibold">热点聚类（股票相关）</h2>
            <div className="space-y-3">
              {topClusters.length > 0 ? (
                topClusters.map((cluster) => (
                  <div key={cluster.id} className="rounded-lg border border-slate-700/80 bg-card/40 p-3">
                    <p className="text-sm font-medium">{cluster.primary_title}</p>
                    <p className="mt-1 line-clamp-3 text-xs text-textMuted">{cluster.summary}</p>
                    <div className="mt-2 text-xs text-textMuted">
                      {cluster.category}
                      {" · "}
                      <LabelWithHint label={`${cluster.article_count} 篇`} hintKey="cluster_article_count" />
                      {" · "}
                      {formatTime(cluster.created_at)}
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-sm text-textMuted">暂无股票相关热点聚类</p>
              )}
            </div>
          </article>

          <article className="rounded-xl border border-slate-700/80 bg-panel p-4">
            <h2 className="mb-3 text-sm font-semibold">实体关系（股票相关）</h2>
            <div className="space-y-2">
              {topRelations.length > 0 ? (
                topRelations.map((relation) => (
                  <div key={relation.id} className="rounded-lg border border-slate-700/80 bg-card/40 p-3">
                    <p className="text-sm">
                      <span className="font-medium">{relation.entity1_name}</span>
                      <span className="mx-1 text-textMuted">↔</span>
                      <span className="font-medium">{relation.entity2_name}</span>
                    </p>
                    <p className="mt-1 text-xs text-textMuted">{relation.relation_text}</p>
                    <p className="mt-1 text-xs text-textMuted">
                      <LabelWithHint label={`置信度 ${Math.round(relation.confidence * 100)}`} hintKey="relation_confidence" />
                      {" · "}
                      {formatTime(relation.last_seen)}
                    </p>
                  </div>
                ))
              ) : (
                <p className="text-sm text-textMuted">暂无股票相关关系数据</p>
              )}
            </div>
          </article>
        </section>
      )}

      <nav className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-4 gap-1 border-t border-slate-700/80 bg-panel/95 px-2 py-2 backdrop-blur md:hidden">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={`rounded-lg px-2 py-1 text-xs ${
              activeTab === tab.id ? "bg-card text-textMain" : "text-textMuted"
            }`}
          >
            <div>{tab.icon}</div>
            <div>{tab.label}</div>
          </button>
        ))}
      </nav>

      <MetricDictionaryCenter open={dictOpen} onClose={() => setDictOpen(false)} />
    </div>
  );
}
