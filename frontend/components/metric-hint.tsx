"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { MetricExplanation } from "@/lib/metric-explanations";

interface MetricHintProps {
  explanation: MetricExplanation;
}

const TOOLTIP_WIDTH = 288;
const TOOLTIP_FALLBACK_HEIGHT = 140;
const TOOLTIP_GAP = 8;
const VIEWPORT_MARGIN = 8;

export function MetricHint({ explanation }: MetricHintProps) {
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0, ready: false });
  const rootRef = useRef<HTMLSpanElement | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);

  const closeHint = useCallback(() => {
    setOpen(false);
    setPinned(false);
  }, []);

  const openHint = useCallback(() => {
    setPosition((prev) => ({ ...prev, ready: false }));
    setOpen(true);
  }, []);

  const updatePosition = useCallback(() => {
    if (!rootRef.current || typeof window === "undefined") {
      return;
    }

    const rect = rootRef.current.getBoundingClientRect();
    const width = tooltipRef.current?.offsetWidth ?? TOOLTIP_WIDTH;
    const height = tooltipRef.current?.offsetHeight ?? TOOLTIP_FALLBACK_HEIGHT;

    const maxLeft = window.innerWidth - width - VIEWPORT_MARGIN;
    let left = rect.right - width;
    left = Math.max(VIEWPORT_MARGIN, Math.min(left, maxLeft));

    let top = rect.bottom + TOOLTIP_GAP;
    if (top + height + VIEWPORT_MARGIN > window.innerHeight) {
      top = Math.max(VIEWPORT_MARGIN, rect.top - height - TOOLTIP_GAP);
    }

    setPosition({ top, left, ready: true });
  }, []);

  useEffect(() => {
    function onPointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (rootRef.current?.contains(target) || tooltipRef.current?.contains(target)) {
        return;
      }
      closeHint();
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        closeHint();
      }
    }

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [closeHint]);

  useEffect(() => {
    if (!open) {
      return;
    }

    updatePosition();
    const raf = window.requestAnimationFrame(updatePosition);
    const onReposition = () => updatePosition();

    window.addEventListener("resize", onReposition);
    window.addEventListener("scroll", onReposition, true);

    return () => {
      window.cancelAnimationFrame(raf);
      window.removeEventListener("resize", onReposition);
      window.removeEventListener("scroll", onReposition, true);
    };
  }, [open, updatePosition]);

  const tooltip =
    open && typeof document !== "undefined"
      ? createPortal(
          <div
            ref={tooltipRef}
            className="fixed z-[120] w-72 rounded-lg border border-slate-600/90 bg-panel p-3 text-xs shadow-xl"
            style={{
              top: position.top,
              left: position.left,
              visibility: position.ready ? "visible" : "hidden"
            }}
            onMouseEnter={() => setOpen(true)}
            onMouseLeave={() => {
              if (!pinned) {
                setOpen(false);
              }
            }}
          >
            <p className="font-semibold text-textMain">{explanation.title}</p>
            <p className="mt-1 leading-5 text-textMuted">{explanation.definition}</p>
            {explanation.calc && (
              <p className="mt-1 leading-5 text-textMuted">计算：{explanation.calc}</p>
            )}
            {explanation.tip && (
              <p className="mt-1 leading-5 text-textMuted">建议：{explanation.tip}</p>
            )}
          </div>,
          document.body
        )
      : null;

  return (
    <span
      ref={rootRef}
      className="ml-1 inline-flex"
      onMouseEnter={openHint}
      onMouseLeave={() => {
        if (!pinned) {
          setOpen(false);
        }
      }}
    >
      <button
        type="button"
        className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-slate-500/80 text-[10px] text-textMuted hover:text-textMain"
        aria-label={`${explanation.title} 说明`}
        onClick={() => {
          if (pinned) {
            closeHint();
            return;
          }
          setPinned(true);
          openHint();
        }}
        onFocus={openHint}
        onBlur={() => {
          if (!pinned) {
            setOpen(false);
          }
        }}
      >
        i
      </button>
      {tooltip}
    </span>
  );
}
