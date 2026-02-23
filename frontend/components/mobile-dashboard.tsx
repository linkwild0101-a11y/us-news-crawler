"use client";

import { useMemo, useState } from "react";

import { MetricHint } from "@/components/metric-hint";
import { MetricDictionaryCenter } from "@/components/metric-dictionary-center";
import {
  readAiDebateViewFlag,
  readDashboardV3ExplainFlag,
  readEvidenceLayerFlag,
  readTransmissionLayerFlag
} from "@/lib/feature-flags";
import { METRIC_EXPLANATIONS, MetricKey } from "@/lib/metric-explanations";
import {
  AiDebateView,
  DashboardData,
  OpportunityItem,
  RiskLevel,
  SentinelSignal,
  SourceMix,
  TransmissionPath,
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

function freshnessBadgeClass(level: DashboardData["dataQuality"]["freshness_level"]): string {
  if (level === "fresh") {
    return "text-riskLow bg-emerald-500/10 border-emerald-300/30";
  }
  if (level === "stale") {
    return "text-riskMid bg-amber-500/10 border-amber-300/30";
  }
  return "text-riskHigh bg-red-500/10 border-red-400/30";
}

function sourceHealthBadgeClass(status: DashboardData["dataQuality"]["source_health_status"]): string {
  if (status === "healthy") {
    return "text-riskLow bg-emerald-500/10 border-emerald-300/30";
  }
  if (status === "degraded") {
    return "text-riskMid bg-amber-500/10 border-amber-300/30";
  }
  return "text-riskHigh bg-red-500/10 border-red-400/30";
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
  // Use fixed UTC+8 display so SSR/CSR render the same timestamp text.
  const utc8 = new Date(date.getTime() + 8 * 60 * 60 * 1000);
  return `${utc8.getUTCMonth() + 1}/${utc8.getUTCDate()} ${utc8.getUTCHours()}:${String(
    utc8.getUTCMinutes()
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

function resolveSourceBadge(sourceMix?: SourceMix | null): { label: string; className: string } {
  if (!sourceMix || sourceMix.x_count <= 0) {
    return {
      label: "News",
      className: "text-sky-300 bg-sky-500/10 border-sky-300/30"
    };
  }
  if (sourceMix.mixed_sources || sourceMix.article_count > 0) {
    return {
      label: "Mixed",
      className: "text-violet-300 bg-violet-500/10 border-violet-300/30"
    };
  }
  return {
    label: "X",
    className: "text-fuchsia-300 bg-fuchsia-500/10 border-fuchsia-300/30"
  };
}

function formatSourceMixLine(sourceMix?: SourceMix | null): string {
  if (!sourceMix || sourceMix.x_count <= 0) {
    return "主要来自新闻源";
  }
  const percent = Math.round(sourceMix.x_ratio * 100);
  const handles = sourceMix.top_x_handles.length > 0
    ? `；Top X: ${sourceMix.top_x_handles.map((name) => `@${name}`).join(", ")}`
    : "";
  return `X占比 ${percent}%（${sourceMix.x_count}/${sourceMix.source_total}）${handles}`;
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

function estimateEvidenceCompleteness(item: OpportunityItem): {
  label: "高" | "中" | "低";
  className: string;
} {
  const evidences = item.evidences || [];
  const evidenceCount = evidences.length || (item.evidence_ids || []).length;
  const sourceCount = new Set(
    evidences
      .map((row) => row.source_name.trim().toLowerCase())
      .filter((name) => name.length > 0)
  ).size;
  const numericFactCount = evidences.reduce((sum, row) => sum + row.numeric_facts.length, 0);

  if (evidenceCount >= 4 && sourceCount >= 2 && numericFactCount >= 2) {
    return {
      label: "高",
      className: "text-riskLow bg-emerald-500/10 border-emerald-300/30"
    };
  }
  if (evidenceCount >= 2) {
    return {
      label: "中",
      className: "text-riskMid bg-amber-500/10 border-amber-300/30"
    };
  }
  return {
    label: "低",
    className: "text-riskHigh bg-red-500/10 border-red-400/30"
  };
}

function estimateTransmissionStrength(item: OpportunityItem): {
  label: "强" | "中" | "弱";
  className: string;
} {
  const rows = item.transmission_paths || [];
  if (!rows.length) {
    return {
      label: "弱",
      className: "text-textMuted bg-slate-500/10 border-slate-400/30"
    };
  }
  const avg = rows.reduce((sum, row) => sum + row.strength, 0) / rows.length;
  if (avg >= 0.7) {
    return {
      label: "强",
      className: "text-riskLow bg-emerald-500/10 border-emerald-300/30"
    };
  }
  if (avg >= 0.5) {
    return {
      label: "中",
      className: "text-riskMid bg-amber-500/10 border-amber-300/30"
    };
  }
  return {
    label: "弱",
    className: "text-textMuted bg-slate-500/10 border-slate-400/30"
  };
}

function toDebateView(item: OpportunityItem): AiDebateView {
  const direct = item.ai_debate_view;
  if (direct) {
    return direct;
  }
  return {
    pro_case: item.why_now || "当前信号与催化结构支持该方向。",
    counter_case: item.counter_view || "若出现反向宏观催化，该观点可能失效。",
    uncertainties: item.uncertainty_flags?.length
      ? item.uncertainty_flags
      : ["证据时效或来源结构可能影响结论稳定性。"],
    pre_trade_checks: [
      "核对原文关键段落和数字事实。",
      "确认近24小时是否有反向催化。",
      "结合仓位与风控阈值再执行。"
    ]
  };
}

function collectOriginalLinks(item: OpportunityItem): Array<{ label: string; url: string }> {
  const seen = new Set<string>();
  const links: Array<{ label: string; url: string }> = [];
  const evidenceRows = item.evidences || [];
  for (const row of evidenceRows) {
    const url = row.source_url.trim();
    if (!url || seen.has(url)) {
      continue;
    }
    seen.add(url);
    const sourceName = row.source_name.trim() || row.source_type || "source";
    links.push({
      label: `${sourceName} · ${formatTime(row.published_at)}`,
      url
    });
    if (links.length >= 8) {
      break;
    }
  }
  return links;
}

function transmissionDirectionClass(direction: TransmissionPath["direction"]): string {
  if (direction === "LONG") {
    return "text-riskLow";
  }
  if (direction === "SHORT") {
    return "text-riskHigh";
  }
  return "text-textMuted";
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
  const sourceBadge = resolveSourceBadge(signal.source_mix);
  return (
    <article className="rounded-xl border border-slate-700/80 bg-panel p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xs text-textMuted">{signal.sentinel_id}</span>
          <span className={`rounded-md border px-2 py-0.5 text-[10px] ${sourceBadge.className}`}>
            <LabelWithHint label={sourceBadge.label} hintKey="source_mix_badge" />
          </span>
        </div>
        <span className={`rounded-md border px-2 py-0.5 text-xs font-semibold ${levelClass(signal.alert_level)}`}>
          {signal.alert_level} · {Math.round(signal.risk_score * 100)}
        </span>
      </div>
      <p className="text-sm text-textMain">{signal.description}</p>
      <p className="mt-2 text-xs text-textMuted">
        <LabelWithHint label="来源构成" hintKey="x_source_ratio" />: {formatSourceMixLine(signal.source_mix)}
      </p>
      {signal.trigger_reasons.length > 0 && (
        <p className="mt-2 text-xs text-textMuted">
          <LabelWithHint label="触发" hintKey="trigger_reasons" />: {signal.trigger_reasons.slice(0, 2).join("；")}
        </p>
      )}
      <div className="mt-2 text-xs text-textMuted">{formatTime(signal.created_at)}</div>
    </article>
  );
}

function OpportunityCard({
  item,
  onOpenEvidence
}: {
  item: OpportunityItem;
  onOpenEvidence: (item: OpportunityItem) => void;
}) {
  const sourceBadge = resolveSourceBadge(item.source_mix);
  const evidenceBadge = estimateEvidenceCompleteness(item);
  const transmissionBadge = estimateTransmissionStrength(item);
  const evidenceCount = (item.evidences || []).length || (item.evidence_ids || []).length;
  const pathCount = (item.transmission_paths || []).length || (item.path_ids || []).length;
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
      {item.counter_view && (
        <p className="mt-1 text-xs leading-5 text-textMuted">
          反方视角：{item.counter_view}
        </p>
      )}
      <p className="mt-2 text-xs leading-5 text-textMuted">
        <LabelWithHint label="失效条件" hintKey="invalid_if" />: {item.invalid_if}
      </p>

      <div className="mt-3 flex flex-wrap gap-2 text-xs">
        <span className={`rounded-md border px-2 py-1 ${evidenceBadge.className}`}>
          证据完整度 {evidenceBadge.label} · {evidenceCount}
        </span>
        <span className={`rounded-md border px-2 py-1 ${transmissionBadge.className}`}>
          传导链 {transmissionBadge.label} · {pathCount}
        </span>
      </div>

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
        <span className={`mr-2 inline-flex rounded-md border px-2 py-0.5 ${sourceBadge.className}`}>
          <LabelWithHint label={sourceBadge.label} hintKey="source_mix_badge" />
        </span>
        <LabelWithHint label="来源构成" hintKey="x_source_ratio" /> {formatSourceMixLine(item.source_mix)}
      </div>
      <div className="mt-2 text-xs text-textMuted">
        信号证据 {item.source_signal_ids.length} · 聚类证据 {item.source_cluster_ids.length} · 到期
        {" "}
        {formatTime(item.expires_at)}
      </div>
      <button
        type="button"
        onClick={() => onOpenEvidence(item)}
        className="mt-3 rounded-md border border-slate-600 px-2 py-1 text-xs text-textMuted hover:text-textMain"
      >
        查看 Why-Now 证据链
      </button>
    </article>
  );
}

function EvidenceDrawer({
  item,
  onClose,
  enableEvidenceLayer,
  enableTransmissionLayer,
  enableAiDebateView,
  onAddToReview,
  reviewQueued
}: {
  item: OpportunityItem;
  onClose: () => void;
  enableEvidenceLayer: boolean;
  enableTransmissionLayer: boolean;
  enableAiDebateView: boolean;
  onAddToReview: (item: OpportunityItem) => void;
  reviewQueued: boolean;
}) {
  const sourceBadge = resolveSourceBadge(item.source_mix);
  const debate = toDebateView(item);
  const evidenceRows = (enableEvidenceLayer ? item.evidences : []) || [];
  const pathRows = (enableTransmissionLayer ? item.transmission_paths : []) || [];
  const originalLinks = collectOriginalLinks(item);
  return (
    <div
      className="fixed inset-0 z-40 bg-black/70 px-3 py-4 backdrop-blur-sm md:px-6 md:py-8"
      onClick={onClose}
    >
      <div
        className="mx-auto max-h-full max-w-xl overflow-y-auto rounded-2xl border border-slate-700 bg-panel p-4"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold">
              {item.ticker} · {item.side} · H{item.horizon}
            </h3>
            <p className="mt-1 text-xs text-textMuted">更新 {formatTime(item.as_of)}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-600 px-2 py-1 text-xs text-textMuted"
          >
            关闭
          </button>
        </div>

        <article className="rounded-lg border border-slate-700/80 bg-card/40 p-3">
          <div className="flex items-start justify-between gap-3">
            <p className="text-xs text-textMuted">1) 关键证据段落</p>
            <button
              type="button"
              onClick={() => onAddToReview(item)}
              className="rounded-md border border-slate-600 px-2 py-1 text-[11px] text-textMuted hover:text-textMain"
            >
              {reviewQueued ? "已加入复核清单" : "加入复核清单"}
            </button>
          </div>
          {evidenceRows.length > 0 ? (
            <div className="mt-2 space-y-2">
              {evidenceRows.map((row) => (
                <div key={row.id} className="rounded-md border border-slate-700/80 bg-card/70 p-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[11px] text-textMuted">
                      {row.source_name || row.source_type} · {formatTime(row.published_at)}
                    </p>
                    <span className="text-[11px] text-textMuted">
                      置信 {Math.round(row.confidence * 100)}%
                    </span>
                  </div>
                  <p className="mt-1 text-sm leading-6 text-textMain">{row.quote_snippet}</p>
                  {row.numeric_facts.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {row.numeric_facts.slice(0, 3).map((fact, index) => (
                        <span
                          key={`${row.id}-${index}`}
                          className="rounded border border-slate-600/70 bg-card/80 px-1.5 py-0.5 text-[10px] text-textMuted"
                        >
                          {String(fact.raw || fact.value || "--")}
                        </span>
                      ))}
                    </div>
                  )}
                  {row.source_url && (
                    <a
                      className="mt-2 inline-flex rounded border border-slate-600 px-2 py-1 text-[11px] text-textMuted hover:text-textMain"
                      href={row.source_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      查看原文
                    </a>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-1 text-sm text-textMuted">暂无结构化证据，建议直接查看原文链接。</p>
          )}
        </article>

        <article className="mt-3 rounded-lg border border-slate-700/80 bg-card/40 p-3">
          <p className="text-xs text-textMuted">2) 宏观→行业→个股 传导链</p>
          {pathRows.length > 0 ? (
            <div className="mt-2 space-y-2">
              {pathRows.map((row) => (
                <div key={row.id} className="rounded-md border border-slate-700/80 bg-card/70 p-2">
                  <p className="text-sm text-textMain">
                    {row.macro_factor}
                    <span className="mx-1 text-textMuted">→</span>
                    {row.industry}
                    <span className="mx-1 text-textMuted">→</span>
                    {item.ticker}
                  </p>
                  <p className="mt-1 text-xs text-textMuted">
                    <span className={transmissionDirectionClass(row.direction)}>
                      {row.direction}
                    </span>
                    {" · 强度 "}
                    {Math.round(row.strength * 100)}
                    {" · 证据 "}
                    {row.evidence_ids.length}
                  </p>
                  {row.reason && <p className="mt-1 text-xs text-textMuted">{row.reason}</p>}
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-1 text-sm text-textMuted">暂无传导链，先按证据与催化审阅。</p>
          )}
        </article>

        <article className="mt-3 rounded-lg border border-slate-700/80 bg-card/40 p-3">
          <p className="text-xs text-textMuted">3) AI 参考建议（非投资建议）</p>
          <p className="mt-1 text-sm leading-6 text-textMain">
            <strong className="font-semibold">正方：</strong>
            {enableAiDebateView ? debate.pro_case : item.why_now}
          </p>
          <p className="mt-2 text-sm leading-6 text-textMain">
            <strong className="font-semibold">反方：</strong>
            {enableAiDebateView ? debate.counter_case : (item.counter_view || "暂无反方摘要")}
          </p>
          <div className="mt-2">
            <p className="text-xs text-textMuted">不确定性</p>
            <ul className="mt-1 space-y-1 text-sm text-textMain">
              {(enableAiDebateView ? debate.uncertainties : item.uncertainty_flags || []).slice(0, 4).map((line) => (
                <li key={line}>- {line}</li>
              ))}
            </ul>
          </div>
          <p className="mt-2 text-xs text-textMuted">
            <LabelWithHint label="失效条件" hintKey="invalid_if" />: {item.invalid_if}
          </p>
        </article>

        <article className="mt-3 rounded-lg border border-slate-700/80 bg-card/40 p-3">
          <p className="text-xs text-textMuted">4) 原文入口</p>
          <p className="mt-1 text-sm text-textMain">
            <span className={`mr-2 inline-flex rounded-md border px-2 py-0.5 text-[10px] ${sourceBadge.className}`}>
              <LabelWithHint label={sourceBadge.label} hintKey="source_mix_badge" />
            </span>
            {formatSourceMixLine(item.source_mix)}
          </p>
          {originalLinks.length > 0 ? (
            <div className="mt-2 space-y-2">
              {originalLinks.map((link) => (
                <a
                  key={link.url}
                  className="block rounded-md border border-slate-600/80 px-2 py-1 text-xs text-textMuted hover:text-textMain"
                  href={link.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  {link.label}
                </a>
              ))}
            </div>
          ) : (
            <p className="mt-1 text-sm text-textMuted">暂无可直达原文链接。</p>
          )}
          <p className="mt-2 text-xs text-textMuted">证据映射</p>
          <p className="mt-1 text-sm text-textMain">
            信号ID: {item.source_signal_ids.length ? item.source_signal_ids.join(", ") : "无"}
          </p>
          <p className="mt-1 text-sm text-textMain">
            聚类ID: {item.source_cluster_ids.length ? item.source_cluster_ids.join(", ") : "无"}
          </p>
        </article>
      </div>
    </div>
  );
}

export function MobileDashboard({ data }: { data: DashboardData }) {
  const [activeTab, setActiveTab] = useState<DashboardTab>("opportunities");
  const [dictOpen, setDictOpen] = useState(false);
  const [selectedOpportunity, setSelectedOpportunity] = useState<OpportunityItem | null>(null);
  const [reviewQueuedMap, setReviewQueuedMap] = useState<Record<number, boolean>>({});
  const showV3ExplainBadge = readDashboardV3ExplainFlag();
  const enableEvidenceLayer = readEvidenceLayerFlag();
  const enableTransmissionLayer = readTransmissionLayerFlag();
  const enableAiDebateView = readAiDebateViewFlag();

  const rankedTicker = useMemo(() => rankTicker(data.tickerDigest), [data.tickerDigest]);
  const opportunities = useMemo(() => rankOpportunities(data.opportunities), [data.opportunities]);
  const longOpportunities = opportunities.filter((item) => item.side === "LONG");
  const shortOpportunities = opportunities.filter((item) => item.side === "SHORT");
  const topSignals = data.sentinelSignals.slice(0, 16);
  const topClusters = data.hotClusters.slice(0, 12);
  const topRelations = data.relations.slice(0, 10);
  const xRadar = data.xSourceRadar.slice(0, 8);

  function handleAddToReviewQueue(item: OpportunityItem): void {
    const storageKey = "stock_review_queue_v1";
    try {
      const raw = window.localStorage.getItem(storageKey);
      const parsed = raw ? JSON.parse(raw) : [];
      const list = Array.isArray(parsed) ? parsed : [];
      const next = [
        {
          id: item.id,
          ticker: item.ticker,
          side: item.side,
          horizon: item.horizon,
          as_of: item.as_of
        },
        ...list.filter((row) => Number((row as { id?: unknown }).id || 0) !== item.id)
      ].slice(0, 120);
      window.localStorage.setItem(storageKey, JSON.stringify(next));
    } catch (error) {
      console.warn("[FRONTEND_REVIEW_QUEUE_FALLBACK]", error);
    }
    setReviewQueuedMap((prev) => ({ ...prev, [item.id]: true }));
  }

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
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              <span
                className={`rounded-md border px-2 py-0.5 font-semibold ${freshnessBadgeClass(data.dataQuality.freshness_level)}`}
              >
                <LabelWithHint
                  label={`新鲜度 ${data.dataQuality.freshness_minutes}m`}
                  hintKey="data_freshness_badge"
                />
              </span>
              <span
                className={`rounded-md border px-2 py-0.5 font-semibold ${sourceHealthBadgeClass(data.dataQuality.source_health_status)}`}
              >
                <LabelWithHint
                  label={
                    `质量 H/D/C ${data.dataQuality.source_health_healthy}/`
                    + `${data.dataQuality.source_health_degraded}/`
                    + `${data.dataQuality.source_health_critical}`
                  }
                  hintKey="source_health_badge"
                />
              </span>
            </div>
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
                <OpportunityCard
                  key={item.id}
                  item={item}
                  onOpenEvidence={(selected) => setSelectedOpportunity(selected)}
                />
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

          <article className="rounded-xl border border-slate-700/80 bg-panel p-4">
            <h2 className="mb-3 text-sm font-semibold">X 信源雷达</h2>
            {xRadar.length > 0 ? (
              <div className="grid gap-3 sm:grid-cols-2">
                {xRadar.map((item) => (
                  <div key={item.handle} className="rounded-lg border border-slate-700/80 bg-card/40 p-3">
                    <div className="mb-1 text-sm font-semibold">@{item.handle}</div>
                    <div className="text-xs text-textMuted">
                      提及 {item.mentions} · Mixed {item.mixed_count}
                    </div>
                    <div className="mt-1 text-xs text-textMuted">
                      平均X占比 {Math.round(item.avg_x_ratio * 100)}% · {formatTime(item.latest_at)}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-textMuted">暂无 X 信源贡献数据。</p>
            )}
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

      {selectedOpportunity && (
        <EvidenceDrawer
          item={selectedOpportunity}
          onClose={() => setSelectedOpportunity(null)}
          enableEvidenceLayer={enableEvidenceLayer}
          enableTransmissionLayer={enableTransmissionLayer}
          enableAiDebateView={enableAiDebateView}
          onAddToReview={handleAddToReviewQueue}
          reviewQueued={Boolean(reviewQueuedMap[selectedOpportunity.id])}
        />
      )}

      <MetricDictionaryCenter open={dictOpen} onClose={() => setDictOpen(false)} />
    </div>
  );
}
