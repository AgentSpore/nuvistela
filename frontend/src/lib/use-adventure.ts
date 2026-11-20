"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getAdventure,
  isPending,
  type Adventure,
  type Chapter,
} from "@/lib/adventure-api";

export type AdventureState =
  { status: "loading" } | { status: "error" } | { status: "ready"; data: Adventure };

/** Flat delay between reads while a chapter or the world is being written. */
export const POLL_MS = 1500;
const BACKOFF_MS = 3000;
const MAX_BACKOFF_MS = 5000;

const SLOW_WORLD_MS = 180_000;
const SLOW_CHAPTER_MS = 60_000;

/** When a continuous wait began: kept while `active`, cleared the moment it ends. */
const waitSince = (prev: number | null, active: boolean): number | null =>
  active ? (prev ?? Date.now()) : null;

type Waits = {
  worldSince: number | null;
  chapterSince: Map<string, number>;
  worldSlow: boolean;
  slowChapterIds: string[];
};

/** Advance the world and per-chapter wait clocks with a fresh reading; `null` starts them empty. */
function trackWaits(prev: Waits | null, data: Adventure | null): Waits {
  const worldSince = waitSince(
    prev?.worldSince ?? null,
    data?.world?.status === "pending",
  );
  const chapterSince = trackChapterWaits(
    prev?.chapterSince ?? new Map(),
    data?.chapters ?? [],
  );
  return {
    worldSince,
    chapterSince,
    worldSlow: waitedLongerThan(worldSince, SLOW_WORLD_MS),
    slowChapterIds: [...chapterSince]
      .filter(([, t]) => waitedLongerThan(t, SLOW_CHAPTER_MS))
      .map(([id]) => id),
  };
}

/** First-seen-pending time per chapter id; a chapter that left pending is dropped, so a later wait starts afresh. */
const trackChapterWaits = (
  prev: ReadonlyMap<string, number>,
  chapters: Chapter[],
): Map<string, number> =>
  new Map(chapters.filter(isPending).map((c) => [c.id, prev.get(c.id) ?? Date.now()]));

const waitedLongerThan = (since: number | null, limitMs: number): boolean =>
  since !== null && Date.now() - since >= limitMs;

/** Something is still coming: a chapter or the world is being written, or the world exists but its first quest has not arrived. */
const awaitsUpdate = (d: Adventure): boolean =>
  d.world?.status === "pending" ||
  d.chapters.some(isPending) ||
  (d.world !== null && d.quest === null && d.chapters.length === 0);

/** Delay before the nth poll in a row of the world cover poll (use-world): 3 s, growing by half, capped at 5 s. */
export const pollDelay = (n: number): number =>
  Math.min(BACKOFF_MS * 1.5 ** n, MAX_BACKOFF_MS);

/**
 * The adventure from the API, the screen's only source of truth. While the world or a chapter is
 * being written, or the first quest is awaited, it polls every 1.5 s, and not at all while the tab is hidden.
 */
export function useAdventure(familyId: string): {
  state: AdventureState;
  paused: boolean;
  slow: boolean;
  slowChapterIds: string[];
  reload: () => void;
} {
  const [state, setState] = useState<AdventureState>({ status: "loading" });
  const [paused, setPaused] = useState(false);
  const [slow, setSlow] = useState(false);
  const [slowChapterIds, setSlowChapterIds] = useState<string[]>([]);
  const [tick, setTick] = useState(0);
  // Wait clocks outlive reloads (quest done, retry) and restart only for another family.
  const clocks = useRef({ familyId, waits: trackWaits(null, null) });
  useEffect(() => {
    if (clocks.current.familyId !== familyId)
      clocks.current = { familyId, waits: trackWaits(null, null) };
    let live = true;
    let pending = false;
    let timer: number | undefined;
    const arm = () => {
      window.clearTimeout(timer);
      if (live && pending && !document.hidden) timer = window.setTimeout(load, POLL_MS);
    };
    async function load() {
      window.clearTimeout(timer);
      try {
        const data = await getAdventure(familyId);
        if (!live) return;
        pending = awaitsUpdate(data);
        const waits = (clocks.current.waits = trackWaits(clocks.current.waits, data));
        setSlow(waits.worldSlow);
        setSlowChapterIds(waits.slowChapterIds);
        setState({ status: "ready", data });
        setPaused(false);
      } catch {
        if (live && pending) setPaused(true);
        if (live) setState((s) => (s.status === "ready" ? s : { status: "error" }));
      }
      arm();
    }
    const onVisibility = () =>
      document.hidden ? window.clearTimeout(timer) : pending && load();
    document.addEventListener("visibilitychange", onVisibility);
    load();
    return () => {
      live = false;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [familyId, tick]);
  const reload = useCallback(() => {
    setState((s) => (s.status === "error" ? { status: "loading" } : s));
    setTick((n) => n + 1);
  }, []);
  return { state, paused, slow, slowChapterIds, reload };
}
