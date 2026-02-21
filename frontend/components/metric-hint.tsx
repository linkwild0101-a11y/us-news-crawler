"use client";

import { useEffect, useRef, useState } from "react";

import { MetricExplanation } from "@/lib/metric-explanations";

interface MetricHintProps {
  explanation: MetricExplanation;
}

export function MetricHint({ explanation }: MetricHintProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    function onPointerDown(event: PointerEvent) {
      if (!rootRef.current) {
        return;
      }
      if (!rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, []);

  return (
    <span
      ref={rootRef}
      className="relative ml-1 inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-slate-500/80 text-[10px] text-textMuted hover:text-textMain"
        aria-label={`${explanation.title} 说明`}
        onClick={() => setOpen((prev) => !prev)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >
        i
      </button>

      {open && (
        <div className="absolute right-0 top-6 z-30 w-72 rounded-lg border border-slate-600/90 bg-panel p-3 text-xs shadow-xl">
          <p className="font-semibold text-textMain">{explanation.title}</p>
          <p className="mt-1 leading-5 text-textMuted">{explanation.definition}</p>
          {explanation.calc && (
            <p className="mt-1 leading-5 text-textMuted">计算：{explanation.calc}</p>
          )}
          {explanation.tip && (
            <p className="mt-1 leading-5 text-textMuted">建议：{explanation.tip}</p>
          )}
        </div>
      )}
    </span>
  );
}
