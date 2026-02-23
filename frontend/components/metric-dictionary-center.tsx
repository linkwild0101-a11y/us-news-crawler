"use client";

import { useMemo, useState } from "react";

import { METRIC_DICTIONARY_ITEMS, MetricDictionaryItem } from "@/lib/metric-explanations";

interface MetricDictionaryCenterProps {
  open: boolean;
  onClose: () => void;
}

function matches(item: MetricDictionaryItem, keyword: string): boolean {
  if (!keyword) {
    return true;
  }
  const normalized = keyword.trim().toLowerCase();
  if (!normalized) {
    return true;
  }
  const tokens = [
    item.key,
    item.title,
    item.definition,
    item.calc || "",
    item.tip || "",
    item.category || "",
    ...(item.aliases || []),
  ];
  return tokens.some((token) => token.toLowerCase().includes(normalized));
}

export function MetricDictionaryCenter({ open, onClose }: MetricDictionaryCenterProps) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("全部");

  const categories = useMemo(() => {
    const set = new Set<string>(["全部"]);
    METRIC_DICTIONARY_ITEMS.forEach((item) => set.add(item.category || "其他"));
    return Array.from(set);
  }, []);

  const filtered = useMemo(() => {
    return METRIC_DICTIONARY_ITEMS.filter((item) => {
      const categoryMatched = category === "全部" || (item.category || "其他") === category;
      if (!categoryMatched) {
        return false;
      }
      return matches(item, query);
    });
  }, [category, query]);

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-40 bg-black/70 px-3 py-4 backdrop-blur-sm md:px-6 md:py-8">
      <div className="mx-auto flex h-full max-w-4xl flex-col rounded-2xl border border-slate-700 bg-panel">
        <div className="border-b border-slate-700 px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-base font-semibold text-textMain">指标字典中心</h2>
            <button
              type="button"
              className="rounded-md border border-slate-600 px-2 py-1 text-xs text-textMuted"
              onClick={onClose}
            >
              关闭
            </button>
          </div>
          <p className="mt-1 text-xs text-textMuted">
            支持按关键词检索指标定义、计算逻辑与使用建议。
          </p>
          <input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索：如 命中率 / drift / LONG / 置信度"
            className="mt-3 w-full rounded-lg border border-slate-600 bg-card px-3 py-2 text-sm text-textMain outline-none focus:border-accent/70"
          />
          <div className="mt-2 flex flex-wrap gap-2">
            {categories.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setCategory(item)}
                className={`rounded-full border px-2 py-0.5 text-xs ${
                  category === item
                    ? "border-accent/70 bg-cyan-500/10 text-accent"
                    : "border-slate-600 text-textMuted"
                }`}
              >
                {item}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3">
          {filtered.length > 0 ? (
            <div className="space-y-3">
              {filtered.map((item) => (
                <article
                  key={item.key}
                  className="rounded-lg border border-slate-700/80 bg-card/40 p-3 text-sm"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-textMain">{item.title}</span>
                    <span className="rounded border border-slate-600 px-1.5 py-0.5 text-[11px] text-textMuted">
                      {item.key}
                    </span>
                    <span className="rounded border border-slate-600 px-1.5 py-0.5 text-[11px] text-textMuted">
                      {item.category || "其他"}
                    </span>
                  </div>
                  <p className="mt-2 text-textMuted">{item.definition}</p>
                  {item.calc && <p className="mt-1 text-textMuted">计算：{item.calc}</p>}
                  {item.tip && <p className="mt-1 text-textMuted">建议：{item.tip}</p>}
                </article>
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-slate-700/80 bg-card/30 p-4 text-sm text-textMuted">
              没有命中结果，请换个关键词。
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
