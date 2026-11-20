"use client";
import { useEffect, useRef } from "react";

/** How often a player who is not choosing the world asks whether it has been chosen. */
export const WORLD_WAIT_MS = 3000;

/**
 * Calls `onPoll` every few seconds, not while the tab is hidden. A tick is skipped while the
 * previous call (when it returns a promise) is still running, so a slow answer is never overtaken.
 */
export function useWorldPoll(onPoll: () => void | Promise<unknown>): void {
  const running = useRef(false);
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.hidden || running.current) return;
      running.current = true;
      Promise.resolve(onPoll())
        .catch(() => {})
        .finally(() => {
          running.current = false;
        });
    }, WORLD_WAIT_MS);
    return () => window.clearInterval(timer);
  }, [onPoll]);
}
