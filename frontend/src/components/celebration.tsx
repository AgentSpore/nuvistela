"use client";
import type { CSSProperties, ReactNode } from "react";

const SPARKS = 16;
const COLORS = ["var(--honey)", "var(--honey-deep)", "oklch(0.9 0.12 95)"];

/** Matches what the reward card's scroll already honours; read once, the burst plays once. */
export function prefersCalm(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;
}

function Spark({ i }: { i: number }) {
  const style = {
    "--a": `${(360 / SPARKS) * i + (i % 2) * 11}deg`,
    "--d": `${i % 3 === 0 ? 80 : i % 3 === 1 ? 62 : 46}px`,
    "--delay": `${(i % 4) * 40}ms`,
    background: COLORS[i % COLORS.length],
  } as CSSProperties;
  const shape = i % 2 ? "size-3 rounded-full" : "size-3.5 rotate-45 rounded-[3px]";
  return (
    <span
      style={style}
      className={`spark pointer-events-none absolute left-1/2 top-1/2 -ml-1.5 -mt-1.5 ${shape}`}
    />
  );
}

/**
 * Honey sparks burst from the check; under reduced motion only a still glow.
 * Everything is absolutely placed around the icon: the card keeps its height, nothing shifts.
 */
export function Celebration({ calm, children }: { calm: boolean; children: ReactNode }) {
  return (
    <span
      aria-hidden="true"
      data-testid="celebration"
      data-motion={calm ? "calm" : "burst"}
      className="relative inline-flex"
    >
      {calm ? (
        <span className="halo pointer-events-none absolute -inset-3 rounded-full bg-honey-soft blur-md" />
      ) : (
        <>
          <span className="burst-ring pointer-events-none absolute inset-0 rounded-full border-4 border-honey" />
          {Array.from({ length: SPARKS }, (_, i) => (
            <Spark key={i} i={i} />
          ))}
        </>
      )}
      <span className="relative inline-flex">{children}</span>
    </span>
  );
}
