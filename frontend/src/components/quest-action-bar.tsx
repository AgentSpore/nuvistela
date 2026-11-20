"use client";
import { useTranslations } from "next-intl";
import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { Button } from "@/components/ui/button";

type Props = {
  onDone: () => void;
  ref: RefObject<HTMLButtonElement | null>;
  /** Where focus goes if the bar disappears while it holds focus. */
  fallback: RefObject<HTMLElement | null>;
};

/**
 * The quest's main action pinned to the bottom while the card's own button is off screen.
 * It is 72 px tall; the page adds matching bottom padding while it is shown (`adventure.tsx`).
 */
export function QuestActionBar({ onDone, ref, fallback }: Props) {
  const t = useTranslations("adventure");
  const [shown, setShown] = useState(false);
  const bar = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(frame);
  }, []);
  // A layout cleanup runs before the node leaves the DOM, while focus is still readable.
  useLayoutEffect(() => {
    const el = bar.current;
    const back = fallback.current;
    return () => {
      if (el?.contains(document.activeElement)) back?.focus({ preventScroll: true });
    };
  }, [fallback]);
  return (
    <div
      ref={bar}
      data-testid="quest-action-bar"
      className={`fixed inset-x-0 bottom-0 z-30 border-t border-line bg-card p-3 shadow-[0_-4px_12px_oklch(0_0_0/0.08)] transition-[opacity,transform] duration-200 motion-reduce:transition-none ${shown ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0 motion-reduce:translate-y-0 motion-reduce:opacity-100"}`}
    >
      <div className="mx-auto w-full max-w-3xl">
        <Button
          ref={ref}
          onClick={onDone}
          aria-describedby="quest-title"
          className="w-full"
        >
          {t("done")}
        </Button>
      </div>
    </div>
  );
}
