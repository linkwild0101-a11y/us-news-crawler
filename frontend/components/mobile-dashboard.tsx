"use client";

import { useMemo, useState } from "react";

import { DashboardData, RiskLevel, SentinelSignal, TickerSignalDigest } from "@/lib/types";

type DashboardTab = "market" | "signals" | "stocks" | "news";

const TABS: { id: DashboardTab; label: string; icon: string }[] = [
  { id: "market", label: "市场", icon: "📈" },
  { id: "signals", label: "哨兵", icon: "🚨" },
  { id: "stocks", label: "看板", icon: "🧭" },
  { id: "news", label: "新闻", icon: "📰" }
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
        <p className="mt-2 text-xs text-textMuted">触发: {signal.trigger_reasons.slice(0, 2).join("；")}</p>
      )}
      <div className="mt-2 text-xs text-textMuted">{formatTime(signal.created_at)}</div>
    </article>
  );
}

export function MobileDashboard({ data }: { data: DashboardData }) {
  const [activeTab, setActiveTab] = useState<DashboardTab>("market");

  const rankedTicker = useMemo(() => rankTicker(data.tickerDigest), [data.tickerDigest]);
  const topSignals = data.sentinelSignals.slice(0, 10);
  const topClusters = data.hotClusters.slice(0, 12);
  const topRelations = data.relations.slice(0, 10);

  return (
    <div className="mx-auto min-h-screen max-w-6xl bg-bg px-4 pb-24 pt-4 text-textMain md:px-6 md:pb-10">
      <header className="mb-4 rounded-2xl border border-slate-700/80 bg-panel p-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold">US-Monitor 移动看板</h1>
            <p className="mt-1 text-xs text-textMuted">数据更新时间: {formatTime(data.dataUpdatedAt)}</p>
          </div>
          <span className={`rounded-md border px-2 py-1 text-xs font-semibold ${levelClass(data.marketSnapshot.risk_level)}`}>
            风险 {data.marketSnapshot.risk_level}
          </span>
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

      {activeTab === "market" && (
        <section className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
            <article className="rounded-xl border border-slate-700/80 bg-panel p-3">
              <div className="text-xs text-textMuted">SPY</div>
              <div className="mt-1 text-lg font-semibold">{formatNumber(data.marketSnapshot.spy)}</div>
            </article>
            <article className="rounded-xl border border-slate-700/80 bg-panel p-3">
              <div className="text-xs text-textMuted">QQQ</div>
              <div className="mt-1 text-lg font-semibold">{formatNumber(data.marketSnapshot.qqq)}</div>
            </article>
            <article className="rounded-xl border border-slate-700/80 bg-panel p-3">
              <div className="text-xs text-textMuted">DIA</div>
              <div className="mt-1 text-lg font-semibold">{formatNumber(data.marketSnapshot.dia)}</div>
            </article>
            <article className="rounded-xl border border-slate-700/80 bg-panel p-3">
              <div className="text-xs text-textMuted">VIX</div>
              <div className="mt-1 text-lg font-semibold">{formatNumber(data.marketSnapshot.vix)}</div>
            </article>
            <article className="rounded-xl border border-slate-700/80 bg-panel p-3">
              <div className="text-xs text-textMuted">10Y</div>
              <div className="mt-1 text-lg font-semibold">{formatNumber(data.marketSnapshot.us10y)}</div>
            </article>
            <article className="rounded-xl border border-slate-700/80 bg-panel p-3">
              <div className="text-xs text-textMuted">DXY</div>
              <div className="mt-1 text-lg font-semibold">{formatNumber(data.marketSnapshot.dxy)}</div>
            </article>
          </div>
          <article className="rounded-xl border border-slate-700/80 bg-panel p-4">
            <div className="mb-2 text-sm font-semibold">当日简报</div>
            <p className="text-sm leading-6 text-textMain">{data.marketSnapshot.daily_brief}</p>
          </article>
          <article className="rounded-xl border border-slate-700/80 bg-panel p-4">
            <div className="mb-3 text-sm font-semibold">最新 L1-L4 信号</div>
            <div className="grid gap-3 sm:grid-cols-2">
              {topSignals.length > 0 ? (
                topSignals.slice(0, 4).map((signal) => <SignalCard key={signal.id} signal={signal} />)
              ) : (
                <p className="text-sm text-textMuted">暂无信号</p>
              )}
            </div>
          </article>
        </section>
      )}

      {activeTab === "signals" && (
        <section className="grid gap-3 sm:grid-cols-2">
          {topSignals.length > 0 ? (
            topSignals.map((signal) => <SignalCard key={signal.id} signal={signal} />)
          ) : (
            <article className="rounded-xl border border-slate-700/80 bg-panel p-4 text-sm text-textMuted">
              暂无哨兵告警
            </article>
          )}
        </section>
      )}

      {activeTab === "stocks" && (
        <section className="space-y-3">
          {rankedTicker.map((row) => (
            <article
              key={row.ticker}
              className="rounded-xl border border-slate-700/80 bg-panel p-3"
            >
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-base font-semibold">{row.ticker}</h3>
                <span className={`rounded-md border px-2 py-0.5 text-xs font-semibold ${levelClass(row.risk_level)}`}>
                  {row.risk_level}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="rounded-lg bg-card/70 p-2">
                  <div className="text-xs text-textMuted">24h 信号数</div>
                  <div className="mt-1 font-semibold">{row.signal_count_24h}</div>
                </div>
                <div className="rounded-lg bg-card/70 p-2">
                  <div className="text-xs text-textMuted">关联热点</div>
                  <div className="mt-1 font-semibold">{row.related_cluster_count_24h}</div>
                </div>
              </div>
              {row.top_sentinel_levels.length > 0 && (
                <p className="mt-2 text-xs text-textMuted">高频等级: {row.top_sentinel_levels.join(", ")}</p>
              )}
            </article>
          ))}
        </section>
      )}

      {activeTab === "news" && (
        <section className="space-y-4">
          <article className="rounded-xl border border-slate-700/80 bg-panel p-4">
            <h2 className="mb-3 text-sm font-semibold">热点聚类</h2>
            <div className="space-y-3">
              {topClusters.length > 0 ? (
                topClusters.map((cluster) => (
                  <div key={cluster.id} className="rounded-lg border border-slate-700/80 bg-card/40 p-3">
                    <p className="text-sm font-medium">{cluster.primary_title}</p>
                    <p className="mt-1 line-clamp-3 text-xs text-textMuted">{cluster.summary}</p>
                    <div className="mt-2 text-xs text-textMuted">
                      {cluster.category} · {cluster.article_count} 篇 · {formatTime(cluster.created_at)}
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-sm text-textMuted">暂无热点聚类</p>
              )}
            </div>
          </article>

          <article className="rounded-xl border border-slate-700/80 bg-panel p-4">
            <h2 className="mb-3 text-sm font-semibold">实体关系</h2>
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
                      置信度 {Math.round(relation.confidence * 100)} · {formatTime(relation.last_seen)}
                    </p>
                  </div>
                ))
              ) : (
                <p className="text-sm text-textMuted">暂无关系数据</p>
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
    </div>
  );
}
